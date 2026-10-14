"""
Leitura do cofre do Obsidian (somente leitura).

Tudo fica preso dentro da pasta do cofre: nenhum caminho vindo do modelo
consegue sair dela.
"""

import re
import unicodedata
from pathlib import Path

IGNORAR = {".obsidian", ".trash", "Templates"}
ITEM_NUMERADO = re.compile(r"^\s*\d+\.\s+\*\*(.+?)\*\*", re.MULTILINE)


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower()


def _notas(cofre: Path):
    for caminho in cofre.rglob("*.md"):
        if not any(parte in IGNORAR for parte in caminho.relative_to(cofre).parts):
            yield caminho


def _dentro_do_cofre(cofre: Path, caminho: Path) -> bool:
    try:
        return caminho.resolve().is_relative_to(cofre.resolve())
    except OSError:
        return False


def pendencias(cofre: Path, notas: list[str]) -> list[dict]:
    """Títulos dos itens numerados ("1. **Título.**") de cada nota de pendências."""
    projetos = []
    for relativo in notas:
        caminho = cofre / relativo
        if not _dentro_do_cofre(cofre, caminho) or not caminho.is_file():
            continue
        texto = caminho.read_text(encoding="utf-8", errors="ignore")
        itens = [t.strip().rstrip(".:") for t in ITEM_NUMERADO.findall(texto)]
        projeto = caminho.parent.name if caminho.parent != cofre else caminho.stem
        projetos.append({"projeto": projeto, "total": len(itens), "itens": itens})
    return projetos


def buscar(cofre: Path, busca: str, limite: int = 6) -> str:
    """Procura as palavras da busca nas notas e devolve trechos com o nome da nota."""
    palavras = [p for p in _normalizar(busca).split() if len(p) > 2]
    if not palavras:
        return "Busca vazia."

    achados = []
    for caminho in _notas(cofre):
        texto = caminho.read_text(encoding="utf-8", errors="ignore")
        normal = _normalizar(texto)
        if not all(p in normal for p in palavras):
            continue
        pontos = sum(normal.count(p) for p in palavras)
        # O texto normalizado tem o mesmo tamanho na maioria dos casos; serve
        # para localizar o trecho aproximado no original.
        pos = normal.find(palavras[0])
        trecho = texto[max(0, pos - 300): pos + 600].replace("\n", " ")
        achados.append((pontos, caminho.relative_to(cofre).as_posix(), trecho))

    if not achados:
        return f"Nada encontrado no cofre para: {busca}"
    achados.sort(reverse=True)
    blocos = [f"[{nome}]\n...{trecho}..." for _, nome, trecho in achados[:limite]]
    return "\n\n".join(blocos)


def ler(cofre: Path, nome: str, limite: int = 9000) -> str:
    """Lê uma nota pelo nome (com ou sem .md, sem diferenciar acento/maiúscula)."""
    alvo = _normalizar(Path(nome).stem)
    candidatos = [c for c in _notas(cofre) if _normalizar(c.stem) == alvo]
    if not candidatos:
        candidatos = [c for c in _notas(cofre) if alvo in _normalizar(c.stem)]
    if not candidatos:
        return f"Nenhuma nota chamada '{nome}'."
    caminho = min(candidatos, key=lambda c: len(c.stem))
    if not _dentro_do_cofre(cofre, caminho):
        return "Nota fora do cofre."
    texto = caminho.read_text(encoding="utf-8", errors="ignore")
    if len(texto) > limite:
        texto = texto[:limite] + "\n[...nota cortada por tamanho...]"
    return f"[{caminho.relative_to(cofre).as_posix()}]\n{texto}"
