"""
Baixa, SOB PEDIDO do usuário (assistente de primeira execução / página /configurar), o que não cabe no instalador:
  whisper    reconhecimento de voz próprio (Hugging Face, ~480 MB)
  whisper_preciso  Whisper large-v3-turbo (~1,6 GB): entende bem melhor; usado sozinho quando baixado (precisa de placa NVIDIA para ser rápido)
  embeddings memória por significado (Hugging Face, ~220 MB, opcional)
  cuda       bibliotecas NVIDIA para o Whisper rodar na placa de vídeo (~1,1 GB, PyPI, opcional; sem elas roda na CPU)
O Jarvis em si nunca baixa nada sozinho: só esta rotina, quando o usuário clica. O CUDA vem com conferência de SHA-256 do PyPI.
"""

import hashlib
import json
import os
import shutil
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

import caminhos

# versões testadas com o ctranslate2 do Jarvis (as mesmas do ambiente de desenvolvimento)
URL_CHAMADO = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/"
CUDA_PACOTES = [("nvidia-cublas-cu12", "12.9.2.10"), ("nvidia-cuda-nvrtc-cu12", "12.9.86"), ("nvidia-cudnn-cu12", "9.27.0.42")]
PROGRESSO = {"item": "", "fase": "", "pct": 0.0, "erro": "", "ocupado": False, "feito": []}
_trava = threading.Lock()


def pasta_cuda() -> Path:
    return caminhos.DADOS / "cuda"


def tem_nvidia() -> bool:
    import subprocess
    try:
        r = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=6, creationflags=0x08000000)
        return r.returncode == 0 and "GPU" in r.stdout
    except Exception:
        return False


def cuda_instalado() -> bool:
    return any(pasta_cuda().glob("*/bin/cublas64_*.dll"))


def estado() -> dict:
    import semantica
    import stt
    return {
        "whisper": stt.modelo_em_disco(stt.MODELO_PADRAO),
        "whisper_preciso": stt.modelo_em_disco(stt.MODELO_PRECISO),
        "chamado": all((stt.pasta_chamado() / a).exists() for a in stt.ARQUIVOS_CHAMADO),
        "vozlocal": __import__("voz_local").disponivel(),
        "embeddings": any((caminhos.DADOS / "memoria" / "modelos").glob("models--*MiniLM*")),
        "nvidia": tem_nvidia(), "cuda": cuda_instalado(),
        "progresso": dict(PROGRESSO),
    }


def _definir(**kw):
    PROGRESSO.update(kw)


