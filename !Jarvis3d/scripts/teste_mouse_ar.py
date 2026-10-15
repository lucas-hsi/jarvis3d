"""Mouse no ar (servidor): ignora tudo se o usuário não ligou; baixa/solta o botão; bloqueia clique em janela sensível; freia excesso de cliques; desligar solta o botão; intenção por voz."""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
os.environ["JARVIS_MEMORIA_DIR"] = tempfile.mkdtemp(prefix="jarvis_mouse_")
os.environ["JARVIS_SEM_VOZ"] = "1"
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
import intencoes  # noqa: E402
import server  # noqa: E402

ok = True


def checar(c, t):
    global ok
    ok &= bool(c)
    print("  [%s] %s" % ("OK" if c else "FALHOU", t))


calls = []
wc = server.windows_ctl
wc.mover_mouse = lambda x, y: calls.append(("mover", round(x), round(y)))
wc.mouse_botao = lambda b, botao="esquerdo": calls.append(("botao", b, botao))
wc.clicar = lambda x, y, botao="esquerdo", duplo=False: calls.append(("clicar", botao))
wc.rolar = lambda p: calls.append(("rolar", p))
wc.zoom = lambda p: calls.append(("zoom", p))
wc.tamanho_da_tela = lambda: (1000, 500)
wc.tecla_pressionada = lambda vk: False
foco = {"t": "Bloco de notas"}
wc.janela_em_foco = lambda: foco["t"]


class WS:
    async def send_text(self, *_): pass
    async def send_json(self, *_): pass


async def principal():
    s = server.Sessao(WS())
    msgs = []

    async def env(m): msgs.append(m)
    s.enviar = env
    server.tratar_mouse(s, {"acao": "mover", "x": 0.5, "y": 0.5})
    checar(not calls, "modo desligado: tudo é ignorado (nem o modelo nem a rede ligam sozinhos)")
    await server.ligar_mouse_no_ar(s, True)
    server.tratar_mouse(s, {"acao": "mover", "x": 0.5, "y": 0.5})
    checar(("mover", 500, 250) in calls or ("mover", 500, 249) in calls, f"mover converte 0..1 para pixels da tela: {calls[-1]}")
    server.tratar_mouse(s, {"acao": "baixar"})
    server.tratar_mouse(s, {"acao": "soltar"})
    checar(calls[-2:] == [("botao", True, "esquerdo"), ("botao", False, "esquerdo")], "baixar e soltar apertam e soltam o botão esquerdo")
    server.tratar_mouse(s, {"acao": "rolar", "passos": 99})
    server.tratar_mouse(s, {"acao": "zoom", "passos": -9})
    checar(("rolar", 5) in calls and ("zoom", -3) in calls, "rolagem e zoom têm limite por comando")
    foco["t"] = "Nubank - Meu banco - Google Chrome"
    n = len(calls)
    server.tratar_mouse(s, {"acao": "baixar"})
    await asyncio.sleep(0.05)
    checar(len(calls) == n and any("sensível" in m.get("texto", "") for m in msgs), "janela de banco em foco: clique por gesto bloqueado e avisado")
    foco["t"] = "Bloco de notas"
    s.mouse_cliques = []
    for _ in range(12):
        server.tratar_mouse(s, {"acao": "clique_direito"})
    checar(sum(1 for c in calls if c == ("clicar", "direito")) == 8, "no máximo 8 cliques por segundo")
    server.tratar_mouse(s, {"acao": "baixar"}) if False else None
    s.mouse_cliques = []
    server.tratar_mouse(s, {"acao": "baixar"})
    checar(s.mouse_baixo, "botão ficou apertado (arrastando)")
    await server.ligar_mouse_no_ar(s, False)
    checar(calls[-1] == ("botao", False, "esquerdo") and not s.mouse_baixo and not s.mouse_ativo, "desligar SEMPRE solta o botão")
    checar(any(m.get("tipo") == "mouse_modo" and m["ativo"] is False for m in msgs), "a interface é avisada do desligamento")
    wc.tecla_pressionada = lambda vk: vk == 0x1B
    await server.ligar_mouse_no_ar(s, True)
    await asyncio.sleep(0.6)
    checar(not s.mouse_ativo, "ESC (em qualquer janela) desliga o modo")


asyncio.run(principal())
print("INTENÇÕES POR VOZ")
for f, v in (("ativa o mouse no ar", True), ("liga o mouse", True), ("Jarvis, ativa o cursor por gesto", True), ("desativa o mouse no ar", False), ("para o mouse", False)):
    r = intencoes.interpretar(f, lambda n: None)
    checar(r and r["acao"] == "mouse" and r["valor"] is v, f"'{f}' -> {r and r['valor']}")
for f in ("abre o mouse do windows", "o mouse está quebrado", "move o mouse para o canto"):
    checar(intencoes.interpretar(f, lambda n: None) is None, f"'{f}' não é atalho")
print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
sys.exit(0 if ok else 1)
