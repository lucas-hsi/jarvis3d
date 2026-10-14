"""
Autorização do Google (Gmail e Agenda) e chamadas à API.

- Fluxo de "app instalado" com PKCE: abre o seu navegador, você escolhe a conta e aprova, o Google devolve um
  código para um endereço local (127.0.0.1) e o Jarvis troca por um token. A sua senha do Google nunca passa por aqui.
- O token de renovação fica no COFRE DE CREDENCIAIS DO WINDOWS (não em arquivo). O arquivo do cliente OAuth
  (segredos\\google_client.json) é o único segredo em disco; está no .gitignore.
- Permissões mínimas: ler Gmail, criar rascunhos/enviar, ler/criar/editar eventos da Agenda.
- Para revogar a qualquer momento: https://myaccount.google.com/permissions
"""

import asyncio
import base64
import hashlib
import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

import caminhos

BASE = Path(__file__).parent
ARQ_CLIENTE = Path(os.environ.get("JARVIS_GOOGLE_CLIENTE") or caminhos.DADOS / "segredos" / "google_client.json")
URL_AUTH = os.environ.get("JARVIS_GOOGLE_AUTH", "https://accounts.google.com/o/oauth2/v2/auth")
URL_TOKEN = os.environ.get("JARVIS_GOOGLE_TOKEN", "https://oauth2.googleapis.com/token")
GMAIL = os.environ.get("JARVIS_GOOGLE_GMAIL", "https://gmail.googleapis.com/gmail/v1/users/me")
AGENDA = os.environ.get("JARVIS_GOOGLE_AGENDA", "https://www.googleapis.com/calendar/v3")
DRIVE = os.environ.get("JARVIS_GOOGLE_DRIVE", "https://www.googleapis.com/drive/v3")
SERVICO = "Jarvis-Google"

ESC_GMAIL_LER = "https://www.googleapis.com/auth/gmail.readonly"
ESC_GMAIL_ESCREVER = "https://www.googleapis.com/auth/gmail.compose"
ESC_AGENDA_EVENTOS = "https://www.googleapis.com/auth/calendar.events"
ESC_AGENDA_LER = "https://www.googleapis.com/auth/calendar.readonly"
ESC_GMAIL_ORGANIZAR = "https://www.googleapis.com/auth/gmail.modify"     # marcar lido, rótulos, arquivar, lixeira (NÃO apaga de vez)
ESC_DRIVE = "https://www.googleapis.com/auth/drive"
ESCOPOS = [ESC_GMAIL_LER, ESC_GMAIL_ESCREVER, ESC_GMAIL_ORGANIZAR, ESC_AGENDA_EVENTOS, ESC_AGENDA_LER, ESC_DRIVE]
NOMES_ESCOPO = {ESC_GMAIL_LER: "ler o Gmail", ESC_GMAIL_ESCREVER: "criar rascunhos e enviar e-mails",
                ESC_GMAIL_ORGANIZAR: "organizar o Gmail (lido, rótulos, arquivar, lixeira)",
                ESC_AGENDA_EVENTOS: "criar e editar eventos da Agenda", ESC_AGENDA_LER: "ler a Agenda",
                ESC_DRIVE: "ler e organizar o Google Drive"}


class ErroGoogle(ValueError):
    """Erro com mensagem pronta para o Jarvis explicar ao usuário."""


# ------------------------------------------------------------------ onde o token fica guardado
def _arquivo_de_teste() -> Path | None:
    p = os.environ.get("JARVIS_SEGREDOS_ARQUIVO")
    return Path(p) if p else None


def _guardar(dados: dict):
    arq = _arquivo_de_teste()
    if arq:                                  # só nos testes
        arq.write_text(json.dumps(dados), encoding="utf-8")
        return
    import keyring
    keyring.set_password(SERVICO, "token", json.dumps(dados))


def _ler() -> dict | None:
    arq = _arquivo_de_teste()
    try:
        if arq:
            return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None
        import keyring
        bruto = keyring.get_password(SERVICO, "token")
        return json.loads(bruto) if bruto else None
    except Exception:
        return None


def _apagar():
    arq = _arquivo_de_teste()
    if arq:
        arq.unlink(missing_ok=True)
        return
    try:
        import keyring
        keyring.delete_password(SERVICO, "token")
    except Exception:
        pass


_cache = {"token": None, "expira": 0.0}


def desconectar():
    _apagar()
    _cache.update(token=None, expira=0.0)


def conectado() -> bool:
    return bool(_ler())


def escopos_concedidos() -> list[str]:
    return (_ler() or {}).get("escopos", [])


def tem_escopo(escopo: str) -> bool:
    return escopo in escopos_concedidos()


def cliente() -> tuple[str, str]:
    try:
        bruto = json.loads(ARQ_CLIENTE.read_text(encoding="utf-8"))
    except OSError:
        raise ErroGoogle("Falta o arquivo do cliente OAuth do Google (segredos\\google_client.json). Siga o guia GOOGLE-SETUP.md.")
    except json.JSONDecodeError:
        raise ErroGoogle("O arquivo segredos\\google_client.json não é um JSON válido. Baixe-o de novo no Google Cloud.")
    dados = bruto.get("installed") or bruto.get("web") or bruto
    if not dados.get("client_id") or not dados.get("client_secret"):
        raise ErroGoogle("O arquivo do cliente OAuth não tem client_id/client_secret. Crie um cliente do tipo 'App para computador'.")
    return dados["client_id"], dados["client_secret"]


def cliente_configurado() -> bool:
    try:
        cliente()
        return True
    except ErroGoogle:
        return False


