"""
Teste da webcam de ponta a ponta, sem câmera real e sem gastar nada: um "navegador" simulado responde ao pedido
de captura com uma foto gerada. Confere a confirmação na 1ª foto, a imagem chegando ao modelo, recusa, erros
de permissão e imagem inválida, e que nada é gravado em disco.

Uso:  .venv\\Scripts\\python.exe -X utf8 scripts\\teste_camera.py
"""

import asyncio
import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import websockets
from PIL import Image

BASE = Path(__file__).resolve().parent.parent
PORTA_SERVIDOR, PORTA_FALSA = 8352, 9879
PRINCIPAIS: list[dict] = []


def sse(evento, dados):
    return f"event: {evento}\ndata: {json.dumps(dados)}\n\n".encode()


def corpo(blocos, parada):
    saida = sse("message_start", {"type": "message_start", "message": {
        "id": "m", "type": "message", "role": "assistant", "model": "claude-haiku-5-5", "content": [],
        "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 5, "output_tokens": 1}}})
    for i, b in enumerate(blocos):
        if b["type"] == "text":
            saida += sse("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}})
            saida += sse("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": b["texto"]}})
        else:
            saida += sse("content_block_start", {"type": "content_block_start", "index": i, "content_block": {
                "type": "tool_use", "id": b["id"], "name": b["name"], "input": {}}})
            saida += sse("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {
                "type": "input_json_delta", "partial_json": json.dumps(b["input"])}})
        saida += sse("content_block_stop", {"type": "content_block_stop", "index": i})
    saida += sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": parada, "stop_sequence": None}, "usage": {"output_tokens": 9}})
    return saida + sse("message_stop", {"type": "message_stop"})


class Falsa(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
        if req.get("tool_choice"):
            dados = json.dumps({"id": "m", "type": "message", "role": "assistant", "model": "x", "stop_sequence": None,
                                "content": [{"type": "tool_use", "id": "t", "name": "registrar_memorias", "input": {"operacoes": []}}],
                                "stop_reason": "tool_use", "usage": {"input_tokens": 1, "output_tokens": 1}}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(dados)
            return
        PRINCIPAIS.append(req)
        ultimo = req["messages"][-1]["content"]
        if isinstance(ultimo, list) and any(c.get("type") == "tool_result" for c in ultimo):
            dados = corpo([{"type": "text", "texto": "Você está de camisa azul, chefe."}], "end_turn")
        else:
            dados = corpo([{"type": "tool_use", "id": "toolu_c", "name": "ver_camera", "input": {"segundos": 1}}], "tool_use")
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        self.wfile.write(dados)


def foto(largura=1280, altura=720) -> str:
    b = io.BytesIO()
    Image.effect_noise((largura, altura), 60).convert("RGB").save(b, "JPEG", quality=85)
    return base64.b64encode(b.getvalue()).decode()


async def conversa(ws, texto, confirmar=True, resposta_camera=None):
    """Um turno numa conexão já aberta. `resposta_camera`: dict que o 'navegador' devolve ao pedido de captura."""
    await ws.send(json.dumps({"tipo": "fala", "texto": texto}))
    eventos = []
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), 30))
        if m["tipo"] in ("sistema", "painel"):
            continue
        eventos.append(m)
        if m["tipo"] == "confirmar":
            await ws.send(json.dumps({"tipo": "confirmacao", "id": m["id"], "ok": confirmar}))
        elif m["tipo"] == "capturar_camera":
            await ws.send(json.dumps({"tipo": "foto_camera", "id": m["id"], **(resposta_camera or {"imagem": foto()})}))
        elif m["tipo"] == "fim":
            return eventos


def conectar():
    return websockets.connect(f"ws://127.0.0.1:{PORTA_SERVIDOR}/ws", origin=f"http://127.0.0.1:{PORTA_SERVIDOR}", max_size=2 ** 24)


def resultado_da_ferramenta(req) -> dict:
    return next(c for c in req["messages"][-1]["content"] if c.get("type") == "tool_result")


