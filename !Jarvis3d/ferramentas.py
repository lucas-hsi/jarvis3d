"""
Ferramentas que o Jarvis pode usar.

Regras de segurança:
- Sites: só http/https (nada de file://, que leria arquivos do PC).
- Programas: só os listados em "programas" no config.json; o modelo escolhe
  um nome da lista, nunca um comando.
- Cofre: somente leitura, preso à pasta do cofre (ver cofre.py).
- Arquivos e mouse/teclado ficam em pc.py, com confirmação do usuário imposta pelo código.
- Terminal e Oficina (terminal.py, oficina.py) também passam por pc.py, com a política de risco do seguranca_cmd.py.
- Não há ferramenta de apagar arquivos de vez fora da Oficina.
"""

import asyncio
import base64
import io
import os
import re
import shutil
import subprocess
import webbrowser
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import httpx
from PIL import ImageGrab

import cofre
import pc
import windows_ctl

LIMITE_TEXTO = 6000

_playwright = None
_navegador = None
_contexto = None
_pagina = None
_trava_navegador = asyncio.Lock()


def definicoes(programas: dict, tem_cofre: bool) -> list[dict]:
    """Ferramentas no formato da API do Claude."""
    ferramentas = [
        {
            "name": "pesquisar_web",
            "description": "Pesquisa na internet (rápido, sem abrir janela; as páginas aparecem em miniatura num canto da tela do Jarvis), lê o primeiro resultado e devolve o texto da página mais os outros resultados. Use para qualquer pergunta sobre fatos atuais, preços, pessoas, empresas ou quando pedirem para pesquisar/googlar.",
            "input_schema": {
                "type": "object",
                "properties": {"consulta": {"type": "string", "description": "O que pesquisar."}},
                "required": ["consulta"],
            },
        },
        {
            "name": "ler_pagina",
            "description": "Abre uma URL no navegador visível e devolve o texto principal da página.",
            "input_schema": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "URL completa, com https://"}},
                "required": ["url"],
            },
        },
        {
            "name": "abrir_site",
            "description": "Abre uma URL no navegador padrão do usuário, para ele usar. Não devolve conteúdo.",
            "input_schema": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "URL completa, com https://"}},
                "required": ["url"],
            },
        },
        {
            "name": "ver_tela",
            "description": "Tira um print da tela do usuário e devolve a imagem para você analisar. Use quando ele perguntar o que tem na tela ou pedir ajuda com algo que está vendo.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "noticias",
            "description": "Busca as manchetes atuais do Google Notícias Brasil. Sem tema traz as principais do dia.",
            "input_schema": {
                "type": "object",
                "properties": {"tema": {"type": "string", "description": "Tema opcional, ex.: 'inteligência artificial'."}},
            },
        },
    ]
    if programas:
        ferramentas.append({
            "name": "abrir_programa",
            "description": "Abre um programa do computador do usuário. Os da lista (" + ", ".join(sorted(programas)) + ") abrem direto; qualquer outro "
                           "aplicativo INSTALADO (Menu Iniciar) abre pelo nome, sem inventar caminhos nem comandos.",
            "input_schema": {
                "type": "object",
                "properties": {"programa": {"type": "string", "description": "nome do programa, como o usuário falou"}},
                "required": ["programa"],
            },
        })
    if tem_cofre:
        ferramentas += [
            {
                "name": "consultar_cofre",
                "description": "Procura nas notas do Obsidian do usuário (o segundo cérebro com o mapa dos projetos dele, pendências, ideias e aprendizados). Use antes de responder perguntas sobre os projetos dele.",
                "input_schema": {
                    "type": "object",
                    "properties": {"busca": {"type": "string", "description": "Palavras-chave."}},
                    "required": ["busca"],
                },
            },
            {
                "name": "ler_nota",
                "description": "Lê uma nota inteira do Obsidian pelo nome (ex.: 'Meu Projeto', 'Meu Projeto - Riscos e pendências').",
                "input_schema": {
                    "type": "object",
                    "properties": {"nota": {"type": "string"}},
                    "required": ["nota"],
                },
            },
        ]
    return ferramentas + pc.definicoes()


