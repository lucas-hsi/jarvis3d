"""
Oficina do Jarvis: a pasta-sandbox onde ele cria arquivos, scripts e pequenos programas, e o executor VISÍVEL.

Tudo o que ele roda aparece numa janela do PowerShell na tela (título "Jarvis · ..."), com o comando em amarelo e a saída
ao vivo; a mesma saída vai linha a linha para a tela do Jarvis (mensagem WS `terminal`). Nada roda escondido.

Segurança (imposta aqui, não pelo modelo):
- Pasta: só dentro de OFICINA (padrão %USERPROFILE%\\Jarvis Oficina; ajuste "oficina_pasta"). Nunca '..', nunca fora.
- Sobrescrever guarda a versão anterior (DADOS\\oficina\\versoes): nada se perde.
- Comandos passam pelo seguranca_cmd: leitura roda direto; criar na Oficina roda direto (se o pedido não leu conteúdo de fora);
  risco pede confirmação forte ("confirmo"); bloqueado nunca roda.
- Python roda pela guarda (guarda\\guarda_python.py): grava só na Oficina, sem abrir programas, sem internet (salvo autorizado).
- Sem administrador, tempo máximo, saída cortada, auditoria em memoria\\terminal.log (comando, nível, código; sem a saída).
"""

import asyncio
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import caminhos
import seguranca_cmd

PASTA = Path(os.environ.get("JARVIS_OFICINA") or (Path.home() / "Jarvis Oficina"))
INTERNO = caminhos.DADOS / "oficina"                 # FORA da Oficina: os scripts não alcançam os executores nem as versões
GUARDA = caminhos.CODIGO / "guarda" / "guarda_python.py"
LOG = caminhos.DADOS / "memoria" / "terminal.log"
VISIVEL = os.environ.get("JARVIS_TERMINAL_OCULTO") != "1"
SEGURA_JANELA_S = 25                                  # a janela fica na tela depois de terminar, para dar tempo de ler
EXT_TEXTO = {".py", ".pyw", ".ps1", ".psm1", ".bat", ".cmd", ".txt", ".md", ".json", ".csv", ".html", ".htm", ".css", ".js", ".mjs", ".ts",
             ".jsx", ".tsx", ".vue", ".svg", ".xml", ".yml", ".yaml", ".ini", ".toml", ".cfg", ".sql", ".log", ".gitignore", ".env.example", ""}
NOMES_RESERVADOS = re.compile(r"(?i)^(con|prn|aux|nul|com\d|lpt\d)(\.|$)")
MAX_ARQUIVO = 400_000
CREATE_NEW_CONSOLE, CREATE_NO_WINDOW = 0x10, 0x08000000
CFG: dict = {}
BOM = "\ufeff"                                        # PowerShell 5.1 só lê acentos certo com BOM


def configurar(cfg: dict):
    """Chamado pelo servidor ao subir: pasta e Python escolhidos no config/ajustes."""
    global PASTA
    CFG.clear()
    CFG.update(cfg or {})
    if cfg.get("oficina_pasta") and not os.environ.get("JARVIS_OFICINA"):
        PASTA = Path(str(cfg["oficina_pasta"])).expanduser()


def pasta() -> Path:
    if not PASTA.exists():
        PASTA.mkdir(parents=True, exist_ok=True)
        (PASTA / "LEIA-ME.txt").write_text(
            "Oficina do Jarvis\n\nAqui o Jarvis cria arquivos, scripts e pequenos programas quando você pede.\n"
            "Ele só grava dentro desta pasta. Scripts Python rodam com uma guarda que impede gravar fora daqui,\n"
            "abrir outros programas e acessar a internet sem a sua autorização.\n"
            "Versões anteriores de arquivos sobrescritos ficam guardadas pelo Jarvis (dá para pedir de volta).\n", encoding="utf-8")
    return PASTA


