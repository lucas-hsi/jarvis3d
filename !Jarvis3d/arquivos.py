"""
Organização de arquivos, com regras de segurança.

- Só mexe dentro das pastas listadas em "pastas_liberadas" do config.json.
- Nunca apaga: "lixo" é mover para _Jarvis-lixo dentro da própria pasta.
- Toda movimentação vai para um registro em desfazer\\ e pode ser revertida.
- Este módulo só EXECUTA. Quem pede a confirmação do usuário é ferramentas.py.
"""

import json
import shutil
import time
import unicodedata
from pathlib import Path

import caminhos

BASE = caminhos.CODIGO
PASTA_DESFAZER = caminhos.DADOS / "desfazer"
LIXO = "_Jarvis-lixo"

CATEGORIAS = {
    "Imagens": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".svg", ".tiff", ".ico"},
    "Vídeos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv"},
    "Áudios": {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma"},
    "PDFs": {".pdf"},
    "Documentos": {".doc", ".docx", ".txt", ".rtf", ".odt", ".md", ".ppt", ".pptx", ".odp"},
    "Planilhas": {".xls", ".xlsx", ".csv", ".ods"},
    "Compactados": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "Instaladores": {".exe", ".msi", ".msix", ".apk", ".iso"},
    "Código": {".py", ".js", ".ts", ".json", ".html", ".css", ".sql", ".ipynb", ".sh", ".bat", ".ps1"},
}
PASTAS_DE_CATEGORIA = set(CATEGORIAS) | {"Outros", LIXO}
# nunca mexe: atalhos, downloads em andamento, arquivos de sistema
IGNORAR_EXT = {".lnk", ".url", ".tmp", ".crdownload", ".part", ".partial", ".ini", ".sys", ".dll"}
RECENTE_S = 600  # arquivos mexidos nos últimos 10 min podem estar em uso


class ErroArquivos(ValueError):
    pass


def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def raizes(config: dict) -> list[Path]:
    saida = []
    for p in config.get("pastas_liberadas", []):
        try:
            c = Path(p).resolve()
            if c.is_dir():
                saida.append(c)
        except OSError:
            continue
    return saida


def resolver(entrada: str, rs: list[Path], *, permitir_raiz: bool = True) -> Path:
    """Aceita caminho completo ou apelido ('downloads', 'área de trabalho'). Garante estar numa pasta liberada."""
    if not rs:
        raise ErroArquivos("Nenhuma pasta liberada no config.json (pastas_liberadas).")
    texto = entrada.strip().strip('"')
    apelidos = {"desktop": "area de trabalho", "documents": "documentos", "documento": "documentos", "download": "downloads"}
    chave = apelidos.get(_sem_acento(texto), _sem_acento(texto))
    for r in rs:
        if _sem_acento(r.name) == chave:
            return r
    caminho = Path(texto)
    if not caminho.is_absolute():
        # nome relativo: procura dentro das pastas liberadas
        for r in rs:
            if (r / texto).exists():
                caminho = r / texto
                break
    try:
        alvo = caminho.resolve()
    except OSError:
        raise ErroArquivos(f"Caminho inválido: {entrada}")
    for r in rs:
        if alvo == r:
            if permitir_raiz:
                return alvo
            raise ErroArquivos("Não mexo na pasta raiz em si, só no que está dentro dela.")
        if r in alvo.parents:
            return alvo
    raise ErroArquivos(f"'{entrada}' está fora das pastas que o Lucas liberou.")


def _raiz_de(caminho: Path, rs: list[Path]) -> Path:
    for r in rs:
        if caminho == r or r in caminho.parents:
            return r
    raise ErroArquivos("Fora das pastas liberadas.")


def _livre(destino: Path) -> Path:
    if not destino.exists():
        return destino
    n = 2
    while True:
        novo = destino.with_name(f"{destino.stem} ({n}){destino.suffix}")
        if not novo.exists():
            return novo
        n += 1


def _tamanho(b: int) -> str:
    for unidade in ("B", "KB", "MB", "GB"):
        if b < 1024 or unidade == "GB":
            return f"{b:.0f} {unidade}" if unidade == "B" else f"{b:.1f} {unidade}"
        b /= 1024


# ------------------------------------------------------------------ leitura

