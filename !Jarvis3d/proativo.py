"""
Proatividade e rotinas: lembretes por voz, vigias de cotação, rotinas ("modo trabalho") com horário, alertas de agenda e e-mail importante.
O Jarvis FALA sozinho só quando o app está aberto e ele não está no meio de uma conversa; o que venceu com o app fechado é avisado ao abrir (até 3 h depois).
Tudo em memoria\\proativo.json (sem segredos). Nada aqui executa ação de risco: rotinas só abrem programas/sites, ajustam volume/tema, falam e pedem o briefing.
"""

import asyncio
import json
import re
import time
import uuid
from datetime import datetime, timedelta

import httpx

import caminhos

ARQ = caminhos.DADOS / "memoria" / "proativo.json"
PASSOS_OK = {"abrir_programa", "abrir_site", "volume", "tema", "modo", "falar", "esperar", "briefing"}
PAR = re.compile(r"^[A-Z]{3}-[A-Z]{3}$")

DEFINICOES = [
    {"name": "lembrete_voz",
     "description": "Cria um lembrete que o Jarvis FALA sozinho na hora certa (com o app aberto). Use 'em_minutos' (ex.: 20) para 'daqui a 20 minutos' ou 'data_hora' (ISO local, ex.: 2026-10-16T09:00) para um horário. 'repetir' opcional: diario ou semanal.",
     "input_schema": {"type": "object", "properties": {"texto": {"type": "string"}, "em_minutos": {"type": "number"}, "data_hora": {"type": "string"}, "repetir": {"type": "string", "enum": ["diario", "semanal"]}}, "required": ["texto"]}},
    {"name": "vigiar_cotacao",
     "description": "Vigia uma cotação e AVISA por voz quando passar do valor (uma vez). Pares no formato MOEDA-MOEDA: USD-BRL (dólar), EUR-BRL (euro), BTC-BRL (bitcoin), GBP-BRL... 'op' = acima ou abaixo.",
     "input_schema": {"type": "object", "properties": {"par": {"type": "string"}, "op": {"type": "string", "enum": ["acima", "abaixo"]}, "valor": {"type": "number"}}, "required": ["par", "op", "valor"]}},
    {"name": "rotina_salvar",
     "description": ("Salva uma ROTINA com nome (ex.: 'modo trabalho', 'bom dia', 'fim do expediente'): lista de passos executados em sequência sem pedir nada. "
                     "Passos: abrir_programa (valor = nome), abrir_site (valor = URL https), volume (valor = 0 a 100), tema (valor = cor), modo (valor = foco, moderno, completo, cinema), "
                     "falar (valor = frase), esperar (valor = segundos, máx. 30), briefing (resumo do dia). 'hora' (HH:MM) e 'dias' (0=segunda ... 6=domingo) fazem rodar sozinha todo dia."),
     "input_schema": {"type": "object", "properties": {"nome": {"type": "string"},
                                                        "passos": {"type": "array", "items": {"type": "object", "properties": {"tipo": {"type": "string", "enum": sorted(PASSOS_OK)}, "valor": {"type": "string"}}, "required": ["tipo"]}},
                                                        "hora": {"type": "string"}, "dias": {"type": "array", "items": {"type": "integer"}}}, "required": ["nome", "passos"]}},
    {"name": "rotina_executar", "description": "Executa uma rotina salva agora (pelo nome).",
     "input_schema": {"type": "object", "properties": {"nome": {"type": "string"}}, "required": ["nome"]}},
    {"name": "proativo_gerenciar",
     "description": "Lista ou cancela lembretes, vigias de cotação e rotinas. tipo: lembretes, vigias ou rotinas. acao: listar ou cancelar (cancelar usa 'id' do lembrete/vigia ou o 'nome' da rotina).",
     "input_schema": {"type": "object", "properties": {"tipo": {"type": "string", "enum": ["lembretes", "vigias", "rotinas"]}, "acao": {"type": "string", "enum": ["listar", "cancelar"]}, "id": {"type": "string"}}, "required": ["tipo", "acao"]}},
]
NOMES = {d["name"] for d in DEFINICOES}


# ---------------------------------------------------------------- estado
def _ler() -> dict:
    try:
        d = json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    d.setdefault("lembretes", []); d.setdefault("vigias", []); d.setdefault("rotinas", {}); d.setdefault("vistos", {})
    return d