def resolver(relativo: str, deve_existir: bool = False) -> Path:
    """Caminho dentro da Oficina. Aceita relativo ('calc/app.py') ou absoluto que já esteja dentro dela."""
    base = pasta().resolve()
    texto = str(relativo or "").strip().strip("'\"")
    if not texto or texto in (".", "\\", "/"):
        return base
    if "\x00" in texto or ".." in Path(texto).parts:
        raise ValueError("Caminho inválido: use um caminho dentro da Oficina, sem '..'.")
    p = Path(texto)
    alvo = (p if p.is_absolute() else base / p).resolve()
    if alvo != base and base not in alvo.parents:
        raise ValueError(f"Só posso mexer dentro da Oficina ({base}). '{texto}' fica fora dela.")
    if any(NOMES_RESERVADOS.match(parte) for parte in alvo.relative_to(base).parts):
        raise ValueError("Nome reservado do Windows (CON, NUL, COM1...).")
    if deve_existir and not alvo.exists():
        raise ValueError(f"Não existe na Oficina: {alvo.relative_to(base)}")
    return alvo


def relativo(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(pasta().resolve())) or "."
    except ValueError:
        return str(p)


# ------------------------------------------------------------------ Python e editor
def python_exe() -> str | None:
    escolhido = CFG.get("python_exe")
    if escolhido and Path(escolhido).exists():
        return str(escolhido)
    for nome in ("python", "py"):
        achado = shutil.which(nome)
        if achado and "windowsapps" not in achado.lower():      # o "python" da Microsoft Store é só um atalho que abre a loja
            return achado
    return None


