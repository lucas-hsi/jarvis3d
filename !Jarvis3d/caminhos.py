"""
Onde ficam as coisas do Jarvis: CÓDIGO (arquivos do programa, só leitura) e DADOS (o que é de cada usuário).

  CODIGO  frontend/, personalidade padrão, config.example.json. Em desenvolvimento é a pasta do repositório;
          empacotado (PyInstaller) é a pasta interna do executável.
  DADOS   config.json, ajustes.json, memoria/, segredos/, musica/, desfazer/, vozes-teste/, logs, personalidade.md.
          Sem a variável JARVIS_HOME é IGUAL ao CODIGO (comportamento de sempre, nada muda no C:\\Jarvis atual).
          Instalado como produto, o instalador/Electron define JARVIS_HOME=%APPDATA%\\Jarvis.

Na primeira execução com DADOS vazio, copia os arquivos padrão (config.example.json, personalidade.md) para DADOS,
para o servidor subir mesmo sem configuração (aí avisa que falta a chave) em vez de quebrar.
"""

import os
import shutil
import sys
from pathlib import Path


def _codigo() -> Path:
    if getattr(sys, "frozen", False):                       # PyInstaller
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).parent


CODIGO = _codigo()
DADOS = Path(os.environ["JARVIS_HOME"]).expanduser() if os.environ.get("JARVIS_HOME") else CODIGO


def pasta(*partes: str, criar: bool = False) -> Path:
    p = DADOS.joinpath(*partes)
    if criar:
        p.mkdir(parents=True, exist_ok=True)
    return p


def _copiar_padrao(origem: Path, destino: Path):
    try:
        if not destino.exists() and origem.exists() and origem.resolve() != destino.resolve():
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origem, destino)
    except OSError:
        pass


def _config_inicial(destino: Path):
    """Primeira execução de uma instalação nova: config neutra a partir do exemplo (sem o cofre nem as pastas do Lucas)."""
    import json
    exemplo = CODIGO / "config.example.json"
    if destino.exists() or not exemplo.exists():
        return
    try:
        cfg = json.loads(exemplo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    casa = Path.home()
    cfg["cofre_obsidian"] = ""                                   # o usuário escolhe a pasta do Obsidian, se tiver
    cfg["notas_pendencias"] = []
    cfg["cidade"] = ""
    cfg["pastas_liberadas"] = [str(casa / p).replace("\\", "/") for p in ("Downloads", "Documents", "Desktop")]
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def arquivo_config() -> Path:
    """config.json (chaves e preferências). JARVIS_CONFIG (testes) manda; senão DADOS/config.json, criado se faltar."""
    if os.environ.get("JARVIS_CONFIG"):
        return Path(os.environ["JARVIS_CONFIG"])
    arq = DADOS / "config.json"
    if DADOS != CODIGO:
        _config_inicial(arq)               # instalação nova; em desenvolvimento (DADOS == CODIGO) nada é criado
    return arq


def arquivo_ajustes() -> Path:
    return Path(os.environ.get("JARVIS_AJUSTES") or DADOS / "ajustes.json")


def personalidade() -> Path:
    """personalidade.md editável do usuário; se não houver, copia a padrão do programa."""
    arq = DADOS / "personalidade.md"
    _copiar_padrao(CODIGO / "personalidade.md", arq)
    return arq if arq.exists() else CODIGO / "personalidade.md"