def _baixar_arquivo(url: str, destino: Path, sha256: str, rotulo: str, base_pct: float, fatia: float):
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": "Jarvis-instalador"})
    with urllib.request.urlopen(req, timeout=60) as r, open(destino, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        lido = 0
        while True:
            bloco = r.read(1 << 20)
            if not bloco:
                break
            f.write(bloco); h.update(bloco); lido += len(bloco)
            if total:
                _definir(fase=f"{rotulo} ({lido // (1 << 20)} de {total // (1 << 20)} MB)", pct=round(base_pct + fatia * lido / total, 1))
    if h.hexdigest().lower() != sha256.lower():
        destino.unlink(missing_ok=True)
        raise RuntimeError("conferência de integridade (SHA-256) falhou: arquivo corrompido ou adulterado")


def _instalar_cuda():
    pasta_cuda().mkdir(parents=True, exist_ok=True)
    tmp = pasta_cuda() / "_baixando"
    tmp.mkdir(exist_ok=True)
    n = len(CUDA_PACOTES)
    for i, (nome, versao) in enumerate(CUDA_PACOTES):
        with urllib.request.urlopen(f"https://pypi.org/pypi/{nome}/{versao}/json", timeout=30) as r:
            dados = json.load(r)
        roda = next((u for u in dados["urls"] if u["filename"].endswith("win_amd64.whl")), None)
        if roda is None:
            raise RuntimeError(f"{nome} {versao} não tem versão para Windows 64 bits")
        arq = tmp / roda["filename"]
        _baixar_arquivo(roda["url"], arq, roda["digests"]["sha256"], nome, 100 * i / n, 100 / n * 0.9)
        _definir(fase=f"extraindo {nome}")
        alvo = pasta_cuda() / nome
        if alvo.exists():
            shutil.rmtree(alvo)
        with zipfile.ZipFile(arq) as z:
            for m in z.namelist():
                if m.lower().endswith(".dll") and "/bin/" in m.replace("\\", "/"):
                    destino = alvo / "bin" / Path(m).name          # só as DLLs, achatadas em <pacote>\bin
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(m) as src, open(destino, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        arq.unlink(missing_ok=True)
    shutil.rmtree(tmp, ignore_errors=True)


def _instalar_whisper(modelo: str = "", mb: int = 480):
    import stt
    from faster_whisper.utils import download_model
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    destino = stt.pasta_modelos()
    destino.mkdir(parents=True, exist_ok=True)
    parar = threading.Event()
    ja_tinha = sum(f.stat().st_size for f in destino.rglob("*") if f.is_file())     # outro modelo já baixado não conta no progresso

    def acompanhar():                                       # o Hugging Face não dá progresso fácil: mede a pasta crescendo
        while not parar.is_set():
            tam = max(0, sum(f.stat().st_size for f in destino.rglob("*") if f.is_file()) - ja_tinha)
            _definir(fase=f"baixando o Whisper ({tam // (1 << 20)} de ~{mb} MB)", pct=min(97.0, round(tam / (mb * (1 << 20)) * 100, 1)))
            time.sleep(1)
    threading.Thread(target=acompanhar, daemon=True).start()
    try:
        for tentativa in range(1, 5):
            try:
                download_model(modelo or stt.MODELO_PADRAO, cache_dir=str(destino))
                return
            except Exception:
                if tentativa == 4:
                    raise
                time.sleep(10 * tentativa)                  # o Hugging Face às vezes dá 429/500
    finally:
        parar.set()


def _instalar_embeddings():
    import semantica
    from fastembed import TextEmbedding
    destino = caminhos.DADOS / "memoria" / "modelos"
    destino.mkdir(parents=True, exist_ok=True)
    _definir(fase="baixando o modelo de memória por significado (~220 MB)", pct=30.0)
    TextEmbedding(model_name=semantica.MODELO_PADRAO, cache_dir=str(destino))


def _instalar_chamado():
    import stt
    pasta = stt.pasta_chamado()
    pasta.mkdir(parents=True, exist_ok=True)
    for i, nome in enumerate(stt.ARQUIVOS_CHAMADO):
        _definir(fase=f"baixando {nome}", pct=round(100 * i / len(stt.ARQUIVOS_CHAMADO), 1))
        req = urllib.request.Request(URL_CHAMADO + nome, headers={"User-Agent": "Jarvis-instalador"})
        with urllib.request.urlopen(req, timeout=60) as r, open(pasta / (nome + ".parte"), "wb") as f:
            shutil.copyfileobj(r, f)
        (pasta / (nome + ".parte")).replace(pasta / nome)


def _instalar_vozlocal():
    import voz_local
    pasta = voz_local.pasta()
    pasta.mkdir(parents=True, exist_ok=True)
    for i, nome in enumerate(voz_local.ARQUIVOS):
        alvo = pasta / nome
        if alvo.exists():
            continue
        req = urllib.request.Request(voz_local.URL + nome, headers={"User-Agent": "Jarvis-instalador"})
        with urllib.request.urlopen(req, timeout=60) as r, open(str(alvo) + ".parte", "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            lido = 0
            while True:
                bloco = r.read(1 << 20)
                if not bloco:
                    break
                f.write(bloco)
                lido += len(bloco)
                _definir(fase=f"baixando {nome} ({lido // (1 << 20)} de {total // (1 << 20)} MB)", pct=round(50 * i + (50 * lido / total if total else 0), 1))
        (pasta / (nome + ".parte")).replace(alvo)


def baixar(item: str) -> bool:
    """Começa o download em segundo plano. Devolve False se já há um em andamento ou o item é desconhecido."""
    rotinas = {"vozlocal": _instalar_vozlocal, "chamado": _instalar_chamado, "whisper": _instalar_whisper, "whisper_preciso": lambda: _instalar_whisper(__import__("stt").MODELO_PRECISO, 1550), "embeddings": _instalar_embeddings, "cuda": _instalar_cuda}
    if item not in rotinas or not _trava.acquire(blocking=False):
        return False

    def tarefa():
        try:
            _definir(item=item, fase="começando", pct=0.0, erro="", ocupado=True)
            rotinas[item]()
            _definir(fase="pronto", pct=100.0)
            PROGRESSO["feito"] = sorted(set(PROGRESSO.get("feito", [])) | {item})
        except Exception as e:
            _definir(erro=f"{type(e).__name__}: {str(e)[:160]}", fase="falhou")
        finally:
            _definir(ocupado=False)
            _trava.release()
    threading.Thread(target=tarefa, daemon=True, name="instalador").start()
    return True