def abrir_no_editor(arquivo: Path) -> str:
    """Mostra o arquivo para o usuário. Nunca 'executa' (os.startfile num .py rodaria o script)."""
    code = shutil.which("code")
    try:
        if code:
            subprocess.Popen(["cmd", "/c", "code", "--reuse-window", str(arquivo)], creationflags=CREATE_NO_WINDOW,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "VS Code"
        subprocess.Popen(["notepad.exe", str(arquivo)])
        return "Bloco de Notas"
    except OSError as e:
        return f"não consegui abrir o editor ({e})"


def abrir_pasta_no_explorer(p: Path):
    subprocess.Popen(["explorer.exe", str(p if p.is_dir() else p.parent)])


# ------------------------------------------------------------------ arquivos
def escrever(rel: str, conteudo: str) -> tuple[Path, bool, str]:
    """(arquivo, era_novo, aviso). Sobrescrever guarda a versão anterior."""
    alvo = resolver(rel)
    if alvo == pasta().resolve():
        raise ValueError("Informe o nome do arquivo (ex.: calculadora/app.py).")
    ext = "".join(alvo.suffixes[-2:]).lower() if alvo.name.endswith(".env.example") else alvo.suffix.lower()
    if ext not in EXT_TEXTO:
        raise ValueError(f"Só crio arquivos de texto e código (.py, .ps1, .html, .js, .md, .json...). '{ext}' não.")
    if alvo.name.lower() == ".env":
        raise ValueError("Não crio arquivo .env (segredos). Use .env.example sem valores reais.")
    if len(conteudo.encode("utf-8")) > MAX_ARQUIVO:
        raise ValueError("Conteúdo grande demais (máx. 400 KB por arquivo).")
    novo, aviso = not alvo.exists(), ""
    if not novo:
        if alvo.is_dir():
            raise ValueError("Já existe uma pasta com esse nome.")
        destino = INTERNO / "versoes" / relativo(alvo)
        destino = destino.with_name(destino.name + time.strftime(".%Y%m%d-%H%M%S"))
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(alvo, destino)
        aviso = "a versão anterior ficou guardada"
    alvo.parent.mkdir(parents=True, exist_ok=True)
    bom = BOM if ext in (".ps1", ".psm1") and not conteudo.startswith(BOM) else ""     # PowerShell 5.1 lê acentos certo com BOM
    alvo.write_text(bom + conteudo, encoding="utf-8", newline="\r\n" if ext in (".ps1", ".bat", ".cmd") else None)
    return alvo, novo, aviso


def ler(rel: str, limite: int = 40_000) -> str:
    alvo = resolver(rel, deve_existir=True)
    if alvo.is_dir():
        return listar(rel)
    texto = alvo.read_text(encoding="utf-8", errors="replace")
    return texto if len(texto) <= limite else texto[:limite] + f"\n[... cortado: {len(texto)} caracteres no total]"


def listar(rel: str = "", limite: int = 200) -> str:
    base = resolver(rel, deve_existir=True)
    linhas, n = [f"Oficina: {pasta()}", f"Pasta: {relativo(base)}"], 0
    for raiz, pastas, arquivos in os.walk(base):
        pastas[:] = sorted(p for p in pastas if p not in ("__pycache__", "node_modules", ".git", ".venv", "venv"))
        nivel = len(Path(raiz).relative_to(base).parts)
        if nivel > 3:
            continue
        for a in sorted(arquivos):
            n += 1
            if n > limite:
                linhas.append(f"... (mais itens; peça uma subpasta)")
                return "\n".join(linhas)
            f = Path(raiz) / a
            linhas.append(f"{'  ' * nivel}{relativo(f)}  ({f.stat().st_size} B)")
    if n == 0:
        linhas.append("(vazia)")
    return "\n".join(linhas)


# ------------------------------------------------------------------ executor visível
def _q(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def _janela_host(titulo: str, pasta_exec: Path, exibir: str, nivel: str, chamada: str, fim: Path, segurar: int) -> str:
    """Script da janela visível: cabeçalho, o comando em amarelo, a execução, o resultado e uma pausa para ler."""
    linhas_cmd = [l for l in exibir.splitlines() if l.strip()][:8] or [exibir]
    mostra = "\n".join(f"Write-Host ('  ' + {_q(l[:220])}) -ForegroundColor Yellow" for l in linhas_cmd)
    cor = {"leitura": "DarkCyan", "oficina": "DarkGreen", "risco": "DarkYellow"}.get(nivel, "DarkCyan")
    return f"""$ProgressPreference = 'SilentlyContinue'
try {{ [Console]::OutputEncoding = [Text.Encoding]::UTF8 }} catch {{ }}
try {{ $Host.UI.RawUI.WindowTitle = {_q('Jarvis · ' + titulo[:80])} }} catch {{ }}
Write-Host ''
Write-Host '  JARVIS  ' -BackgroundColor {cor} -ForegroundColor White -NoNewline
Write-Host ('  ' + {_q(titulo[:120])}) -ForegroundColor Cyan
Write-Host ('  pasta: ' + {_q(str(pasta_exec))} + '   |   segurança: ' + {_q(nivel)}) -ForegroundColor DarkGray
Write-Host ''
{mostra}
Write-Host ''
Set-Location -LiteralPath {_q(str(pasta_exec))}
$__t = [Diagnostics.Stopwatch]::StartNew()
{chamada}
$__c = $LASTEXITCODE
if ($null -eq $__c) {{ $__c = 0 }}
Set-Content -LiteralPath {_q(str(fim))} -Value $__c -Encoding ASCII
Write-Host ''
if ($__c -eq 0) {{ Write-Host ('  [OK] Concluído em {{0:N1}} s' -f $__t.Elapsed.TotalSeconds) -ForegroundColor Green }}
else {{ Write-Host ('  [ERRO] Terminou com código ' + $__c) -ForegroundColor Red }}
if ({segurar} -gt 0) {{
    Write-Host ('  Esta janela fecha sozinha em {segurar} s (qualquer tecla fecha agora).') -ForegroundColor DarkGray
    $__ate = (Get-Date).AddSeconds({segurar})
    while ((Get-Date) -lt $__ate) {{ try {{ if ([Console]::KeyAvailable) {{ break }} }} catch {{ break }}; Start-Sleep -Milliseconds 200 }}
}}
"""


def _filho_ps(comando: str, saida: Path) -> str:
    """Script que roda o comando do Jarvis num PowerShell filho: a saída vai para a janela E para o arquivo que o servidor lê."""
    return f"""$ProgressPreference = 'SilentlyContinue'
try {{ [Console]::OutputEncoding = [Text.Encoding]::UTF8 }} catch {{ }}
$__w = New-Object System.IO.StreamWriter({_q(str(saida))}, $false, (New-Object System.Text.UTF8Encoding($false)))
$__w.AutoFlush = $true
& {{
{comando}
}} *>&1 | Out-String -Stream -Width 180 | ForEach-Object {{ [Console]::WriteLine($_); $__w.WriteLine($_) }}
$__w.Close()
if ($LASTEXITCODE) {{ exit $LASTEXITCODE }}
"""


async def executar_visivel(sessao, *, titulo: str, pasta_exec: Path, exibir: str, nivel: str, segundos: int,
                           comando_ps: str | None = None, python: tuple[str, Path, list[str], bool] | None = None) -> tuple[int | None, str, float, str]:
    """Roda numa janela visível do PowerShell. Devolve (código ou None se passou do tempo/fechada, saída, segundos, situação)."""
    rid = uuid.uuid4().hex[:8]
    pasta_int = INTERNO / "exec"
    pasta_int.mkdir(parents=True, exist_ok=True)
    for velho in pasta_int.glob("*"):                                 # limpa execuções de mais de 1 dia
        try:
            if time.time() - velho.stat().st_mtime > 86400:
                velho.unlink()
        except OSError:
            pass
    saida, fim, host = pasta_int / f"{rid}.saida.txt", pasta_int / f"{rid}.fim", pasta_int / f"{rid}.ps1"
    if python:
        exe, script, args, rede = python
        partes = [_q(exe), "-E", "-u", "-X", "utf8", _q(str(GUARDA)), "--raiz", _q(str(pasta())), "--saida", _q(str(saida))]
        if rede:
            partes.append("--rede")
        partes += ["--", _q(str(script))] + [_q(a) for a in args]
        chamada = "& " + " ".join(partes)
    else:
        filho = pasta_int / f"{rid}.cmd.ps1"
        filho.write_text(BOM + _filho_ps(comando_ps or "", saida), encoding="utf-8")
        chamada = f"& powershell.exe -NoProfile -ExecutionPolicy Bypass -File {_q(str(filho))}"
    host.write_text(BOM + _janela_host(titulo, pasta_exec, exibir, nivel, chamada, fim, SEGURA_JANELA_S if VISIVEL else 0), encoding="utf-8")

    gid = "term-" + rid
    await sessao.enviar({"tipo": "terminal", "id": gid, "inicio": True, "titulo": titulo[:120], "comando": exibir[:600], "nivel": nivel,
                         "pasta": str(pasta_exec), "visivel": VISIVEL})
    t0 = time.monotonic()
    proc = subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(host)], cwd=str(pasta_exec),
                            creationflags=CREATE_NEW_CONSOLE if VISIVEL else CREATE_NO_WINDOW,
                            stdin=None if VISIVEL else subprocess.DEVNULL, stdout=None if VISIVEL else subprocess.DEVNULL,
                            stderr=None if VISIVEL else subprocess.DEVNULL)
    if VISIVEL:
        asyncio.create_task(_trazer_para_frente("Jarvis · " + titulo[:80]))
    lidos, resto, codigo, situacao = 0, "", None, ""
    while True:
        await asyncio.sleep(0.25)
        try:
            if saida.exists():
                with open(saida, "rb") as f:
                    f.seek(lidos)
                    pedaco = f.read()
                if pedaco:
                    lidos += len(pedaco)
                    texto = resto + pedaco.decode("utf-8", errors="replace")
                    *linhas, resto = texto.split("\n")
                    if linhas:
                        await sessao.enviar({"tipo": "terminal", "id": gid, "linhas": [l.rstrip("\r")[:300] for l in linhas[-60:]]})
        except OSError:
            pass
        if fim.exists():
            try:
                codigo = int((fim.read_text(encoding="ascii", errors="ignore").strip() or "0").splitlines()[0])
            except ValueError:
                codigo = 1
            situacao = "ok"
            break
        if proc.poll() is not None:
            await asyncio.sleep(0.3)
            if not fim.exists():
                situacao = "fechada"                                    # o usuário fechou a janela antes do fim (ou o PowerShell caiu)
                break
        if time.monotonic() - t0 > segundos:
            await asyncio.to_thread(subprocess.run, ["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                                    creationflags=CREATE_NO_WINDOW)
            situacao = "tempo"
            break
    if resto.strip():
        await sessao.enviar({"tipo": "terminal", "id": gid, "linhas": [resto.rstrip("\r")[:300]]})
    texto = saida.read_text(encoding="utf-8", errors="replace").strip() if saida.exists() else ""
    gasto = time.monotonic() - t0
    await sessao.enviar({"tipo": "terminal", "id": gid, "fim": True, "codigo": codigo, "situacao": situacao, "segundos": round(gasto, 1)})
    if not VISIVEL:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    return codigo, texto, gasto, situacao


async def _trazer_para_frente(titulo: str):
    """Põe a janela do PowerShell por cima das outras SEM roubar o teclado (o usuário continua falando/escrevendo no Jarvis)."""
    try:
        import windows_ctl
    except Exception:
        return
    for _ in range(16):
        await asyncio.sleep(0.25)
        try:
            if await asyncio.to_thread(windows_ctl.trazer_sem_foco, titulo):
                return
        except Exception:
            return


def cortar(saida: str, limite: int = 6000) -> str:
    return saida if len(saida) <= limite else saida[:limite // 2] + "\n[... cortado ...]\n" + saida[-(limite // 2 - 200):]


def auditar(comando: str, nivel: str, codigo, segundos: float, origem: str = "terminal"):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{origem}\tnivel={nivel}\tcodigo={codigo}\t{segundos:.1f}s\t{comando[:300]!r}\n")
    except OSError:
        pass


# ------------------------------------------------------------------ política: quem decide se roda
async def autorizar(sessao, nivel: str, motivos: list[str], titulo: str, detalhes: list[str]) -> tuple[bool, str]:
    """(pode_rodar, mensagem_para_o_modelo_se_nao). Leitura roda; oficina roda se o pedido não leu conteúdo de fora; risco confirma forte."""
    if nivel == "bloqueado":
        await sessao.enviar({"tipo": "aviso", "texto": "Bloqueado pela segurança: " + "; ".join(motivos)})
        return False, ("BLOQUEADO pela segurança do Jarvis (não roda nem com confirmação): " + "; ".join(motivos) +
                       ". Diga isso em uma frase e, se for algo que ele realmente quer, explique que ele mesmo precisa fazer à mão.")
    if nivel == "leitura":
        return True, ""
    if nivel == "oficina" and getattr(sessao, "liberado", lambda _o: False)("oficina"):
        return True, ""
    alto = nivel == "risco"
    corpo = (["RISCO: " + m for m in motivos] if alto else []) + detalhes
    if not await _confirmar(sessao, titulo, corpo, "alto" if alto else "medio"):
        return False, "O usuário NÃO autorizou. Nada foi executado. Não insista; diga em uma frase que respeita a decisão."
    return True, ""


async def _confirmar(sessao, titulo: str, detalhes: list[str], nivel: str) -> bool:
    try:
        return await sessao.confirmar(titulo, detalhes, nivel=nivel)
    except TypeError:                                                  # sessões antigas/testes sem o parâmetro nivel
        return await sessao.confirmar(titulo, detalhes)


# ------------------------------------------------------------------ ferramentas
def _def(nome, descricao, props, req):
    return {"name": nome, "description": descricao, "input_schema": {"type": "object", "properties": props, "required": req}}


DEFINICOES = [
    _def("oficina_escrever",
         "Cria ou atualiza um arquivo de texto/código (Python, PowerShell, HTML, JS, CSS, JSON, Markdown...) na OFICINA do Jarvis "
         "(pasta-sandbox do usuário). Use para escrever scripts e pequenos programas inteiros, um arquivo por chamada. Não pede "
         "confirmação; sobrescrever guarda a versão anterior. Por padrão abre o arquivo no editor para o usuário VER. "
         "Organize cada programa numa subpasta (ex.: 'calculadora/app.py').",
         {"caminho": {"type": "string", "description": "caminho relativo dentro da Oficina, ex.: 'organizador/main.py'"},
          "conteudo": {"type": "string", "description": "o conteúdo COMPLETO do arquivo"},
          "abrir": {"type": "boolean", "description": "abrir no editor para o usuário ver (padrão true; em projetos com vários arquivos, abra só o principal)"}},
         ["caminho", "conteudo"]),
    _def("oficina_rodar",
         "RODA um script da Oficina numa janela do PowerShell VISÍVEL para o usuário e devolve a saída. .py roda com a GUARDA "
         "(grava só na Oficina, não abre outros programas, sem internet a menos que rede=true, que pede confirmação). .ps1/.bat passam "
         "pela análise de risco (o perigoso pede confirmação; o destrutivo é bloqueado). .html abre no navegador. Use depois de "
         "oficina_escrever para testar o que criou; se der erro, corrija o arquivo e rode de novo.",
         {"arquivo": {"type": "string", "description": "caminho relativo na Oficina, ex.: 'calculadora/app.py'"},
          "argumentos": {"type": "array", "items": {"type": "string"}, "description": "argumentos da linha de comando (opcional)"},
          "rede": {"type": "boolean", "description": "o script precisa de internet (pede confirmação do usuário)"},
          "segundos": {"type": "number", "description": "tempo máximo (padrão 120, máximo 600)"}},
         ["arquivo"]),
    _def("oficina_ler", "Lê um arquivo da Oficina (para corrigir ou continuar um programa). Só leitura.",
         {"caminho": {"type": "string"}}, ["caminho"]),
    _def("oficina_listar", "Lista os arquivos da Oficina (ou de uma subpasta dela). Só leitura.",
         {"pasta": {"type": "string", "description": "subpasta (opcional)"}}, []),
    _def("oficina_abrir", "Mostra ao usuário: abre a pasta da Oficina (ou uma subpasta) no Explorador, ou um arquivo no editor.",
         {"caminho": {"type": "string", "description": "pasta ou arquivo dentro da Oficina (vazio = a Oficina)"}}, []),
]
NOMES = {d["name"] for d in DEFINICOES}
ROTULOS = {"oficina_escrever": "OFICINA", "oficina_rodar": "TERMINAL", "oficina_ler": "OFICINA", "oficina_listar": "OFICINA",
           "oficina_abrir": "OFICINA"}


def descrever(nome: str, entrada: dict) -> str:
    return str(entrada.get("caminho") or entrada.get("arquivo") or entrada.get("pasta") or "Oficina")[:60]


async def executar(nome: str, entrada: dict, sessao) -> str:
    if nome == "oficina_listar":
        return listar(str(entrada.get("pasta") or ""))
    if nome == "oficina_ler":
        return ler(str(entrada.get("caminho") or ""))
    if nome == "oficina_abrir":
        alvo = resolver(str(entrada.get("caminho") or ""), deve_existir=True)
        if alvo.is_dir():
            abrir_pasta_no_explorer(alvo)
            return f"Pasta aberta no Explorador: {alvo}"
        return f"Arquivo aberto no {abrir_no_editor(alvo)}: {alvo}"
    if nome == "oficina_escrever":
        conteudo = entrada.get("conteudo")
        if not isinstance(conteudo, str):
            raise ValueError("Faltou o 'conteudo' do arquivo.")
        alvo, novo, aviso = escrever(str(entrada.get("caminho") or ""), conteudo)
        linhas = conteudo.splitlines()
        await sessao.enviar({"tipo": "oficina", "evento": "arquivo", "caminho": relativo(alvo), "novo": novo, "linhas": len(linhas),
                             "previa": "\n".join(l[:140] for l in linhas[:22])})
        editor = abrir_no_editor(alvo) if entrada.get("abrir", True) is not False else ""
        sinais = seguranca_cmd.sinais_python(conteudo) if alvo.suffix.lower() in (".py", ".pyw") else []
        partes = [f"{'Criado' if novo else 'Atualizado'}: {alvo} ({len(linhas)} linhas)" + (f"; {aviso}" if aviso else "") + "."]
        if editor:
            partes.append(f"Aberto no {editor} para o usuário ver.")
        if sinais:
            partes.append("Atenção ao rodar: o código " + ", ".join(sinais) + " (a guarda barra o que for fora da Oficina, programas e internet).")
        return " ".join(partes)
    if nome == "oficina_rodar":
        return await rodar(entrada, sessao)
    raise ValueError(f"Ferramenta desconhecida: {nome}")


def _segundos(entrada: dict, padrao: int, maximo: int) -> int:
    try:
        return max(5, min(maximo, int(float(entrada.get("segundos") or padrao))))
    except (TypeError, ValueError):
        return padrao


def _resultado(codigo, saida: str, gasto: float, situacao: str, segundos: int) -> str:
    if situacao == "tempo":
        return f"Passou de {segundos} s e foi encerrado (a janela fechou).\n{cortar(saida)}".strip()
    if situacao == "fechada":
        return f"A janela foi fechada antes de terminar (provavelmente pelo usuário).\n{cortar(saida)}".strip()
    bloqueio = "\n(A guarda do Jarvis barrou uma ação do script: veja a linha [GUARDA DO JARVIS].)" if "[GUARDA DO JARVIS]" in saida else ""
    return f"Código de saída {codigo} ({gasto:.1f} s). O usuário viu tudo na janela do PowerShell.\n{cortar(saida) or '(sem saída)'}{bloqueio}"


async def rodar(entrada: dict, sessao) -> str:
    arquivo = resolver(str(entrada.get("arquivo") or ""), deve_existir=True)
    if arquivo.is_dir():
        raise ValueError("Informe o arquivo a rodar, não a pasta.")
    ext = arquivo.suffix.lower()
    args = [str(a)[:500] for a in (entrada.get("argumentos") or []) if isinstance(a, (str, int, float))][:20]
    segundos = _segundos(entrada, 120, 600)
    rel = relativo(arquivo)
    if ext in (".html", ".htm", ".svg"):
        os.startfile(str(arquivo))                       # abre no navegador padrão (a página roda na caixa de areia do navegador)
        await sessao.enviar({"tipo": "oficina", "evento": "abriu", "caminho": rel})
        return f"Abri {rel} no navegador."
    if ext in (".py", ".pyw"):
        exe = python_exe()
        if not exe:
            return "Não achei o Python instalado neste computador (python/py no PATH). Diga ao usuário para instalar o Python 3 do python.org."
        rede = bool(entrada.get("rede"))
        if rede and not await _confirmar(sessao, f"Rodar {rel} com acesso à internet",
                                         ["O script poderá baixar e enviar dados pela internet.", "O resto da guarda continua: grava só na Oficina e não abre programas."],
                                         "alto"):
            return "O usuário NÃO autorizou a internet para o script. Rode sem rede ou ajuste o código."
        exibir = f"python {rel}" + (" " + " ".join(args) if args else "") + ("   [com internet]" if rede else "   [guarda: só a Oficina, sem internet]")
        codigo, saida, gasto, situacao = await executar_visivel(sessao, titulo=f"rodando {rel}", pasta_exec=arquivo.parent, exibir=exibir,
                                                                nivel="oficina (guarda)", segundos=segundos, python=(exe, arquivo, args, rede))
        auditar(exibir, "oficina", codigo, gasto, "oficina_rodar")
        return _resultado(codigo, saida, gasto, situacao, segundos)
    if ext in (".ps1", ".bat", ".cmd"):
        codigo_fonte = arquivo.read_text(encoding="utf-8", errors="replace").lstrip(BOM)
        nivel, motivos = seguranca_cmd.classificar_script(codigo_fonte, ext, arquivo.parent, pasta())
        nivel = "oficina" if nivel == "leitura" else nivel
        ok, msg = await autorizar(sessao, nivel, motivos, f"Rodar o script {rel}", [f"Arquivo: {arquivo}", f"Tempo máximo: {segundos} s. Sem administrador."])
        if not ok:
            auditar(rel, nivel, "negado", 0, "oficina_rodar")
            return msg
        comando = f"& {_q(str(arquivo))} " + " ".join(_q(a) for a in args) if ext == ".ps1" else f"cmd /c {_q(str(arquivo))} " + " ".join(_q(a) for a in args)
        codigo, saida, gasto, situacao = await executar_visivel(sessao, titulo=f"rodando {rel}", pasta_exec=arquivo.parent, exibir=f"{rel} " + " ".join(args),
                                                                nivel=nivel, segundos=segundos, comando_ps=comando)
        auditar(rel, nivel, codigo, gasto, "oficina_rodar")
        return _resultado(codigo, saida, gasto, situacao, segundos)
    raise ValueError(f"Não sei rodar '{ext}'. Rodo .py (com a guarda), .ps1, .bat/.cmd e abro .html.")