def descrever(nome: str, entrada: dict) -> tuple[str, str]:
    """Rótulo curto para o painel de atividade: (tipo, detalhe)."""
    detalhe = entrada.get("consulta") or entrada.get("url") or entrada.get("tema") \
        or entrada.get("busca") or entrada.get("nota") or entrada.get("programa") or entrada.get("caminho") or entrada.get("arquivo") or entrada.get("comando")         or entrada.get("pasta") or entrada.get("pasta_origem") or entrada.get("pasta_pai") or entrada.get("titulo")         or entrada.get("objetivo") or entrada.get("acao") or entrada.get("combinacao") or entrada.get("comando") or entrada.get("texto") or ""
    rotulos = {
        "pesquisar_web": "PESQUISA", "ler_pagina": "LEITURA", "abrir_site": "ABRINDO",
        "ver_tela": "VISÃO", "noticias": "NOTÍCIAS", "abrir_programa": "PROGRAMA",
        "consultar_cofre": "COFRE", "ler_nota": "COFRE", "habilitar_ferramentas": "MODO", "briefing": "BRIEFING", **pc.ROTULOS,
    }
    return rotulos.get(nome, nome.upper()), str(detalhe)[:80]


async def executar(nome: str, entrada, config: dict, sessao=None) -> tuple[list | str, bool]:
    """Roda a ferramenta. Devolve (conteúdo do tool_result, deu_erro)."""
    if not isinstance(entrada, dict):
        return "Entrada inválida.", True
    try:
        if nome == "pesquisar_web":
            consulta = _texto(entrada, "consulta")
            return await pesquisar_web(consulta), False
        if nome == "ler_pagina":
            return await ler_pagina(_url(entrada)), False
        if nome == "abrir_site":
            url = _url(entrada)
            await asyncio.to_thread(webbrowser.open, url)
            return f"Aberto no navegador: {url}", False
        if nome == "ver_tela":
            return await asyncio.to_thread(ver_tela), False
        if nome == "noticias":
            return await noticias(str(entrada.get("tema") or "").strip()), False
        if nome == "abrir_programa":
            return abrir_programa_verificado(_texto(entrada, "programa"), config.get("programas", {}))[0], False
        if nome == "consultar_cofre":
            import memoria
            achados = await asyncio.to_thread(memoria.instancia().buscar_cofre, _texto(entrada, "busca"), 6, 1)
            if achados:
                return "\n\n".join(f"[{c['caminho']}]\n{' '.join(c['trecho'].split())[:700]}" for c in achados), False
            return await asyncio.to_thread(cofre.buscar, _pasta_cofre(config), _texto(entrada, "busca")), False
        if nome == "ler_nota":
            return await asyncio.to_thread(cofre.ler, _pasta_cofre(config), _texto(entrada, "nota")), False
        if nome in pc.NOMES:
            return await pc.executar(nome, entrada, config, sessao, ver_tela)
        return f"Ferramenta desconhecida: {nome}", True
    except ValueError as e:
        return str(e), True
    except Exception as e:  # a ferramenta falhou; o modelo explica ao usuário
        return f"Falhou: {type(e).__name__}: {e}"[:500], True


def _texto(entrada: dict, campo: str) -> str:
    valor = entrada.get(campo)
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"Faltou o campo '{campo}'.")
    return valor.strip()


def _url(entrada: dict) -> str:
    url = _texto(entrada, "url")
    if re.match(r"^(javascript|data|file|chrome|about|blob|vbscript|view-source|mailto|tel|ftp):", url, re.IGNORECASE):
        raise ValueError("Só abro endereços http ou https.")
    if "://" not in url:
        url = "https://" + url
    partes = urlparse(url)
    if partes.scheme not in ("http", "https") or not partes.netloc:
        raise ValueError("Só abro endereços http ou https.")
    return url


def _pasta_cofre(config: dict) -> Path:
    return Path(config.get("cofre_obsidian", ""))


# ---------------------------------------------------------------- navegador

async def _pagina_escondida():
    """A aba do navegador do Jarvis SEM trazer a janela para a frente (pesquisa/leitura não roubam a tela; o usuário abre pela miniatura)."""
    import navegador
    return await navegador.pagina(mostrar=False)


async def _pagina_visivel():
    """A aba do navegador do Jarvis (Chrome dedicado, mesmo usado para YouTube e para operar páginas)."""
    import navegador
    return await navegador.pagina(mostrar=True)


