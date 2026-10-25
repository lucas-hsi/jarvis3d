"""Adaptador do Gemini SEM rede: chamadas paralelas não grudam os nomes, blocos viram JSON (a reserva aceita), entrada vazia não quebra
e a thought signature volta para o Gemini. Bugs vistos no servidor.log de 2026-10-24 ('trilha_sonoraterminal_executar',
"'ToolUseBlock' object has no attribute 'get'", 'ToolUseBlock is not JSON serializable')."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")
import gemini_adaptador as g  # noqa: E402

ok = True


def checar(c, t):
    global ok
    ok &= bool(c)
    print("  [%s] %s" % ("OK" if c else "FALHOU", t))


def juntar(pedacos):
    agg = {}
    for p in pedacos:
        g.juntar_chamada(agg, p)
    return [(v["name"], json.loads(v["arguments"] or "{}")) for v in agg.values()]


def fc(nome=None, args=None, id_=None, index=None):
    d = {"function": {}}
    if nome:
        d["function"]["name"] = nome
    if args is not None:
        d["function"]["arguments"] = args
    if id_:
        d["id"] = id_
    if index is not None:
        d["index"] = index
    return d


r = juntar([fc("trilha_sonora", '{"acao":"iniciar"}', index=0), fc("terminal_executar", '{"comando":"Get-Date"}', index=0)])
checar([n for n, _ in r] == ["trilha_sonora", "terminal_executar"], f"duas chamadas paralelas com o MESMO index ficam separadas: {r}")
r = juntar([fc("trilha_sonora", '{"acao":"iniciar"}', id_="a"), fc("terminal_executar", '{"comando":"dir"}', id_="b")])
checar([n for n, _ in r] == ["trilha_sonora", "terminal_executar"], "ids diferentes = chamadas diferentes")
r = juntar([fc("trilha_sonora", "{}"), fc("oficina_listar", "{}")])
checar([n for n, _ in r] == ["trilha_sonora", "oficina_listar"], "sem index nem id, com argumentos vazios ({}) também separa")
r = juntar([fc("terminal_executar", '{"coman', id_="x", index=0), fc(args='do":"Get-Date"}', index=0)])
checar(r == [("terminal_executar", {"comando": "Get-Date"})], f"argumentos em pedaços continuam a mesma chamada: {r}")
r = juntar([fc("terminal_", index=0), fc("executar", index=0), fc(args='{"comando":"dir"}', index=0)])
checar(r == [("terminal_executar", {"comando": "dir"})], f"nome em pedaços é juntado: {r}")
r = juntar([fc("a", '{"x":1}', index=0), fc("b", '{"y":2}', index=1), fc(args="", index=1)])
checar([n for n, _ in r] == ["a", "b"], "index diferentes (padrão OpenAI) continuam funcionando")

b = g.ToolUseBlock("id1", "terminal_executar", {}, "assinatura")
checar(b.name == "terminal_executar" and b.get("name") == "terminal_executar" and b.type == "tool_use", "bloco funciona como objeto e como dict")
txt = json.dumps([b, g.TextBlock("oi")])
checar("tool_use" in txt and "assinatura" not in txt, "blocos viram JSON (a reserva aceita) sem vazar a thought signature")
checar(b.thought_signature == "assinatura", "a thought signature continua guardada no bloco")
msgs = g._converter_mensagens([{"role": "user", "content": "roda"}, {"role": "assistant", "content": [g.TextBlock(""), b]},
                               {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "id1", "content": "ok"}]}])
tc = msgs[1]["tool_calls"][0]
checar(tc["function"]["name"] == "terminal_executar" and tc["function"]["arguments"] == "{}", "entrada vazia ({}) não quebra a conversão (era o AttributeError)")
checar(tc.get("extra_content", {}).get("google", {}).get("thought_signature") == "assinatura", "a thought signature volta para o Gemini")
checar(msgs[2] == {"role": "tool", "tool_call_id": "id1", "content": "ok"}, "resultado da ferramenta vai certo")

print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
sys.exit(0 if ok else 1)