def listar(pasta: Path, limite: int = 60) -> str:
    itens = sorted(pasta.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    linhas = []
    for p in itens[:limite]:
        try:
            linhas.append(f"[pasta] {p.name}" if p.is_dir() else f"{p.name} ({_tamanho(p.stat().st_size)})")
        except OSError:
            continue
    extra = f"\n... e mais {len(itens) - limite} itens" if len(itens) > limite else ""
    return f"{pasta} — {len(itens)} itens:\n" + "\n".join(linhas) + extra


# ------------------------------------------------------------------ planos (nada é movido aqui)

def categoria_de(arquivo: Path) -> str:
    ext = arquivo.suffix.lower()
    return next((c for c, exts in CATEGORIAS.items() if ext in exts), "Outros")


def plano_organizar(pasta: Path) -> dict:
    """Arquivos soltos na pasta (sem entrar nas subpastas) → subpasta por tipo."""
    mover, ignorados, agora = [], 0, time.time()
    for p in pasta.iterdir():
        try:
            if not p.is_file() or p.name.startswith(".") or p.suffix.lower() in IGNORAR_EXT:
                ignorados += p.is_file()
                continue
            if agora - p.stat().st_mtime < RECENTE_S:
                ignorados += 1
                continue
        except OSError:
            continue
        mover.append((p, pasta / categoria_de(p) / p.name))
    resumo: dict[str, int] = {}
    for _, d in mover:
        resumo[d.parent.name] = resumo.get(d.parent.name, 0) + 1
    return {"mover": mover, "resumo": resumo, "ignorados": ignorados}


def plano_mover(origens: list[Path], destino: Path) -> list[tuple[Path, Path]]:
    if destino.exists() and not destino.is_dir():
        raise ErroArquivos("O destino precisa ser uma pasta.")
    saida = []
    for o in origens:
        if not o.exists():
            raise ErroArquivos(f"Não existe: {o.name}")
        if o == destino or o in destino.parents:
            raise ErroArquivos("Não dá para mover uma pasta para dentro dela mesma.")
        saida.append((o, destino / o.name))
    return saida


def plano_lixo(origens: list[Path], rs: list[Path]) -> list[tuple[Path, Path]]:
    saida = []
    for o in origens:
        if not o.exists():
            raise ErroArquivos(f"Não existe: {o.name}")
        if o.name == LIXO or LIXO in o.parts:
            raise ErroArquivos("Isso já está no lixo do Jarvis.")
        saida.append((o, _raiz_de(o, rs) / LIXO / o.name))
    return saida


# ------------------------------------------------------------------ execução

def executar(movimentos: list[tuple[Path, Path]], rs: list[Path], rotulo: str) -> dict:
    """Move de verdade e grava o registro para desfazer. Revalida tudo na hora de agir."""
    feitos, falhas = [], []
    for origem, destino in movimentos:
        try:
            _raiz_de(origem.resolve(), rs)
            _raiz_de(destino.parent.resolve() if destino.parent.exists() else destino.parent, rs)
            if not origem.exists():
                raise ErroArquivos("sumiu")
            destino.parent.mkdir(parents=True, exist_ok=True)
            final = _livre(destino)
            shutil.move(str(origem), str(final))
            feitos.append({"origem": str(origem), "destino": str(final)})
        except Exception as e:
            falhas.append(f"{origem.name}: {e}")
    if feitos:
        PASTA_DESFAZER.mkdir(exist_ok=True)
        registro = PASTA_DESFAZER / f"{time.strftime('%Y%m%d-%H%M%S')}.json"
        registro.write_text(json.dumps({"rotulo": rotulo, "movimentos": feitos}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"feitos": len(feitos), "falhas": falhas}


def renomear(origem: Path, novo_nome: str, rs: list[Path]) -> Path:
    if any(c in novo_nome for c in '\\/:*?"<>|') or not novo_nome.strip():
        raise ErroArquivos("Nome inválido.")
    destino = origem.with_name(novo_nome.strip())
    if destino.exists():
        raise ErroArquivos("Já existe algo com esse nome.")
    _raiz_de(origem, rs)
    origem.rename(destino)
    PASTA_DESFAZER.mkdir(exist_ok=True)
    (PASTA_DESFAZER / f"{time.strftime('%Y%m%d-%H%M%S')}.json").write_text(json.dumps(
        {"rotulo": f"renomear {origem.name}", "movimentos": [{"origem": str(origem), "destino": str(destino)}]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return destino


def ultimo_registro() -> Path | None:
    registros = sorted(PASTA_DESFAZER.glob("*.json")) if PASTA_DESFAZER.exists() else []
    return registros[-1] if registros else None


def descricao_do_desfazer() -> tuple[str, int]:
    r = ultimo_registro()
    if r is None:
        raise ErroArquivos("Não há nenhuma organização para desfazer.")
    dados = json.loads(r.read_text(encoding="utf-8"))
    return dados["rotulo"], len(dados["movimentos"])


def desfazer(rs: list[Path]) -> dict:
    r = ultimo_registro()
    if r is None:
        raise ErroArquivos("Não há nenhuma organização para desfazer.")
    dados = json.loads(r.read_text(encoding="utf-8"))
    voltaram, falhas = 0, []
    for m in reversed(dados["movimentos"]):
        origem, atual = Path(m["origem"]), Path(m["destino"])
        try:
            _raiz_de(atual.resolve(), rs)
            if not atual.exists():
                raise ErroArquivos("não está mais lá")
            origem.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(atual), str(_livre(origem)))
            voltaram += 1
        except Exception as e:
            falhas.append(f"{atual.name}: {e}")
    r.rename(r.with_suffix(".feito"))
    # remove subpastas de categoria que ficaram vazias
    for m in dados["movimentos"]:
        pai = Path(m["destino"]).parent
        if pai.name in PASTAS_DE_CATEGORIA and pai.is_dir() and not any(pai.iterdir()):
            pai.rmdir()
    return {"voltaram": voltaram, "falhas": falhas}
