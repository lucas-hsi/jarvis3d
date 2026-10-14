"""
Diagnóstico do Jarvis: confere se esta máquina está pronta para rodar em alto nível, SEM mostrar nenhum segredo.

Cada checagem devolve {id, titulo, estado: ok|aviso|erro|info, detalhe, dica}. Usado por:
  - scripts\\diagnostico.py (linha de comando),
  - GET /api/diagnostico (a página /diagnostico mostra e acrescenta os testes que só o navegador faz: microfone com
    cancelamento de eco, câmera, alto-falante, WebGL).
Testes que tocam hardware ou rede só rodam quando pedidos: mic=True grava ~3 s do microfone SÓ para medir o nível
(nada é salvo nem enviado); chaves=True valida as chaves de API online (com chamadas gratuitas); rede=True testa os serviços.
"""

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import caminhos


def _ps(comando: str, tempo: int = 15) -> str:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", comando], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=tempo, creationflags=0x08000000)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def _c(id_, titulo, estado, detalhe="", dica=""):
    return {"id": id_, "titulo": titulo, "estado": estado, "detalhe": detalhe, "dica": dica}


# ------------------------------------------------------------------ sistema e hardware

def sistema() -> list[dict]:
    saida = []
    ram = ""
    try:
        import psutil
        ram = f"{round(psutil.virtual_memory().total / 2**30)} GB de RAM, {psutil.cpu_count(logical=False)} núcleos ({psutil.cpu_count()} threads)"
    except Exception:
        pass
    saida.append(_c("so", "Sistema", "ok" if platform.system() == "Windows" else "aviso",
                    f"{platform.system()} {platform.release()} ({platform.version()}); Python {platform.python_version()}; {ram}",
                    "" if platform.system() == "Windows" else "O Jarvis foi feito para Windows."))
    livre = shutil.disk_usage(caminhos.DADOS).free / 2**30
    saida.append(_c("disco", "Espaço livre (pasta de dados)", "ok" if livre > 3 else ("aviso" if livre > 1 else "erro"),
                    f"{livre:.1f} GB livres em {caminhos.DADOS.anchor or caminhos.DADOS}",
                    "Modelos de voz e memória semântica pedem alguns GB." if livre <= 3 else ""))
    saida.append(_c("pastas", "Pastas", "info", f"programa: {caminhos.CODIGO} | dados do usuário: {caminhos.DADOS}"))
    return saida


def placas_de_video() -> list[dict]:
    saida = []
    txt = _ps("Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + '|' + [math]::Round($_.AdapterRAM/1MB) + '|' + $_.DriverVersion }")
    placas = [l.split("|") for l in txt.splitlines() if "|" in l]
    for nome, vram, drv in placas:
        marca = "NVIDIA" if "nvidia" in nome.lower() else ("AMD" if ("amd" in nome.lower() or "radeon" in nome.lower()) else ("Intel" if "intel" in nome.lower() else ""))
        saida.append(_c("gpu_" + marca.lower(), f"Placa de vídeo: {nome}", "info", f"driver {drv}; memória dedicada reportada {vram} MB"))
    if not placas:
        saida.append(_c("gpu", "Placas de vídeo", "aviso", "não consegui listar", "Rode no Windows com PowerShell disponível."))
    cuda = ""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=10, creationflags=0x08000000)
        cuda = r.stdout.strip()
        cab = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=10, creationflags=0x08000000).stdout
        import re
        achou = re.search(r"CUDA Version:\s*([0-9.]+)", cab)
        versao = achou.group(1) if achou else "?"
        saida.append(_c("cuda", "NVIDIA / CUDA", "ok", f"{cuda}; CUDA {versao}",
                        "A voz (Whisper) pode usar esta placa para ficar mais rápida."))
    except Exception:
        saida.append(_c("cuda", "NVIDIA / CUDA", "info", "nvidia-smi não encontrado (sem placa NVIDIA ou sem driver)",
                        "Sem NVIDIA o reconhecimento de voz roda na CPU; funciona, só é mais lento."))
    return saida


# ------------------------------------------------------------------ áudio e câmera