_TEXTO_PRINCIPAL = """
() => {
  for (const sel of ['main', 'article', '[role="main"]', '#content', '.content', 'body']) {
    const el = document.querySelector(sel);
    if (el && el.innerText.trim().length > 200) return el.innerText.trim();
  }
  return document.body ? document.body.innerText.trim() : '';
}
"""

_RESULTADOS_DDG = """
() => [...document.querySelectorAll('[data-testid="result"]')].slice(0, 6).map(r => {
  const a = r.querySelector('[data-testid="result-title-a"]');
  const s = r.querySelector('[data-result="snippet"]');
  return { titulo: a ? a.innerText : '', url: a ? a.href : '', resumo: s ? s.innerText : '' };
}).filter(r => r.url)
"""


async def pesquisar_web(consulta: str) -> str:
    """Busca por HTTP (DuckDuckGo HTML) e lê o 1º resultado legível, sem abrir o Chrome na frente do usuário (~1-3 s em vez de ~8 s).
    Se a busca por HTTP não trouxer nada (bloqueio), cai para o navegador do Jarvis, minimizado."""
    import httpx
    import pesquisa
    try:
        async with httpx.AsyncClient(headers=pesquisa.CAB, timeout=httpx.Timeout(10.0, connect=5.0), follow_redirects=True) as cli:
            resultados = await pesquisa._buscar_ddg(cli, consulta)
            primeiro = None
            if resultados:
                # lê os 5 primeiros em paralelo e fica com o PRIMEIRO que responder legível (um site lento não segura a resposta)
                tarefas = [asyncio.create_task(pesquisa._ler(cli, r)) for r in resultados[:5]]
                try:
                    for prox in asyncio.as_completed(tarefas, timeout=3.0):
                        p = await prox
                        if p:
                            primeiro = p
                            break
                except asyncio.TimeoutError:
                    pass
                finally:
                    for t in tarefas:
                        t.cancel()
    except Exception:
        resultados, primeiro = [], None
    if not resultados:
        return await _pesquisar_web_navegador(consulta)
    lista = "\n".join(f"- {r['titulo']} ({r['url']}): {r['resumo']}" for r in resultados)
    texto = (f"\n\nTexto do primeiro resultado ({primeiro['titulo']}):\n{primeiro['texto'][:LIMITE_TEXTO]}" if primeiro
             else "\n\n(Não consegui ler o texto das páginas; use os resumos acima ou ler_pagina.)")
    return f"Resultados para '{consulta}':\n{lista}{texto}"


async def _pesquisar_web_navegador(consulta: str) -> str:
    async with _trava_navegador:
        pagina = await _pagina_escondida()
        await pagina.goto(f"https://duckduckgo.com/?q={quote_plus(consulta)}&kl=br-pt", timeout=20000)
        try:
            await pagina.wait_for_selector('[data-testid="result-title-a"]', timeout=8000)
        except Exception:
            return f"A pesquisa por '{consulta}' não trouxe resultados."
        resultados = await pagina.evaluate(_RESULTADOS_DDG)
        lista = "\n".join(f"- {r['titulo']} ({r['url']}): {r['resumo']}" for r in resultados)

        primeiro = ""
        if resultados:
            try:
                await pagina.goto(resultados[0]["url"], timeout=15000, wait_until="domcontentloaded")
                await pagina.wait_for_timeout(1500)
                texto = await pagina.evaluate(_TEXTO_PRINCIPAL)
                primeiro = f"\n\nTexto do primeiro resultado ({await pagina.title()}):\n{texto[:LIMITE_TEXTO]}"
            except Exception as e:
                primeiro = f"\n\n(Não consegui abrir o primeiro resultado: {e})"
        return f"Resultados para '{consulta}':\n{lista}{primeiro}"