def _gravar(d: dict):
    ARQ.parent.mkdir(parents=True, exist_ok=True)
    ARQ.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _quando(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")


def lembrete_add(texto: str, em_minutos: float | None = None, data_hora: str | None = None, repetir: str | None = None) -> str:
    texto = texto.strip()[:300]
    if not texto:
        raise ValueError("Faltou o texto do lembrete.")
    if em_minutos is not None:
        ts = time.time() + max(0.2, min(60 * 24 * 60, float(em_minutos))) * 60
    elif data_hora:
        try:
            dt = datetime.fromisoformat(str(data_hora))
        except ValueError:
            raise ValueError("Data/hora inválida: use ISO local, ex.: 2026-10-16T09:00.")
        ts = (dt if dt.tzinfo else dt.astimezone()).timestamp() if dt.tzinfo else dt.timestamp()
        if ts < time.time() - 60:
            raise ValueError("Esse horário já passou.")
    else:
        raise ValueError("Diga em quantos minutos ou a data e hora.")
    d = _ler()
    d["lembretes"].append({"id": uuid.uuid4().hex[:6], "quando": ts, "texto": texto, "repetir": repetir if repetir in ("diario", "semanal") else None})
    _gravar(d)
    return f"Lembrete criado para {_quando(ts)}: {texto}" + (f" (repete {repetir})" if repetir in ("diario", "semanal") else "")


def vigia_add(par: str, op: str, valor: float) -> str:
    par = par.strip().upper()
    if not PAR.match(par) or op not in ("acima", "abaixo"):
        raise ValueError("Par inválido: use algo como USD-BRL, EUR-BRL, BTC-BRL.")
    d = _ler()
    d["vigias"] = [v for v in d["vigias"] if len(d["vigias"]) < 12]
    d["vigias"].append({"id": uuid.uuid4().hex[:6], "par": par, "op": op, "valor": float(valor), "criado": time.time()})
    _gravar(d)
    return f"Vou avisar quando {par} ficar {op} de {valor:g}."


def rotina_salvar(nome: str, passos: list, hora: str | None = None, dias: list | None = None) -> str:
    nome = re.sub(r"\s+", " ", nome.strip().lower())[:40]
    limpos = []
    for p in (passos or [])[:20]:
        tipo = str(p.get("tipo", ""))
        valor = str(p.get("valor", ""))[:300]
        if tipo not in PASSOS_OK:
            raise ValueError(f"Passo desconhecido: {tipo}")
        if tipo == "abrir_site" and not valor.startswith(("http://", "https://")):
            raise ValueError("abrir_site precisa de uma URL http(s).")
        limpos.append({"tipo": tipo, "valor": valor})
    if not nome or not limpos:
        raise ValueError("Faltou o nome ou os passos.")
    agenda = None
    if hora:
        if not re.fullmatch(r"\d{1,2}:\d{2}", hora):
            raise ValueError("Hora no formato HH:MM.")
        agenda = {"hora": hora.zfill(5), "dias": [int(x) for x in (dias or range(7)) if 0 <= int(x) <= 6]}
    d = _ler()
    d["rotinas"][nome] = {"passos": limpos, "agenda": agenda, "ultima": ""}
    _gravar(d)
    return f"Rotina '{nome}' salva com {len(limpos)} passo(s)" + (f", todo dia às {agenda['hora']}." if agenda else ".")


def achar_rotina(texto: str) -> str | None:
    """'modo trabalho', 'rotina bom dia', 'executa a rotina X' -> nome da rotina salva (ou None)."""
    t = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", texto.lower())).strip()
    t = re.sub(r"^(jarvis )?(pode )?(executa|executar|roda|rodar|inicia|iniciar|ativa|ativar|faz|fazer)? ?(a |o )?(rotina|modo)? ?", "", t).strip()
    rot = _ler()["rotinas"]
    for nome in rot:
        if t == nome or t == re.sub(r"^(modo|rotina) ", "", nome):
            return nome
    return None


def gerenciar(entrada: dict) -> str:
    tipo, acao, id_ = entrada.get("tipo"), entrada.get("acao"), str(entrada.get("id") or "").strip().lower()
    d = _ler()
    if tipo == "lembretes":
        if acao == "listar":
            return "\n".join(f"[{l['id']}] {_quando(l['quando'])} — {l['texto']}" + (f" ({l['repetir']})" if l["repetir"] else "") for l in d["lembretes"]) or "Nenhum lembrete."
        n = len(d["lembretes"]); d["lembretes"] = [l for l in d["lembretes"] if l["id"] != id_]; _gravar(d)
        return "Lembrete cancelado." if len(d["lembretes"]) < n else "Não achei esse lembrete."
    if tipo == "vigias":
        if acao == "listar":
            return "\n".join(f"[{v['id']}] {v['par']} {v['op']} de {v['valor']:g}" for v in d["vigias"]) or "Nenhum vigia."
        n = len(d["vigias"]); d["vigias"] = [v for v in d["vigias"] if v["id"] != id_]; _gravar(d)
        return "Vigia cancelado." if len(d["vigias"]) < n else "Não achei esse vigia."
    if tipo == "rotinas":
        if acao == "listar":
            return "\n".join(f"{n}: {len(r['passos'])} passos" + (f", todo dia às {r['agenda']['hora']}" if r["agenda"] else "") for n, r in d["rotinas"].items()) or "Nenhuma rotina."
        nome = id_ or str(entrada.get("nome") or "").lower()
        if nome in d["rotinas"]:
            del d["rotinas"][nome]; _gravar(d)
            return "Rotina apagada."
        return "Não achei essa rotina."
    raise ValueError("Tipo inválido.")


def executar(nome: str, entrada: dict) -> str:
    if nome == "lembrete_voz":
        return lembrete_add(str(entrada.get("texto", "")), entrada.get("em_minutos"), entrada.get("data_hora"), entrada.get("repetir"))
    if nome == "vigiar_cotacao":
        return vigia_add(str(entrada.get("par", "")), str(entrada.get("op", "")), float(entrada.get("valor")))
    if nome == "rotina_salvar":
        return rotina_salvar(str(entrada.get("nome", "")), entrada.get("passos") or [], entrada.get("hora"), entrada.get("dias"))
    if nome == "proativo_gerenciar":
        return gerenciar(entrada)
    raise ValueError("Ferramenta desconhecida.")


# ---------------------------------------------------------------- o laço (roda no servidor)
async def _cotacao(par: str) -> float | None:
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            r = await cli.get(f"https://economia.awesomeapi.com.br/last/{par}")
            return float(r.json()[par.replace("-", "")]["bid"])
    except Exception:
        return None


async def verificar_uma_vez(anunciar, executar_rotina, google_ok, google_api, agora: float | None = None, checar_rede: bool = True) -> list[str]:
    """Um ciclo: lembretes vencidos, rotinas com horário, vigias (se `checar_rede`) e alertas do Google. `anunciar(texto) -> bool` diz se conseguiu falar."""
    feitos = []
    agora = agora or time.time()
    d = _ler()
    mudou = False
    # lembretes
    resto = []
    for l in d["lembretes"]:
        if l["quando"] > agora:
            resto.append(l)
            continue
        if agora - l["quando"] > 3 * 3600 and not l["repetir"]:
            mudou = True
            continue                                                      # venceu faz muito tempo (app fechado): descarta
        if await anunciar(f"Lembrete, {l['texto']}.", True):
            feitos.append("lembrete:" + l["id"]); mudou = True
            if l["repetir"]:
                l["quando"] += 86400 if l["repetir"] == "diario" else 7 * 86400
                resto.append(l)
        else:
            resto.append(l)
    d["lembretes"] = resto
    # rotinas agendadas
    dt = datetime.fromtimestamp(agora)
    for nome, r in d["rotinas"].items():
        ag = r.get("agenda")
        if not ag or dt.weekday() not in ag["dias"] or r.get("ultima") == dt.strftime("%Y-%m-%d"):
            continue
        h, m = map(int, ag["hora"].split(":"))
        alvo = dt.replace(hour=h, minute=m, second=0, microsecond=0)
        if alvo <= dt <= alvo + timedelta(minutes=90):
            if await executar_rotina(nome, r["passos"]):
                r["ultima"] = dt.strftime("%Y-%m-%d"); mudou = True; feitos.append("rotina:" + nome)
    # vigias de cotação
    if checar_rede:
        for v in list(d["vigias"]):
            preco = await _cotacao(v["par"])
            if preco is None:
                continue
            if (v["op"] == "acima" and preco > v["valor"]) or (v["op"] == "abaixo" and preco < v["valor"]):
                if await anunciar(f"Atenção: {v['par']} está em {preco:.2f}, {v['op']} de {v['valor']:g}."):
                    d["vigias"].remove(v); mudou = True; feitos.append("vigia:" + v["id"])
    # Google: compromisso nos próximos 15 min e e-mail importante novo
    if google_ok():
        try:
            from google_auth import AGENDA, ESC_AGENDA_LER, GMAIL, ESC_GMAIL_LER
            ini = datetime.now().astimezone()
            r = await google_api("GET", f"{AGENDA}/calendars/primary/events", params={"timeMin": ini.isoformat(), "timeMax": (ini + timedelta(minutes=16)).isoformat(), "singleEvents": "true", "orderBy": "startTime", "maxResults": 3}, escopo=ESC_AGENDA_LER)
            for e in r.get("items", []):
                chave = "ev:" + e["id"] + (e.get("start", {}).get("dateTime", ""))
                if chave in d["vistos"] or "dateTime" not in e.get("start", {}):
                    continue
                if await anunciar(f"Daqui a pouco: {e.get('summary', 'um compromisso')}."):
                    d["vistos"][chave] = agora; mudou = True; feitos.append("agenda:" + e["id"])
            r = await google_api("GET", f"{GMAIL}/messages", params={"q": "is:unread is:important newer_than:1d in:inbox", "maxResults": 3}, escopo=ESC_GMAIL_LER)
            for m in r.get("messages", []):
                chave = "mail:" + m["id"]
                if chave in d["vistos"]:
                    continue
                det = await google_api("GET", f"{GMAIL}/messages/{m['id']}", params={"format": "metadata", "metadataHeaders": ["From", "Subject"]}, escopo=ESC_GMAIL_LER)
                from google_util import cabecalho
                de = re.sub(r"<.*?>", "", cabecalho(det, "From")).strip().strip('"')[:40]
                assunto = cabecalho(det, "Subject")[:70]
                if await anunciar(f"E-mail importante de {de}: {assunto}."):
                    d["vistos"][chave] = agora; mudou = True; feitos.append("email:" + m["id"])
        except Exception:
            pass
    if len(d["vistos"]) > 400:
        d["vistos"] = dict(sorted(d["vistos"].items(), key=lambda kv: kv[1])[-200:])
    if mudou:
        _gravar(d)
    return feitos
