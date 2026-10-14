"""
Mede o tempo até o PRIMEIRO TEXTO do modelo (o que o Lucas sente como "demora") em variações do pedido, com o prompt REAL do Jarvis.
Gasta a chave da Anthropic (centavos: ~25 chamadas de ~4 mil tokens). Uso:  .venv\\Scripts\\python.exe -X utf8 scripts\\bench_llm.py
"""

import asyncio
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
os.environ["JARVIS_MEMORIA_DIR"] = tempfile.mkdtemp(prefix="jarvis_bench_")
os.environ["JARVIS_SEM_VOZ"] = "1"
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
import server  # noqa: E402
import roteador  # noqa: E402

PERGUNTAS = ["Que horas são agora?", "Qual a capital da França?", "Me conta uma curiosidade rápida sobre o espaço."]


def todas_ferramentas():
    return (server.ferramentas.definicoes(server.CFG.get("programas", {}), server.TEM_COFRE) + server.cerebro.definicoes(server.TEM_COFRE)
            + [server.camera.definicao(), server.direcao.definicao()] + server.navegador.definicoes() + server.interface.definicoes()
            + server.google_tools.definicoes(server.google_auth.conectado()) + [server.FERRAMENTA_ENCERRAR, server.FERRAMENTA_DORMIR, server.briefing.DEFINICAO, roteador.FERRAMENTA_HABILITAR])


def historia_falsa(n=6):
    h = []
    for i in range(n):
        h.append({"role": "user", "content": f"Pergunta número {i + 1} do chefe sobre agenda, projetos, e-mails e o que fazer hoje no escritório da loja de peças." + " detalhe" * 40})
        h.append({"role": "assistant", "content": f"Resposta número {i + 1}: claro, chefe. Vou resumir o que importa e deixar o resto para depois." + " ok" * 60})
    return h


def ferramentas_nucleo():
    todas = (server.ferramentas.definicoes(server.CFG.get("programas", {}), server.TEM_COFRE) + server.cerebro.definicoes(server.TEM_COFRE)
             + [server.camera.definicao(), server.direcao.definicao()] + server.navegador.definicoes() + server.interface.definicoes()
             + server.google_tools.definicoes(server.google_auth.conectado()) + [server.FERRAMENTA_ENCERRAR, server.FERRAMENTA_DORMIR, server.briefing.DEFINICAO, roteador.FERRAMENTA_HABILITAR])
    return roteador.filtrar(todas, {"nucleo"})


async def uma(variante, pergunta, ferr, estatico, dinamico):
    hist = historia_falsa() if variante.get("historia") else []
    msgs = hist + [{"role": "user", "content": pergunta}]
    if variante.get("cache_historia") and hist:
        ultimo = hist[-1]
        hist[-1] = {"role": ultimo["role"], "content": [{"type": "text", "text": ultimo["content"], "cache_control": {"type": "ephemeral", "ttl": "1h"}}]}
        msgs = hist + [{"role": "user", "content": pergunta}]
    kw = dict(model=server.MODELO, max_tokens=300, messages=msgs)
    ttl = {"type": "ephemeral", "ttl": "1h"} if variante.get("ttl1h") else {"type": "ephemeral"}
    if variante.get("sem_cache"):
        kw["system"] = estatico + "\n" + dinamico
        kw["tools"] = ferr
    else:
        kw["system"] = [{"type": "text", "text": estatico, "cache_control": ttl}, {"type": "text", "text": dinamico}]
        kw["tools"] = (ferr[:-1] + [{**ferr[-1], "cache_control": ttl}]) if ferr else []
    if variante.get("sem_ferramentas"):
        kw.pop("tools")
    if variante.get("esforco") is not None:
        kw["output_config"] = {"effort": variante["esforco"]}
    if variante.get("pensar") == "off":
        kw["thinking"] = {"type": "disabled"}
    if variante.get("modelo"):
        kw["model"] = variante["modelo"]
    t0 = time.perf_counter(); primeiro = None
    async with server.ai.messages.stream(**kw) as s:
        async for _ in s.text_stream:
            if primeiro is None:
                primeiro = time.perf_counter() - t0
        final = await s.get_final_message()
    uso = final.usage
    return primeiro, time.perf_counter() - t0, getattr(uso, "input_tokens", 0), getattr(uso, "cache_read_input_tokens", 0) or 0, getattr(uso, "cache_creation_input_tokens", 0) or 0


async def principal():
    estatico, dinamico = server.montar_sistema_partes("Que horas são?", {})
    ferr = ferramentas_nucleo()
    print(f"modelo {server.MODELO} | esforço {server.ESFORCO} | núcleo: {len(ferr)} ferramentas\n")
    variantes = [
        ("A. como está hoje (esforço low, cache 5 min, 19 ferramentas)", dict(esforco=server.ESFORCO)),
        ("B. A + cache de 1 hora", dict(esforco=server.ESFORCO, ttl1h=True)),
        ("C. B + sem 'pensar' (thinking desligado)", dict(esforco=server.ESFORCO, ttl1h=True, pensar="off")),
        ("D. B sem ferramentas (pergunta simples)", dict(esforco=server.ESFORCO, ttl1h=True, sem_ferramentas=True)),
        ("F. B com TODAS as 79 ferramentas (prefixo fixo)", dict(esforco=server.ESFORCO, ttl1h=True, todas=True)),
        ("G. B + histórico de 6 turnos SEM cache no histórico", dict(esforco=server.ESFORCO, ttl1h=True, historia=True)),
        ("H. B + histórico de 6 turnos COM cache no histórico", dict(esforco=server.ESFORCO, ttl1h=True, historia=True, cache_historia=True)),
    ]
    for nome, v in variantes:
        tempos = []
        try:
            f_use = todas_ferramentas() if v.get("todas") else ferr
            if v.get("todas"):
                f_use = roteador.filtrar(f_use, set(roteador.GRUPOS_ORDEM))
            await uma(v, "oi", f_use, estatico, dinamico)               # aquece o cache desta variante (não conta)
            for p in PERGUNTAS:
                tempos.append(await uma(v, p, f_use, estatico, dinamico))
        except Exception as e:
            print(f"{nome}\n    ERRO {type(e).__name__}: {str(e)[:160]}\n")
            continue
        t1 = [t[0] for t in tempos]
        print(f"{nome}\n    1º texto: mediana {statistics.median(t1) * 1000:.0f} ms (min {min(t1) * 1000:.0f}, máx {max(t1) * 1000:.0f}) | "
              f"total {statistics.median(t[1] for t in tempos) * 1000:.0f} ms | entrada sem cache {tempos[-1][2]}, lida do cache {tempos[-1][3]}, criada {tempos[-1][4]}\n")


asyncio.run(principal())
