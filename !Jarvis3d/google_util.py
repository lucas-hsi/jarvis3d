"""Utilidades compartilhadas por google_tools.py (Agenda/E-mail) e google_extra.py (organizar Gmail, Drive)."""

import base64
import json
import re
import time
from html.parser import HTMLParser

import google_auth as ga
import memoria

EMAIL = re.compile(r"^[^@\s<>,;\"']+@[^@\s<>,;\"']+\.[^@\s<>,;\"']+$")


def texto(entrada: dict, campo: str, obrigatorio=True) -> str:
    v = entrada.get(campo)
    if v is None or (isinstance(v, str) and not v.strip()):
        if obrigatorio:
            raise ga.ErroGoogle(f"Faltou o campo '{campo}'.")
        return ""
    return str(v).strip()


def validar_emails(lista, campo="para") -> list[str]:
    saida = []
    for e in lista or []:
        e = str(e).strip()
        if re.search(r"[\r\n]", e) or not EMAIL.match(e):
            raise ga.ErroGoogle(f"Endereço de e-mail inválido em '{campo}': {e[:60]}")
        saida.append(e)
    return saida


def registrar(tipo: str, **dados):
    try:
        memoria.PASTA.mkdir(parents=True, exist_ok=True)
        with open(memoria.PASTA / "google_atividade.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "tipo": tipo, **dados}, ensure_ascii=False) + "\n")
    except OSError:
        pass


class _Texto(HTMLParser):
    def __init__(self):
        super().__init__()
        self.partes, self._ignorar = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._ignorar += 1
        elif tag in ("br", "p", "div", "tr", "li", "h1", "h2", "h3"):
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._ignorar = max(0, self._ignorar - 1)

    def handle_data(self, d):
        if not self._ignorar:
            self.partes.append(d)


def html_para_texto(html: str) -> str:
    p = _Texto()
    p.feed(html)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", "".join(p.partes))).strip()


def decodificar(b64: str) -> str:
    return base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4)).decode("utf-8", errors="replace")


def corpo_e_anexos(payload: dict) -> tuple[str, list[str]]:
    texto_, html, anexos = [], [], []

    def andar(p):
        mime, dados = p.get("mimeType", ""), (p.get("body") or {}).get("data")
        if p.get("filename"):
            anexos.append(p["filename"])
        elif mime == "text/plain" and dados:
            texto_.append(decodificar(dados))
        elif mime == "text/html" and dados:
            html.append(decodificar(dados))
        for sub in p.get("parts") or []:
            andar(sub)
    andar(payload)
    corpo = "\n".join(texto_).strip() or html_para_texto("\n".join(html))
    return corpo, anexos


def cabecalho(msg: dict, nome: str) -> str:
    for h in (msg.get("payload") or {}).get("headers", []):
        if h["name"].lower() == nome.lower():
            return h["value"]
    return ""
