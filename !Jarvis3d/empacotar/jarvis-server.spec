# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: empacota o servidor Python do Jarvis (sem Python instalado na máquina do usuário).
# Uso (na pasta C:\Jarvis):  .venv\Scripts\python.exe -m PyInstaller empacotar\jarvis-server.spec --noconfirm --distpath dist-server --workpath build-server
# Fica de FORA de propósito: config.json, ajustes.json, segredos\, memoria\, musica\, logs, as bibliotecas CUDA (1,1 GB) e os modelos (baixados na 1ª execução).
from PyInstaller.utils.hooks import collect_all

RAIZ = SPECPATH + "\\.."

datas = [
    (RAIZ + "\\frontend", "frontend"),
    (RAIZ + "\\personalidade.md", "."),
    (RAIZ + "\\config.example.json", "."),
    (RAIZ + "\\icone.ico", "."),
]
binarios, ocultos = [], [
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
    "keyring.backends.Windows", "win32ctypes.core", "comtypes.client",
]
for pacote in ("faster_whisper", "ctranslate2", "onnxruntime", "fastembed", "tokenizers", "uiautomation", "comtypes", "sounddevice",
               "playwright", "certifi", "av", "anthropic", "tiktoken_ext", "openwakeword", "docx", "openpyxl", "pypdf", "lxml", "mcp", "kokoro_onnx", "espeakng_loader", "phonemizer"):
    try:
        d, b, h = collect_all(pacote)
        datas += d; binarios += b; ocultos += h
    except Exception:
        pass

a = Analysis(
    [RAIZ + "\\server.py"],
    pathex=[RAIZ],
    binaries=binarios,
    datas=datas,
    hiddenimports=ocultos,
    excludes=["tkinter", "matplotlib", "pytest", "IPython", "notebook", "torch", "tensorflow", "scipy.tests", "nvidia"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="jarvis-server", console=True, icon=RAIZ + "\\icone.ico", upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="jarvis-server", upx=False)