def principal():
    tmp = Path(tempfile.mkdtemp(prefix="jarvis_cam_"))
    cfg = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
    cfg.update(porta=PORTA_SERVIDOR, anthropic_api_key="falsa", elevenlabs_api_key="", autorizacao="sempre_perguntar")   # este teste exercita o caminho COM confirmação
    arq = tmp / "config_teste.json"
    arq.write_text(json.dumps(cfg), encoding="utf-8")
    falso = HTTPServer(("127.0.0.1", PORTA_FALSA), Falsa)
    threading.Thread(target=falso.serve_forever, daemon=True).start()
    env = dict(os.environ, JARVIS_CONFIG=str(arq), JARVIS_MEMORIA_DIR=str(tmp / "mem"), ANTHROPIC_BASE_URL=f"http://127.0.0.1:{PORTA_FALSA}",
               ELEVENLABS_API_KEY="", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    proc = subprocess.Popen([sys.executable, str(BASE / "server.py")], cwd=BASE, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    ok = True

    def checar(cond, texto):
        nonlocal ok
        ok &= bool(cond)
        print("  [%s] %s" % ("OK" if cond else "FALHOU", texto))

    async def tudo():
        print("1) PRIMEIRA FOTO da sessão: pede confirmação, depois captura")
        async with conectar() as ws:
            ev = await conversa(ws, "o que estou vestindo?")
            tipos = [e["tipo"] for e in ev]
            conf = next((e for e in ev if e["tipo"] == "confirmar"), None)
            checar(conf and "câmera" in conf["titulo"].lower(), f"pediu confirmação antes de ligar: {conf and conf['titulo']}")
            checar(conf and any("não é salva" in d for d in conf["detalhes"]), "a confirmação avisa que a imagem não é salva")
            checar("capturar_camera" in tipos and tipos.index("confirmar") < tipos.index("capturar_camera"), "a captura só é pedida DEPOIS do sim")
            cap = next(e for e in ev if e["tipo"] == "capturar_camera")
            checar(cap["segundos"] == 1, "o modelo pôde pedir a contagem regressiva (1 s)")
            res = resultado_da_ferramenta(PRINCIPAIS[-1])
            blocos = res["content"]
            img = next((b for b in blocos if b.get("type") == "image"), None)
            checar(img and img["source"]["media_type"] == "image/jpeg", "a imagem chegou ao modelo como bloco de imagem JPEG")
            im = Image.open(io.BytesIO(base64.b64decode(img["source"]["data"])))
            checar(max(im.size) <= 1024, f"foi reduzida para o máximo de 1024 px ({im.size[0]}x{im.size[1]}), controlando o custo")
            checar(any(e["tipo"] == "fala" and "camisa azul" in e["texto"] for e in ev), "o Jarvis respondeu com base na foto")
            rot = [e["rotulo"] for e in ev if e["tipo"] == "ferramenta" and e["estado"] == "inicio"]
            checar(rot == ["CÂMERA"], "a atividade mostra CÂMERA")

            print("\n2) SEGUNDA FOTO, mesma sessão: não pergunta de novo")
            ev = await conversa(ws, "e agora?")
            checar(not any(e["tipo"] == "confirmar" for e in ev) and any(e["tipo"] == "capturar_camera" for e in ev), "já autorizada nesta sessão, captura direto")

        print("\n3) USUÁRIO RECUSA (sessão nova)")
        async with conectar() as ws:
            ev = await conversa(ws, "olha pra mim", confirmar=False)
            checar(not any(e["tipo"] == "capturar_camera" for e in ev), "recusou: a câmera NUNCA foi acionada")
            res = resultado_da_ferramenta(PRINCIPAIS[-1])
            checar("NÃO autorizou" in json.dumps(res["content"], ensure_ascii=False), "o modelo foi informado da recusa")

        print("\n4) ERROS no navegador")
        async with conectar() as ws:
            ev = await conversa(ws, "me vê", resposta_camera={"erro": "permissao"})
            res = resultado_da_ferramenta(PRINCIPAIS[-1])
            checar(res.get("is_error") and "bloqueou a câmera" in json.dumps(res["content"], ensure_ascii=False), "permissão negada vira erro claro (sem travar)")
            checar(ev[-1]["tipo"] == "fim", "o turno termina normalmente")
            ev = await conversa(ws, "me vê de novo", resposta_camera={"imagem": base64.b64encode(b"isso nao e uma imagem").decode()})
            res = resultado_da_ferramenta(PRINCIPAIS[-1])
            checar(res.get("is_error") and "inválida" in json.dumps(res["content"], ensure_ascii=False), "imagem inválida é recusada")
            ev = await conversa(ws, "mais uma", resposta_camera={"imagem": "A" * 5_000_000})
            res = resultado_da_ferramenta(PRINCIPAIS[-1])
            checar(res.get("is_error"), "imagem gigante é recusada")

        print("\n5) NADA EM DISCO")
        achados = [p for p in list(BASE.rglob("*.jpg")) + list(BASE.rglob("*.jpeg")) + list((tmp).rglob("*.jpg")) if ".venv" not in p.parts]
        checar(not achados, f"nenhuma foto gravada no projeto nem na memória ({len(achados)} arquivos de imagem)")

    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORTA_SERVIDOR}/api/saude", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        asyncio.run(tudo())
    finally:
        proc.terminate()
        falso.shutdown()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
    sys.exit(0 if ok else 1)


principal()