async def ler_pagina(url: str) -> str:
    """Lê por HTTP (sem abrir janela); página que precisa de JavaScript cai para o navegador do Jarvis, minimizado."""
    import httpx
    import pesquisa
    try:
        async with httpx.AsyncClient(headers=pesquisa.CAB, timeout=httpx.Timeout(12.0, connect=5.0), follow_redirects=True) as cli:
            lida = await pesquisa._ler(cli, {"url": url, "titulo": url})
        if lida:
            return f"{lida['titulo']}\n{url}\n\n{lida['texto'][:LIMITE_TEXTO]}"
    except Exception:
        pass
    async with _trava_navegador:
        pagina = await _pagina_escondida()
        await pagina.goto(url, timeout=20000, wait_until="domcontentloaded")
        await pagina.wait_for_timeout(1500)
        texto = await pagina.evaluate(_TEXTO_PRINCIPAL)
        return f"{await pagina.title()}\n{url}\n\n{texto[:LIMITE_TEXTO]}"


async def fechar_navegador():
    import navegador
    await navegador.desconectar()


# ---------------------------------------------------------------- tela

def ver_tela(legenda: str = "Print da tela do usuário agora.") -> list:
    """Print da tela reduzido (lado maior até 1568 px) em JPEG, como bloco de imagem."""
    img = ImageGrab.grab().convert("RGB")
    windows_ctl.TELA["orig"] = img.size
    img.thumbnail((1568, 1568))
    windows_ctl.TELA["env"] = img.size
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    dados = base64.standard_b64encode(buf.getvalue()).decode()
    return [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": dados}},
        {"type": "text", "text": f"{legenda} Imagem de {img.size[0]}x{img.size[1]} pixels; coordenadas de clique usam esta imagem."},
    ]


# ---------------------------------------------------------------- notícias

async def manchetes(tema: str = "", n: int = 14) -> list[str]:
    """Manchetes do Google Notícias Brasil como lista curta ('Título — Fonte'), para o letreiro da tela."""
    base = "https://news.google.com/rss"
    sufixo = "hl=pt-BR&gl=BR&ceid=BR:pt-419"
    url = f"{base}/search?q={quote_plus(tema)}&{sufixo}" if tema else f"{base}?{sufixo}"
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as http:
        resposta = await http.get(url, headers={"User-Agent": "Mozilla/5.0"})
    resposta.raise_for_status()
    saida = []
    for item in ET.fromstring(resposta.content).findall("./channel/item")[:n]:
        titulo = (item.findtext("title", "") or "").rsplit(" - ", 1)[0].strip()
        fonte = (item.findtext("source", "") or "").strip()
        if titulo:
            saida.append(f"{titulo} — {fonte}" if fonte else titulo)
    return saida


async def noticias(tema: str = "") -> str:
    base = "https://news.google.com/rss"
    sufixo = "hl=pt-BR&gl=BR&ceid=BR:pt-419"
    url = f"{base}/search?q={quote_plus(tema)}&{sufixo}" if tema else f"{base}?{sufixo}"
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as http:
        resposta = await http.get(url, headers={"User-Agent": "Mozilla/5.0"})
    resposta.raise_for_status()
    itens = ET.fromstring(resposta.content).findall("./channel/item")[:12]
    linhas = []
    for item in itens:
        titulo = item.findtext("title", "")
        fonte = item.findtext("source", "")
        data = item.findtext("pubDate", "")[:16]
        linhas.append(f"- {titulo} [{fonte}, {data}]")
    if not linhas:
        return "Nenhuma manchete encontrada."
    return f"Manchetes{' sobre ' + tema if tema else ''} (Google Notícias):\n" + "\n".join(linhas)


# ---------------------------------------------------------------- programas

_CATALOGO = {"em": 0.0, "apps": []}


def _sem_acento_min(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn").strip()


def catalogo_de_apps() -> list[dict]:
    """Aplicativos do Menu Iniciar (nome + AppID), lidos pelo próprio Windows e guardados por 10 min. Só o que está instalado."""
    import json
    import time as _t
    if _CATALOGO["apps"] and _t.monotonic() - _CATALOGO["em"] < 600:
        return _CATALOGO["apps"]
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25, creationflags=0x08000000)
        dados = json.loads(r.stdout or "[]")
        if isinstance(dados, dict):
            dados = [dados]
        _CATALOGO["apps"] = [{"nome": d["Name"], "id": d["AppID"]} for d in dados if d.get("Name") and d.get("AppID")]
        _CATALOGO["em"] = _t.monotonic()
    except Exception:
        pass
    return _CATALOGO["apps"]


