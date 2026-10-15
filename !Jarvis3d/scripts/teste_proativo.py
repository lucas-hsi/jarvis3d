"""Proatividade: lembretes (vencer, repetir, não perder se ninguém ouviu), rotinas com horário (1x por dia), vigia de cotação, alertas do Google e o que o usuário pode fazer por voz."""
import asyncio
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
os.environ["JARVIS_HOME"] = tempfile.mkdtemp(prefix="jarvis_pro_")
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
import proativo as P  # noqa: E402

ok = True


def checar(c, t):
    global ok
    ok &= bool(c)
    print("  [%s] %s" % ("OK" if c else "FALHOU", t))


falas, rotinas = [], []
ouvindo = {"v": True}


async def anunciar(texto, urgente=False):
    if not ouvindo["v"]:
        return False
    falas.append(texto)
    return True


async def rotina(nome, passos):
    rotinas.append(nome)
    return True


async def sem_google(*a, **k):
    return {}


async def ciclo(agora=None, google=lambda: False, api=sem_google, rede=False):
    return await P.verificar_uma_vez(anunciar, rotina, google, api, agora=agora, checar_rede=rede)


async def principal():
    print("LEMBRETES")
    r = P.lembrete_add("tirar o bolo", em_minutos=0.2)
    checar("Lembrete criado" in r, r)
    await ciclo()
    checar(not falas, "ainda não venceu: não fala")
    await ciclo(agora=time.time() + 30)
    checar(falas == ["Lembrete, tirar o bolo."], f"venceu: fala uma vez {falas}")
    await ciclo(agora=time.time() + 60)
    checar(len(falas) == 1, "não repete o que já falou")
    P.lembrete_add("remédio", em_minutos=0.2)
    ouvindo["v"] = False
    await ciclo(agora=time.time() + 30)
    checar("remédio" not in " ".join(falas) and len(P._ler()["lembretes"]) == 1, "ninguém ouviu: mantém o lembrete para tentar de novo")
    ouvindo["v"] = True
    await ciclo(agora=time.time() + 31)
    checar(any("remédio" in f for f in falas) and not P._ler()["lembretes"], "voltou a poder falar: avisa e remove")
    P.lembrete_add("academia", em_minutos=0.2, repetir="diario")
    await ciclo(agora=time.time() + 30)
    l = P._ler()["lembretes"]
    checar(len(l) == 1 and l[0]["quando"] > time.time() + 80000, "lembrete diário reagenda para amanhã")
    d = P._ler(); d["lembretes"] = [{"id": "velho", "quando": time.time() - 4 * 3600, "texto": "velho", "repetir": None}]; P._gravar(d)
    n = len(falas)
    await ciclo()
    checar(len(falas) == n and not P._ler()["lembretes"], "lembrete vencido há mais de 3 h é descartado sem falar")
    for ruim in ({"texto": "x"}, {"texto": "x", "data_hora": "ontem"}):
        try:
            P.executar("lembrete_voz", ruim); checar(False, f"deveria recusar {ruim}")
        except ValueError:
            checar(True, f"recusa lembrete inválido {ruim}")

    print("ROTINAS")
    P.rotina_salvar("Modo Trabalho", [{"tipo": "abrir_programa", "valor": "chrome"}, {"tipo": "falar", "valor": "Bom trabalho"}])
    checar(P.achar_rotina("modo trabalho") == "modo trabalho" and P.achar_rotina("executa a rotina trabalho") == "modo trabalho" and P.achar_rotina("abre o chrome") is None, "acha a rotina pelo nome falado e ignora frases comuns")
    try:
        P.rotina_salvar("x", [{"tipo": "terminal", "valor": "del *"}]); checar(False, "passo perigoso deve ser recusado")
    except ValueError:
        checar(True, "passo desconhecido (terminal) é recusado: rotinas não rodam comandos")
    try:
        P.rotina_salvar("x", [{"tipo": "abrir_site", "valor": "file:///c:/"}]); checar(False, "URL não-http deve ser recusada")
    except ValueError:
        checar(True, "abrir_site só aceita http(s)")
    agora = datetime.now()
    P.rotina_salvar("bom dia", [{"tipo": "falar", "valor": "Bom dia"}], hora=agora.strftime("%H:%M"), dias=[agora.weekday()])
    await ciclo()
    await ciclo()
    checar(rotinas.count("bom dia") == 1, "rotina agendada roda UMA vez no dia")
    P.rotina_salvar("noite", [{"tipo": "falar", "valor": "x"}], hora="03:00", dias=list(range(7)))
    await ciclo(agora=datetime.now().replace(hour=14, minute=0).timestamp())
    checar("noite" not in rotinas, "fora do horário não roda")

    print("VIGIA DE COTAÇÃO")
    P.vigia_add("USD-BRL", "acima", 5.50)
    async def preco(par): return 5.40
    P._cotacao = preco
    await ciclo(rede=True)
    checar(len(P._ler()["vigias"]) == 1, "abaixo do alvo: não avisa")
    async def preco2(par): return 5.61
    P._cotacao = preco2
    await ciclo(rede=True)
    checar(any("USD-BRL" in f and "5.61" in f for f in falas) and not P._ler()["vigias"], "passou do alvo: avisa e encerra o vigia")
    try:
        P.vigia_add("dolar", "acima", 5); checar(False, "par inválido")
    except ValueError:
        checar(True, "par inválido é recusado")

    print("GOOGLE (agenda e e-mail)")
    chamadas = []
    async def api(metodo, url, **k):
        chamadas.append(url)
        if "calendars" in url:
            return {"items": [{"id": "e1", "summary": "Reunião com o time", "start": {"dateTime": "2026-10-16T10:00:00-03:00"}}]}
        if url.endswith("/messages"):
            return {"messages": [{"id": "m1"}]}
        return {"payload": {"headers": [{"name": "From", "value": "Ana <ana@x.com>"}, {"name": "Subject", "value": "Contrato assinado"}]}}
    await ciclo(google=lambda: True, api=api)
    checar(any("Reunião com o time" in f for f in falas) and any("Ana" in f and "Contrato assinado" in f for f in falas), "avisa compromisso próximo e e-mail importante")
    n = len(falas)
    await ciclo(google=lambda: True, api=api)
    checar(len(falas) == n, "não repete o mesmo aviso")

    print("GERENCIAR")
    P.lembrete_add("teste", em_minutos=500)
    idl = P._ler()["lembretes"][0]["id"]
    checar("teste" in P.gerenciar({"tipo": "lembretes", "acao": "listar"}) and "cancelado" in P.gerenciar({"tipo": "lembretes", "acao": "cancelar", "id": idl}), "lista e cancela lembrete")
    checar("modo trabalho" in P.gerenciar({"tipo": "rotinas", "acao": "listar"}), "lista rotinas")


asyncio.run(principal())
print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
sys.exit(0 if ok else 1)
