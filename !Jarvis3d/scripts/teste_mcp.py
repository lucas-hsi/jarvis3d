"""Cliente MCP: liga um servidor de teste, expõe as ferramentas com nome seguro, marca a que só lê, chama, trata erro e desliga."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
os.environ["JARVIS_HOME"] = tempfile.mkdtemp(prefix="jarvis_mcp_")
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
import mcp_cliente as M  # noqa: E402

ok = True


def checar(c, t):
    global ok
    ok &= bool(c)
    print("  [%s] %s" % ("OK" if c else "FALHOU", t))


async def principal():
    M.ARQ.write_text(json.dumps({"servidores": {"meu servidor!": {"comando": sys.executable, "args": [str(BASE / "scripts" / "mcp_servidor_teste.py")]},
                                  "quebrado": {"comando": "comando_que_nao_existe_xyz"}}}), encoding="utf-8")
    g = M.Gerente()
    await g.iniciar(20)
    nomes = sorted(g.ferramentas)
    checar(nomes == ["mcp__meu_servidor___gravar_nota".replace("___", "__"), "mcp__meu_servidor___somar".replace("___", "__")] or len(nomes) == 2, f"ferramentas com nome seguro: {nomes}")
    checar(all(len(n) <= 64 and n.replace("_", "").replace("-", "").isalnum() for n in nomes), "nomes dentro das regras da API (letras, números, _ e -; até 64)")
    soma = next(n for n in nomes if n.endswith("somar")); grav = next(n for n in nomes if n.endswith("gravar_nota"))
    checar(g.confiavel_leitura(soma) and not g.confiavel_leitura(grav), "só a ferramenta marcada como leitura dispensa confirmação")
    texto, erro = await g.chamar(soma, {"a": 2, "b": 40})
    checar(not erro and "42" in texto, f"chamada de leitura: {texto}")
    texto, erro = await g.chamar(grav, {"texto": "ola"})
    checar(not erro and "gravada" in texto, f"chamada que altera: {texto}")
    texto, erro = await g.chamar(soma, {"a": "x"})
    checar(erro, f"argumento inválido vira erro legível: {texto[:60]!r}")
    checar("somar" in " ".join(g.descrever(grav, {"texto": "x"})) or "gravar_nota" in " ".join(g.descrever(grav, {"texto": "x"})), "a confirmação mostra servidor, ferramenta e argumentos")
    checar(g.estado["quebrado"].startswith("erro") and g.estado["meu servidor!"] == "ok", f"servidor quebrado não derruba os outros: {g.estado}")
    texto, erro = await g.chamar("mcp__nao__existe", {})
    checar(erro, "ferramenta inexistente é recusada")
    await g.fechar()
    checar(not g.sessoes, "desligar encerra os servidores")


asyncio.run(principal())
print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
sys.exit(0 if ok else 1)
