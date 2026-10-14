"""
Teste de ponta a ponta do controle com confirmação, sem gastar nada e sem tocar nas suas pastas:
API da Anthropic falsa + pasta temporária liberada + servidor numa porta própria + WebSocket como o navegador.

Cenários: (1) o usuário confirma, (2) o usuário recusa. Confere também as emoções por frase.

Uso:  .venv\\Scripts\\python.exe -X utf8 scripts\\teste_confirmacao.py
"""

import asyncio
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

BASE = Path(__file__).resolve().parent.parent
PORTA_SERVIDOR, PORTA_FALSA = 8350, 9877
PASTA_ALVO = ""


def sse(evento, dados):
    return f"event: {evento}\ndata: {json.dumps(dados)}\n\n".encode()


def corpo_stream(blocos, parada):
    saida = sse("message_start", {"type": "message_start", "message": {
        "id": "msg_t", "type": "message", "role": "assistant", "model": "claude-haiku-5-5", "content": [],
        "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 5, "output_tokens": 1}}})
    for i, b in enumerate(blocos):
        if b["type"] == "text":
            saida += sse("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}})
            for pedaco in b["pedacos"]:
                saida += sse("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": pedaco}})
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
        if req.get("tool_choice"):          # aprendizado em segundo plano: nada a registrar
            dados = json.dumps({"id": "m", "type": "message", "role": "assistant", "model": "x", "stop_sequence": None,
                                "content": [{"type": "tool_use", "id": "t", "name": "registrar_memorias", "input": {"operacoes": []}}],
                                "stop_reason": "tool_use", "usage": {"input_tokens": 1, "output_tokens": 1}}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(dados)
            return
        ultimo = req["messages"][-1]
        tem_resultado = isinstance(ultimo["content"], list) and any(c.get("type") == "tool_result" for c in ultimo["content"])
        if not tem_resultado:
            dados = corpo_stream([
                {"type": "text", "pedacos": ["[[adrenalina]] Vamos arrumar essa bagunça agora mesmo! "]},
                {"type": "tool_use", "id": "toolu_1", "name": "organizar_pasta", "input": {"pasta": PASTA_ALVO}},
            ], "tool_use")
        else:
            resultado = json.dumps(ultimo["content"], ensure_ascii=False)
            fala = "[[triunfante]] Missão cumprida, chefe." if "Movidos" in resultado else "[[serio]] Entendido, não mexi em nada."
            dados = corpo_stream([{"type": "text", "pedacos": [fala]}], "end_turn")
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        self.wfile.write(dados)


async def rodada(confirmar: bool):
    eventos = []
    async with websockets.connect(f"ws://127.0.0.1:{PORTA_SERVIDOR}/ws", origin=f"http://127.0.0.1:{PORTA_SERVIDOR}") as ws:
        await ws.send(json.dumps({"tipo": "fala", "texto": "organiza meus downloads"}))
        respondeu = False
        while True:
            m = json.loads(await asyncio.wait_for(ws.recv(), 30))
            if m["tipo"] in ("sistema", "painel"):
                continue
            eventos.append(m)
            if m["tipo"] == "confirmar" and not respondeu:
                respondeu = True
                antes = sorted(p.name for p in Path(PASTA_ALVO).iterdir())
                eventos.append({"tipo": "_arquivos_antes_de_responder", "lista": antes})
                await ws.send(json.dumps({"tipo": "confirmacao", "id": m["id"], "ok": confirmar}))
            if m["tipo"] == "fim":
                return eventos


def principal():
    global PASTA_ALVO
    raiz = Path(tempfile.mkdtemp(prefix="jarvis_conf_"))
    alvo = raiz / "Downloads"
    alvo.mkdir()
    PASTA_ALVO = str(alvo)
    antigo = time.time() - 86400
    for n in ["a.jpg", "b.png", "c.pdf", "d.docx"]:
        f = alvo / n
        f.write_text("x")
        os.utime(f, (antigo, antigo))

    cfg = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
    cfg.update(porta=PORTA_SERVIDOR, pastas_liberadas=[str(raiz)], anthropic_api_key="falsa", elevenlabs_api_key="")
    arq_cfg = raiz / "config_teste.json"
    arq_cfg.write_text(json.dumps(cfg), encoding="utf-8")

    falso = HTTPServer(("127.0.0.1", PORTA_FALSA), Falsa)
    threading.Thread(target=falso.serve_forever, daemon=True).start()
    env = dict(os.environ, JARVIS_MEMORIA_DIR=str(raiz / "mem"), JARVIS_CONFIG=str(arq_cfg), ANTHROPIC_BASE_URL=f"http://127.0.0.1:{PORTA_FALSA}",
               ELEVENLABS_API_KEY="", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    proc = subprocess.Popen([sys.executable, str(BASE / "server.py")], cwd=BASE, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    ok = True

    def checar(cond, texto):
        nonlocal ok
        ok &= bool(cond)
        print("  [%s] %s" % ("OK" if cond else "FALHOU", texto))

    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORTA_SERVIDOR}/api/saude", timeout=1)
                break
            except Exception:
                time.sleep(0.5)

        print("CENÁRIO 1: o usuário CONFIRMA")
        ev = asyncio.run(rodada(True))
        tipos = [e["tipo"] for e in ev]
        conf = next(e for e in ev if e["tipo"] == "confirmar")
        antes = next(e for e in ev if e["tipo"] == "_arquivos_antes_de_responder")["lista"]
        falas = [e for e in ev if e["tipo"] == "fala"]
        checar("organizar_pasta" and "Organizar Downloads" in conf["titulo"], f"pedido de confirmação: {conf['titulo']}")
        checar(any("Imagens" in d for d in conf["detalhes"]), f"detalhes mostram o plano: {conf['detalhes'][:3]}")
        checar(antes == ["a.jpg", "b.png", "c.pdf", "d.docx"], "ANTES de responder, nenhum arquivo foi movido")
        checar((alvo / "Imagens" / "a.jpg").exists() and (alvo / "PDFs" / "c.pdf").exists(), "depois de confirmar, os arquivos foram organizados")
        emocoes = [(f["emocao"], f["texto"]) for f in falas]
        checar(("adrenalina", "Vamos arrumar essa bagunça agora mesmo!") in emocoes, f"emoção 'adrenalina' veio na frase (marca removida do texto): {emocoes[:1]}")
        checar(any(e == "triunfante" for e, _ in emocoes), "emoção 'triunfante' na conclusão")
        checar(any("confirmação" in t.lower() and e == "serio" for e, t in emocoes), "Jarvis falou o pedido de confirmação")
        checar(not any("[[" in t for _, t in emocoes), "nenhuma marca [[...]] vazou para a fala")
        checar(tipos.index("confirmar") < tipos.index("confirmar_fim") < tipos.index("fim"), "ordem: confirmar → fim da confirmação → fim")

        print("\nCENÁRIO 2: o usuário RECUSA (depois de desfazer o anterior)")
        for sub in ("Imagens", "PDFs", "Documentos"):
            for f in (alvo / sub).glob("*"):
                f.rename(alvo / f.name)
            (alvo / sub).rmdir()
        ev = asyncio.run(rodada(False))
        falas = [(e["emocao"], e["texto"]) for e in ev if e["tipo"] == "fala"]
        depois = sorted(p.name for p in alvo.iterdir())
        checar(depois == ["a.jpg", "b.png", "c.pdf", "d.docx"], f"recusou: nada foi movido ({depois})")
        checar(any(e == "serio" and "não mexi" in t for e, t in falas), "Jarvis reconheceu a recusa")
    finally:
        proc.terminate()
        falso.shutdown()
        import shutil
        shutil.rmtree(raiz, ignore_errors=True)
        shutil.rmtree(BASE / "desfazer", ignore_errors=True)

    print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
    sys.exit(0 if ok else 1)


principal()