# ------------------------------------------------------------------ autorização (abre o navegador)
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def autorizar(abrir=webbrowser.open, timeout: float = 240) -> dict:
    """Roda o fluxo completo e guarda o token. Bloqueia até você aprovar (ou estourar o tempo). Rode numa thread."""
    cid, segredo = cliente()
    verificador = secrets.token_urlsafe(64)
    desafio = _b64(hashlib.sha256(verificador.encode()).digest())
    estado = secrets.token_urlsafe(24)
    resultado: dict = {}

    class Receptor(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            if q.get("state", [""])[0] != estado:
                self.send_response(400); self.end_headers(); self.wfile.write(b"state invalido"); return
            resultado["codigo"] = q.get("code", [""])[0]
            resultado["erro"] = q.get("error", [""])[0]
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Jarvis conectado ao Google. Pode fechar esta janela." if resultado["codigo"] else "A autorização foi negada."
            self.wfile.write(f"<html><body style='font-family:sans-serif;background:#02060d;color:#7df9ff;text-align:center;padding-top:20vh'>"
                             f"<h2>J.A.R.V.I.S.</h2><p>{msg}</p></body></html>".encode())

    servidor = HTTPServer(("127.0.0.1", 0), Receptor)
    servidor.timeout = 1
    redirecionamento = f"http://127.0.0.1:{servidor.server_port}"
    url = URL_AUTH + "?" + urlencode({
        "client_id": cid, "redirect_uri": redirecionamento, "response_type": "code", "scope": " ".join(ESCOPOS),
        "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true",
        "code_challenge": desafio, "code_challenge_method": "S256", "state": estado})
    abrir(url)
    fim = time.time() + timeout
    try:
        while not resultado and time.time() < fim:
            servidor.handle_request()
    finally:
        servidor.server_close()
    if not resultado:
        raise ErroGoogle("A autorização demorou demais e foi cancelada.")
    if resultado.get("erro") or not resultado.get("codigo"):
        raise ErroGoogle("A autorização foi negada no Google.")

    r = httpx.post(URL_TOKEN, timeout=20, data={
        "code": resultado["codigo"], "client_id": cid, "client_secret": segredo, "code_verifier": verificador,
        "grant_type": "authorization_code", "redirect_uri": redirecionamento})
    if r.status_code != 200:
        raise ErroGoogle(f"O Google recusou a troca do código ({r.status_code}).")
    j = r.json()
    if not j.get("refresh_token"):
        raise ErroGoogle("O Google não devolveu o token de renovação. Revogue o acesso do Jarvis em myaccount.google.com/permissions e tente de novo.")
    concedidos = [e for e in j.get("scope", "").split() if e in ESCOPOS]
    _guardar({"refresh_token": j["refresh_token"], "escopos": concedidos, "obtido_em": time.time()})
    _cache.update(token=j.get("access_token"), expira=time.time() + int(j.get("expires_in", 3000)))
    faltam = [NOMES_ESCOPO[e] for e in ESCOPOS if e not in concedidos]
    return {"escopos": concedidos, "faltam": faltam}


# ------------------------------------------------------------------ chamadas à API
async def token_de_acesso() -> str:
    if _cache["token"] and time.time() < _cache["expira"] - 60:
        return _cache["token"]
    dados = _ler()
    if not dados:
        raise ErroGoogle("O Google ainda não está conectado. Diga 'conecta meu Google' ou rode Conectar-Google.cmd.")
    cid, segredo = cliente()
    async with httpx.AsyncClient(timeout=15) as http:
        r = await http.post(URL_TOKEN, data={"client_id": cid, "client_secret": segredo,
                                              "refresh_token": dados["refresh_token"], "grant_type": "refresh_token"})
    if r.status_code != 200:
        try:
            motivo = r.json().get("error", "")
        except Exception:
            motivo = ""
        if motivo == "invalid_grant":
            _apagar()
            _cache.update(token=None, expira=0.0)
            raise ErroGoogle("A autorização do Google expirou ou foi revogada. Conecte de novo (diga 'conecta meu Google').")
        raise ErroGoogle(f"Não consegui renovar o acesso ao Google ({r.status_code}).")
    j = r.json()
    _cache.update(token=j["access_token"], expira=time.time() + int(j.get("expires_in", 3000)))
    return _cache["token"]


async def api(metodo: str, url: str, *, params=None, corpo=None, escopo: str | None = None, texto: bool = False) -> dict | str:
    if escopo and not tem_escopo(escopo):
        raise ErroGoogle(f"Falta a permissão para {NOMES_ESCOPO.get(escopo, escopo)}. Conecte de novo e marque todas as caixas.")
    async with httpx.AsyncClient(timeout=20) as http:
        for tentativa in (0, 1):
            tk = await token_de_acesso()
            r = await http.request(metodo, url, params=params, json=corpo, headers={"Authorization": f"Bearer {tk}"})
            if r.status_code == 401 and tentativa == 0:
                _cache.update(token=None, expira=0.0)
                continue
            break
    if r.status_code == 204:
        return {}
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {}).get("message", "")
        except Exception:
            msg = r.text[:120]
        raise ErroGoogle(f"O Google recusou ({r.status_code}): {msg}"[:260])
    return r.text if texto else r.json()


if __name__ == "__main__":     # python google_auth.py  (ou Conectar-Google.cmd)
    print("Vou abrir o Google no seu navegador. Escolha a conta, clique em 'Avançado' se aparecer o aviso de app não")
    print("verificado, marque TODAS as permissões e confirme.\n")
    try:
        r = autorizar()
        print("Conectado!" if not r["faltam"] else "Conectado, mas faltam permissões: " + "; ".join(r["faltam"]))
    except ErroGoogle as e:
        print("Não deu certo:", e)
    input("\nAperte Enter para fechar...")