def achar_app(nome: str, apps: list[dict]) -> dict | None:
    import difflib
    q = _sem_acento_min(nome)
    if not q:
        return None
    nomes = {_sem_acento_min(a["nome"]): a for a in apps}
    if q in nomes:
        return nomes[q]
    contem = [n for n in nomes if q in n or n in q]
    if contem:
        return nomes[min(contem, key=len)]
    parecido = difflib.get_close_matches(q, list(nomes), n=1, cutoff=0.88)
    return nomes[parecido[0]] if parecido else None


# o que aparece no título da janela de programas cujo comando/atalho não tem o mesmo nome (para CONFERIR que abriu de verdade)
ALIAS_JANELA = {"calc": "calculadora", "notepad": "bloco de notas", "msedge": "edge", "explorer": "explorador", "taskmgr": "gerenciador de tarefas",
                "ms-settings": "configuracoes", "chrome": "chrome", "spotify": "spotify", "obsidian": "obsidian"}


def _titulos() -> list[tuple[int, str]]:
    try:
        import windows_ctl
        return windows_ctl.listar_janelas()
    except Exception:
        return []


def abrir_programa_verificado(nome: str, programas: dict, espera_s: float = 5.0) -> tuple[str, str]:
    """Abre o programa e CONFERE pela lista de janelas do Windows. Devolve (texto, estado): 'aberto' (apareceu uma janela), 'ja_aberto'
    (já havia uma e foi trazida para a frente) ou 'sem_janela' (mandei abrir, mas nenhuma janela apareceu ainda; pode demorar)."""
    import time as _t
    chave = _sem_acento_min(nome)
    alvo = programas.get(nome) or next((v for k, v in programas.items() if _sem_acento_min(k) == chave), "")
    pistas = {chave}
    for pedaco in re.split(r"[\s:/\\.]+", _sem_acento_min(str(alvo))):
        if pedaco in ALIAS_JANELA:
            pistas.add(ALIAS_JANELA[pedaco])
    if chave in ALIAS_JANELA:
        pistas.add(ALIAS_JANELA[chave])
    pistas = {p for p in pistas if len(p) >= 3}
    casa = lambda titulo: any(p in _sem_acento_min(titulo) for p in pistas)      # noqa: E731
    lista_antes = _titulos()
    antes = {h for h, _t_ in lista_antes}
    titulos_antes = {t for _h, t in lista_antes}
    ja = next(((h, t) for h, t in _titulos() if casa(t)), None)
    exibido = abrir_programa(nome, programas)
    if ja:
        try:
            import windows_ctl
            windows_ctl.acao_na_janela(ja[1][:30], "focar")
        except Exception:
            pass
        return f"{nome} já estava aberto (janela '{ja[1][:60]}'); trouxe para a frente.", "ja_aberto"
    limite = _t.monotonic() + espera_s
    while _t.monotonic() < limite:
        _t.sleep(0.25)
        agora = _titulos()
        nova = next(((h, t) for h, t in agora if casa(t)), None) or next(((h, t) for h, t in agora if h not in antes and t.strip() and t not in titulos_antes), None)
        if nova:
            return f"{nome} aberto (janela '{nova[1][:60]}').", "aberto"
    return f"Mandei abrir {nome}, mas nenhuma janela apareceu em {espera_s:.0f} s (pode estar demorando ou abriu em segundo plano). Não afirme que abriu; diga que mandou abrir.", "sem_janela"


def abrir_programa(nome: str, programas: dict) -> str:
    alvo = programas.get(nome)
    if alvo is None:
        achado = next((programas[k] for k in programas if _sem_acento_min(k) == _sem_acento_min(nome)), None)
        if achado is not None:
            return abrir_programa(next(k for k in programas if _sem_acento_min(k) == _sem_acento_min(nome)), programas)
        app = achar_app(nome, catalogo_de_apps())
        if app is None:
            raise ValueError(f"Não encontrei '{nome}' entre os programas instalados.")
        subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + app["id"]], close_fds=True)
        return f"{app['nome']} aberto."
    if "://" in alvo or alvo.endswith(":") or os.path.exists(alvo):
        os.startfile(alvo)
    else:
        executavel = shutil.which(alvo)
        if executavel is None:
            raise ValueError(f"Não encontrei o programa '{alvo}' neste computador.")
        subprocess.Popen([executavel], close_fds=True)
    return f"{nome} aberto."
