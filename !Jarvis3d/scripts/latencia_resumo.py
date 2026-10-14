"""
Resume memoria/latencia.jsonl: onde o tempo de cada turno é gasto.

Uso:  .venv\\Scripts\\python.exe scripts\\latencia_resumo.py [--ultimos N] [--arquivo CAMINHO]

"Sentido" do Lucas = do servidor receber o texto até o primeiro áudio chegar ao navegador. Não inclui
o tempo do reconhecimento de voz do Chrome (até ele decidir que você parou de falar) nem o de decodificar
o áudio; esses ficam no navegador e a fase 1 ainda não mede.
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def pct(valores: list[float], p: float) -> float:
    v = sorted(valores)
    return v[min(len(v) - 1, int(round(p * (len(v) - 1))))]


def linha(rotulo: str, valores: list[float], unidade: str = "ms"):
    if not valores:
        print(f"  {rotulo:<38} (sem dados)")
        return
    print(f"  {rotulo:<38} n={len(valores):<4} mediana={statistics.median(valores):>7.0f}{unidade}  p90={pct(valores, 0.9):>7.0f}{unidade}  máx={max(valores):>7.0f}{unidade}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ultimos", type=int, default=200)
    ap.add_argument("--arquivo", default=str(BASE / "memoria" / "latencia.jsonl"))
    a = ap.parse_args()
    arq = Path(a.arquivo)
    if not arq.exists():
        sys.exit(f"Sem dados ainda: {arq} não existe. Converse com o Jarvis (já reiniciado) e rode de novo.")
    turnos, cliente = [], []
    for texto in arq.read_text(encoding="utf-8").splitlines()[-a.ultimos * 2:]:
        try:
            entrada = json.loads(texto)
        except json.JSONDecodeError:
            continue
        (cliente if entrada.get("cliente") else turnos).append(entrada)
    turnos = turnos[-a.ultimos:]
    conversas = [t for t in turnos if not t.get("ativacao")]
    print(f"{len(turnos)} turnos lidos ({len(conversas)} conversas, {len(turnos) - len(conversas)} saudações). Concluídos: {sum(1 for t in turnos if t['concluido'])}.")

    for nome, grupo in (("CONVERSAS", conversas), ("SAUDAÇÕES (palmas)", [t for t in turnos if t.get("ativacao")])):
        if not grupo:
            continue
        print(f"\n{nome}")
        m = lambda k: [t["marcas_ms"][k] for t in grupo if k in t["marcas_ms"]]  # noqa: E731
        linha("prompt montado (memória + cofre)", m("prompt_montado"))
        linha("1º token do modelo (desde o turno)", m("primeiro_token"))
        linha("1ª frase pronta", m("primeira_frase"))
        linha("1º ÁUDIO enviado ao navegador", m("primeiro_audio_enviado"))
        linha("turno inteiro", m("fim"))

        rodadas = [r for t in grupo for r in t["rodadas"]]
        print("  -- chamadas ao modelo")
        linha("1º token (por chamada)", [r["primeiro_token_ms"] for r in rodadas if r["primeiro_token_ms"] is not None])
        linha("duração total (por chamada)", [r["total_ms"] for r in rodadas])
        linha("tokens de entrada (por chamada)", [r["tokens_entrada"] for r in rodadas if r["tokens_entrada"] is not None], "")
        lidos = [r["cache_lido"] or 0 for r in rodadas]
        print(f"  {'tokens lidos do cache':<38} total={sum(lidos)} (0 = sem cache de prompt)")
        print(f"  {'chamadas por turno':<38} mediana={statistics.median([len(t['rodadas']) for t in grupo]):.0f}  máx={max(len(t['rodadas']) for t in grupo)}")

        vozes = [v for t in grupo for v in t["vozes"]]
        print("  -- voz (ElevenLabs)")
        linha("espera na fila (limite de 2 simultâneas)", [v["fila_ms"] for v in vozes])
        linha("pedido de rede por frase", [v["rede_ms"] for v in vozes])
        linha("caracteres por frase", [v["caracteres"] for v in vozes], "")

    if cliente:
        print("\nNAVEGADOR (o que o servidor não vê)")
        c = lambda k: [x[k] for x in cliente if x.get(k) is not None]  # noqa: E731
        linha("Chrome: último parcial → texto final", c("final_apos_parcial_ms"))
        linha("enviou a fala → 1ª frase chegou", c("envio_ate_fala_ms"))
        linha("enviou a fala → áudio COMEÇOU a tocar", c("envio_ate_audio_ms"))
        linha("chegada da 1ª frase → começar a tocar", c("chegada_ate_audio_ms"))

    ferr: dict[str, list[int]] = {}
    for t in turnos:
        for f in t["ferramentas"]:
            ferr.setdefault(f["nome"], []).append(f["ms"])
    if ferr:
        print("\nFERRAMENTAS (inclui espera do usuário quando pede confirmação)")
        for nome, vs in sorted(ferr.items(), key=lambda kv: -statistics.median(kv[1]))[:12]:
            linha(nome, vs)


if __name__ == "__main__":
    main()