def audio(medir_microfone: bool = False) -> list[dict]:
    saida = []
    try:
        import sounddevice as sd
        dispositivos = sd.query_devices()
        padrao = sd.default.device
        entradas = [(i, d) for i, d in enumerate(dispositivos) if d["max_input_channels"] > 0 and sd.query_hostapis(d["hostapi"])["name"] == "Windows WASAPI"]
        saidas = [(i, d) for i, d in enumerate(dispositivos) if d["max_output_channels"] > 0 and sd.query_hostapis(d["hostapi"])["name"] == "Windows WASAPI"]
        ent_padrao = dispositivos[padrao[0]]["name"] if padrao[0] is not None and padrao[0] >= 0 else "(nenhum)"
        sai_padrao = dispositivos[padrao[1]]["name"] if padrao[1] is not None and padrao[1] >= 0 else "(nenhum)"
        saida.append(_c("mic_lista", "Microfones", "ok" if entradas else "erro",
                        f"padrão: {ent_padrao}; encontrados: {', '.join(d['name'][:40] for _, d in entradas) or 'nenhum'}",
                        "" if entradas else "Conecte um microfone e confira Configurações > Sistema > Som."))
        saida.append(_c("saida_lista", "Alto-falantes", "ok" if saidas else "erro",
                        f"padrão: {sai_padrao}; encontrados: {', '.join(d['name'][:40] for _, d in saidas) or 'nenhum'}"))
        if medir_microfone and entradas:
            import numpy as np
            taxa = 16000
            seg = 3.0
            print("  (teste do microfone: FALE normalmente por 3 segundos...)", file=sys.stderr, flush=True)
            gravacao = sd.rec(int(seg * taxa), samplerate=taxa, channels=1, dtype="float32")
            sd.wait()
            x = gravacao[:, 0]
            janelas = x[: len(x) // 800 * 800].reshape(-1, 800)                 # 50 ms
            rms = np.sqrt(np.mean(janelas ** 2, axis=1)) + 1e-9
            db = 20 * np.log10(rms)
            ruido, voz = float(np.percentile(db, 15)), float(np.percentile(db, 95))
            pico = float(np.max(np.abs(x)))
            texto = f"ruído de fundo {ruido:.0f} dBFS; trecho mais forte {voz:.0f} dBFS; pico {pico:.2f}"
            if pico < 0.0005:
                saida.append(_c("mic_nivel", "Nível do microfone (3 s)", "erro", f"silêncio total ({texto})",
                                "Microfone mudo ou bloqueado. Veja Privacidade > Microfone e a tecla de mudo do notebook."))
            elif pico > 0.98:
                saida.append(_c("mic_nivel", "Nível do microfone (3 s)", "aviso", f"{texto} (estourando)", "Diminua o ganho do microfone."))
            elif voz - ruido < 12:
                saida.append(_c("mic_nivel", "Nível do microfone (3 s)", "aviso", f"{texto}: não detectei fala acima do ruído",
                                "Fale durante os 3 segundos do teste. Se falou e continua assim, aumente o ganho do microfone no Windows."))
            else:
                saida.append(_c("mic_nivel", "Nível do microfone (3 s)", "ok", f"{texto}: sua voz foi captada (nada foi salvo nem enviado)"))
    except Exception as e:
        saida.append(_c("audio", "Áudio", "erro", f"{type(e).__name__}: {str(e)[:120]}", "Instale o requirements.txt (sounddevice)."))
    return saida


def privacidade() -> list[dict]:
    """Permissões de microfone/câmera do Windows para apps de área de trabalho (causa comum de 'mic mudo')."""
    saida = []
    for chave, nome in (("microphone", "Microfone"), ("webcam", "Câmera")):
        base = fr"HKCU:\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\{chave}"
        geral = _ps(f"(Get-ItemProperty '{base}' -ErrorAction SilentlyContinue).Value")
        desktop = _ps(f"(Get-ItemProperty '{base}\\NonPackaged' -ErrorAction SilentlyContinue).Value")
        if geral.lower() == "deny":
            saida.append(_c("priv_" + chave, f"Privacidade: {nome}", "erro", "acesso NEGADO nas configurações do Windows",
                            f"Configurações > Privacidade e segurança > {nome}: ative 'Acesso ao {nome.lower()}' e 'Permitir que aplicativos da área de trabalho acessem'."))
        elif desktop.lower() == "deny":
            saida.append(_c("priv_" + chave, f"Privacidade: {nome}", "erro", "apps de área de trabalho NEGADOS",
                            f"Ative 'Permitir que aplicativos da área de trabalho acessem seu {nome.lower()}'."))
        else:
            saida.append(_c("priv_" + chave, f"Privacidade: {nome}", "ok", f"liberado (geral: {geral or 'padrão'}; desktop: {desktop or 'padrão'})"))
    return saida


def cameras() -> list[dict]:
    txt = _ps("Get-PnpDevice -Class Camera,Image -PresentOnly -ErrorAction SilentlyContinue | ForEach-Object { $_.FriendlyName + '|' + $_.Status }")
    itens = [l.split("|") for l in txt.splitlines() if "|" in l]
    if not itens:
        return [_c("camera", "Câmera", "aviso", "nenhuma câmera encontrada", "O modo gravação e 'olhar minha roupa' precisam de webcam.")]
    return [_c("camera", "Câmera", "ok" if all(s.strip() == "OK" for _, s in itens) else "aviso",
               "; ".join(f"{n} ({s.strip()})" for n, s in itens), "A prévia ao vivo é testada na página /diagnostico.")]


# ------------------------------------------------------------------ programa: config, chaves, modelos, navegador

def _config() -> dict:
    try:
        return json.loads(caminhos.arquivo_config().read_text(encoding="utf-8"))
    except Exception:
        return {}


def configuracao(validar_chaves: bool = False) -> list[dict]:
    cfg = _config()
    saida = []
    tem = lambda k: bool(str(cfg.get(k) or os.environ.get(k.upper(), "")).strip()) and not str(cfg.get(k, "")).startswith("COLE")  # noqa: E731
    saida.append(_c("cfg", "Arquivo de configuração", "ok" if cfg else "erro", str(caminhos.arquivo_config()),
                    "" if cfg else "Falta o config.json (o Jarvis cria um ao abrir pela primeira vez)."))
    saida.append(_c("chave_anthropic", "Chave da Anthropic", "ok" if tem("anthropic_api_key") else "erro",
                    "configurada" if tem("anthropic_api_key") else "ausente",
                    "" if tem("anthropic_api_key") else "Crie em console.anthropic.com e cole em config.json (nunca no chat)."))
    saida.append(_c("chave_eleven", "Chave da ElevenLabs (voz)", "ok" if tem("elevenlabs_api_key") else "info",
                    "configurada" if tem("elevenlabs_api_key") else "ausente: usa a voz do Windows/navegador", ""))
    if validar_chaves:
        import httpx
        if tem("anthropic_api_key"):
            try:
                r = httpx.post("https://api.anthropic.com/v1/messages/count_tokens", timeout=15,
                               headers={"x-api-key": cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY", ""), "anthropic-version": "2023-06-01"},
                               json={"model": cfg.get("modelo", "claude-haiku-5-5"), "messages": [{"role": "user", "content": "oi"}]})
                saida.append(_c("chave_anthropic_ok", "Chave da Anthropic (teste online, gratuito)", "ok" if r.status_code == 200 else "erro",
                                f"HTTP {r.status_code}", "" if r.status_code == 200 else "Chave recusada ou sem permissão para o modelo."))
            except Exception as e:
                saida.append(_c("chave_anthropic_ok", "Chave da Anthropic (teste online)", "aviso", f"sem resposta: {type(e).__name__}"))
        if tem("elevenlabs_api_key"):
            try:
                r = httpx.get("https://api.elevenlabs.io/v1/user/subscription", timeout=15, headers={"xi-api-key": cfg.get("elevenlabs_api_key", "")})
                if r.status_code == 200:
                    d = r.json()
                    saida.append(_c("chave_eleven_ok", "Chave da ElevenLabs (teste online)", "ok",
                                    f"plano {d.get('tier')}, {d.get('character_count')}/{d.get('character_limit')} caracteres usados"))
                else:
                    saida.append(_c("chave_eleven_ok", "Chave da ElevenLabs (teste online)", "erro", f"HTTP {r.status_code}"))
            except Exception as e:
                saida.append(_c("chave_eleven_ok", "Chave da ElevenLabs (teste online)", "aviso", f"sem resposta: {type(e).__name__}"))
    cofre = str(cfg.get("cofre_obsidian") or "")
    saida.append(_c("cofre", "Cofre do Obsidian", "ok" if cofre and Path(cofre).is_dir() else "info",
                    cofre if cofre else "não configurado (opcional)", "" if not cofre or Path(cofre).is_dir() else "A pasta do config não existe."))
    return saida


def modelos_e_motores() -> list[dict]:
    saida = []
    pasta = caminhos.DADOS / "memoria" / "modelos"
    achou = pasta.exists() and any(pasta.rglob("*.onnx"))
    saida.append(_c("modelo_embeddings", "Modelo de memória semântica", "ok" if achou else "info",
                    "baixado" if achou else "não baixado: a memória usa só busca por palavras",
                    "" if achou else "Rode scripts\\baixar_modelo_embeddings.py (~220 MB)."))
    for mod, rotulo, dica in (("faster_whisper", "Reconhecimento de voz próprio (faster-whisper)", "Necessário para o app sem Chrome."),
                              ("uiautomation", "Controle do Windows (UI Automation)", "uv pip install uiautomation"),
                              ("fastembed", "Embeddings (fastembed)", "uv pip install fastembed")):
        try:
            __import__(mod)
            saida.append(_c("lib_" + mod, rotulo, "ok", "instalado"))
        except Exception:
            saida.append(_c("lib_" + mod, rotulo, "info" if mod == "faster_whisper" else "aviso", "não instalado", dica))
    chrome = next((p for p in (os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                               os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                               os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
                               os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe")) if os.path.exists(p)), None)
    saida.append(_c("navegador", "Chrome/Edge (navegador do Jarvis e janela atual)", "ok" if chrome else "aviso", chrome or "não encontrado",
                    "" if chrome else "O controle de páginas usa o Chrome ou o Edge instalados."))
    webview = _ps(r"(Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}' -ErrorAction SilentlyContinue).pv")
    saida.append(_c("webview2", "WebView2 (runtime do Edge)", "ok" if webview else "info", webview or "não encontrado", ""))
    return saida


def rede_e_portas(porta: int, testar_rede: bool = False) -> list[dict]:
    saida = []
    with socket.socket() as s:
        s.settimeout(0.3)
        em_uso = s.connect_ex(("127.0.0.1", porta)) == 0
    saida.append(_c("porta", f"Porta local {porta}", "ok", "em uso (provavelmente o próprio Jarvis)" if em_uso else "livre"))
    if testar_rede:
        import httpx
        for nome, url in (("Anthropic", "https://api.anthropic.com"), ("ElevenLabs", "https://api.elevenlabs.io"),
                          ("Hugging Face (modelos)", "https://huggingface.co"), ("Google", "https://www.googleapis.com")):
            t0 = time.perf_counter()
            try:
                r = httpx.head(url, timeout=8, follow_redirects=True)
                ms = round((time.perf_counter() - t0) * 1000)
                saida.append(_c("rede_" + nome.split()[0].lower(), f"Rede: {nome}", "ok" if r.status_code < 500 else "aviso", f"HTTP {r.status_code} em {ms} ms",
                                "O servidor está instável agora; tente de novo mais tarde." if r.status_code >= 500 else ""))
            except Exception as e:
                saida.append(_c("rede_" + nome.split()[0].lower(), f"Rede: {nome}", "aviso", f"sem resposta ({type(e).__name__})"))
    return saida


def rodar(porta: int = 8340, mic: bool = False, chaves: bool = False, rede: bool = False) -> list[dict]:
    return (sistema() + placas_de_video() + audio(mic) + privacidade() + cameras() + configuracao(chaves) + modelos_e_motores() + rede_e_portas(porta, rede))


def formatar(resultados: list[dict]) -> str:
    simbolo = {"ok": "[ OK ]", "aviso": "[AVISO]", "erro": "[ERRO ]", "info": "[ info]"}
    linhas = []
    for r in resultados:
        linhas.append(f"{simbolo.get(r['estado'], '[  ? ]')} {r['titulo']}" + (f": {r['detalhe']}" if r["detalhe"] else ""))
        if r["dica"] and r["estado"] in ("aviso", "erro", "info"):
            linhas.append(f"         -> {r['dica']}")
    n = {e: sum(1 for r in resultados if r["estado"] == e) for e in ("ok", "aviso", "erro")}
    linhas.append(f"\nResumo: {n['ok']} ok, {n['aviso']} avisos, {n['erro']} erros.")
    return "\n".join(linhas)
