"""Tela ao vivo: resumo periódico entra no contexto; janela sensível NÃO é vista; desligar para tudo."""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
os.environ["JARVIS_MEMORIA_DIR"] = tempfile.mkdtemp(prefix="jarvis_tela_")
os.environ["JARVIS_SEM_VOZ"] = "1"
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
import server  # noqa: E402

ok = True


def checar(c, t):
    global ok
    ok &= bool(c)
    print("  [%s] %s" % ("OK" if c else "FALHOU", t))


class Resp:
    def __init__(self, t): self.content = [type("B", (), {"type": "text", "text": t})()]


class IaFalsa:
    def __init__(self): self.chamadas = 0
    class messages:  # noqa: N801
        pass


chamadas = []


class Msgs:
    async def create(self, **kw):
        chamadas.append(kw)
        return Resp("Planilha do Excel aberta com vendas de outubro.")


class Ia:
    messages = Msgs()


async def principal():
    server.ai = Ia()
    server.ferramentas.ver_tela = lambda *a, **k: [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAAA"}}, {"type": "text", "text": "x"}]
    foco = {"t": "Excel - vendas.xlsx"}
    server.windows_ctl.janela_em_foco = lambda: foco["t"]

    class WS:
        async def send_text(self, *_): pass
        async def send_json(self, *_): pass
    s = server.Sessao(WS())
    msgs = []

    async def env(m): msgs.append(m)
    s.enviar = env
    orig_sleep = asyncio.sleep

    async def rapido(t, *a, **k): await orig_sleep(0.01)
    server.asyncio.sleep = rapido
    await server.ligar_tela_ao_vivo(s, True)
    await orig_sleep(0.2)
    checar(s.tela_ativa and "Planilha" in s.tela_resumo, f"resumo entrou no contexto: {s.tela_resumo!r}")
    checar(any(m.get("tipo") == "tela_ao_vivo" and m["ativo"] for m in msgs), "a interface foi avisada (botão aceso)")
    n = len(chamadas)
    foco["t"] = "Nubank - Meu banco - Google Chrome"
    await orig_sleep(0.2)
    checar("sensível" in s.tela_resumo and len(chamadas) == n, "janela de banco em foco: não olhou nem mandou nada ao modelo")
    await server.ligar_tela_ao_vivo(s, False)
    n = len(chamadas)
    foco["t"] = "Excel"
    await orig_sleep(0.2)
    checar(not s.tela_ativa and s.tela_resumo == "" and len(chamadas) == n, "desligar zera o resumo e para as capturas")
    server.asyncio.sleep = orig_sleep


asyncio.run(principal())
print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
sys.exit(0 if ok else 1)
