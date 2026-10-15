"""Custo estimado das chamadas aos modelos (US$), por dia, em memoria\\custos.jsonl. Serve para o teto diário do roteador de modelos e para o painel."""

import json
import time
from collections import defaultdict
from pathlib import Path

import caminhos

# US$ por 1M de tokens: (entrada sem cache, entrada em cache, saída). DeepSeek: tabela oficial (horário de pico é 2x; usa-se o pico por segurança).
PRECOS = {
    "deepseek-flash": (0.30, 0.006, 1.20),
    "deepseek-v4-pro": (1.32, 0.044, 3.96),
    "claude-haiku-5-5": (1.00, 0.10, 5.00),          # estimativa
    "claude-sonnet-5-5": (3.00, 0.30, 15.00),         # estimativa
}
ARQ = caminhos.DADOS / "memoria" / "custos.jsonl"
_hoje: dict = {"dia": "", "total": 0.0, "por_modelo": defaultdict(float)}


def _dia() -> str:
    return time.strftime("%Y-%m-%d")


def _carregar():
    if _hoje["dia"] == _dia():
        return
    _hoje.update(dia=_dia(), total=0.0, por_modelo=defaultdict(float))
    try:
        for linha in ARQ.read_text(encoding="utf-8").splitlines()[-4000:]:
            d = json.loads(linha)
            if d.get("dia") == _hoje["dia"]:
                _hoje["total"] += d["usd"]
                _hoje["por_modelo"][d["modelo"]] += d["usd"]
    except (OSError, ValueError):
        pass


def registrar(modelo: str, uso) -> float:
    """Soma o custo de uma resposta (objeto `usage` da API) e devolve o valor em US$."""
    if uso is None:
        return 0.0
    entrada = getattr(uso, "input_tokens", 0) or 0
    cache = getattr(uso, "cache_read_input_tokens", 0) or 0
    saida = getattr(uso, "output_tokens", 0) or 0
    p = PRECOS.get(modelo) or PRECOS["deepseek-flash"]
    usd = (max(0, entrada - cache) * p[0] + cache * p[1] + saida * p[2]) / 1e6
    _carregar()
    _hoje["total"] += usd
    _hoje["por_modelo"][modelo] += usd
    try:
        ARQ.parent.mkdir(parents=True, exist_ok=True)
        with open(ARQ, "a", encoding="utf-8") as f:
            f.write(json.dumps({"dia": _hoje["dia"], "modelo": modelo, "usd": round(usd, 6), "in": entrada, "cache": cache, "out": saida}) + "\n")
    except OSError:
        pass
    return usd


def hoje() -> dict:
    _carregar()
    return {"usd": round(_hoje["total"], 4), "por_modelo": {k: round(v, 4) for k, v in _hoje["por_modelo"].items()}}


def dentro_do_orcamento(limite_usd: float) -> bool:
    _carregar()
    return _hoje["total"] < limite_usd
