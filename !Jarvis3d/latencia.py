"""
Medição de tempo por etapa de cada turno (fase 1: só observa, não muda comportamento).

Uma linha JSON por turno em memoria/latencia.jsonl. Guarda tempos, nomes de ferramentas e contagens
de tokens/caracteres; NUNCA o texto da conversa. Qualquer falha aqui é engolida: medir não pode
derrubar um turno. Resumo: .venv\\Scripts\\python.exe scripts\\latencia_resumo.py
"""

import contextvars
import json
import os
import time
from pathlib import Path

import caminhos

PASTA = Path(os.environ.get("JARVIS_MEMORIA_DIR") or caminhos.DADOS / "memoria")
ARQUIVO = PASTA / "latencia.jsonl"
MAX_BYTES = 2_000_000          # passou disso, o arquivo antigo vira .velho (guarda uma geração)

ATUAL: contextvars.ContextVar["Turno | None"] = contextvars.ContextVar("turno_latencia", default=None)


def _ms(desde: float) -> int:
    return round((time.perf_counter() - desde) * 1000)


class Turno:
    def __init__(self, ativacao: bool, caracteres: int):
        self.t0 = time.perf_counter()
        self.inicio = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.ativacao = ativacao
        self.caracteres = caracteres
        self.marcas: dict[str, int] = {}       # nome -> ms desde o início do turno (1ª ocorrência)
        self.rodadas: list[dict] = []          # uma por chamada ao modelo
        self.ferramentas: list[dict] = []
        self.vozes: list[dict] = []
        self.eventos: list[str] = []           # o que deu errado ou fugiu do normal neste turno

    def marca(self, nome: str):
        self.marcas.setdefault(nome, _ms(self.t0))

    def rodada(self, ms_primeiro_token: int | None, ms_total: int, uso, parada: str | None, n_ferramentas: int | None = None):
        self.rodadas.append({
            "primeiro_token_ms": ms_primeiro_token, "total_ms": ms_total, "parada": parada, "ferramentas_enviadas": n_ferramentas,
            "tokens_entrada": getattr(uso, "input_tokens", None),
            "tokens_saida": getattr(uso, "output_tokens", None),
            "cache_lido": getattr(uso, "cache_read_input_tokens", None),
            "cache_criado": getattr(uso, "cache_creation_input_tokens", None),
        })

    def ferramenta(self, nome: str, ms: int, erro: bool, espera_confirmacao: bool):
        self.ferramentas.append({"nome": nome, "ms": ms, "erro": erro, "pode_esperar_usuario": espera_confirmacao})

    def voz(self, caracteres: int, ms_fila: int, ms_rede: int):
        self.vozes.append({"caracteres": caracteres, "fila_ms": ms_fila, "rede_ms": ms_rede})

    def salvar(self, concluido: bool):
        try:
            self.marca("fim")
            linha = {
                "inicio": self.inicio, "ativacao": self.ativacao, "caracteres_entrada": self.caracteres,
                "concluido": concluido, "eventos": self.eventos, "marcas_ms": self.marcas, "rodadas": self.rodadas,
                "ferramentas": self.ferramentas, "vozes": self.vozes,
            }
            PASTA.mkdir(parents=True, exist_ok=True)
            if ARQUIVO.exists() and ARQUIVO.stat().st_size > MAX_BYTES:
                ARQUIVO.replace(ARQUIVO.with_suffix(".velho"))
            with ARQUIVO.open("a", encoding="utf-8") as f:
                f.write(json.dumps(linha, ensure_ascii=False) + "\n")
        except Exception:
            pass


def registrar_cliente(msg: dict):
    """Tempos medidos pelo navegador (o servidor não os vê). Só números inteiros e limitados; nada do texto da conversa."""
    try:
        campos = ("final_apos_parcial_ms", "envio_ate_fala_ms", "envio_ate_audio_ms", "chegada_ate_audio_ms", "stt_audio_ms", "stt_transcricao_ms")
        linha = {"cliente": True, "quando": time.strftime("%Y-%m-%dT%H:%M:%S")}
        for c in campos:
            v = msg.get(c)
            linha[c] = int(v) if isinstance(v, (int, float)) and 0 <= v < 600000 else None
        PASTA.mkdir(parents=True, exist_ok=True)
        with ARQUIVO.open("a", encoding="utf-8") as f:
            f.write(json.dumps(linha) + "\n")
    except Exception:
        pass


def iniciar(ativacao: bool, caracteres: int) -> Turno:
    """Cria o turno e o deixa visível (via contextvar) para as tarefas criadas daqui em diante."""
    turno = Turno(ativacao, caracteres)
    ATUAL.set(turno)
    return turno


def evento(nome: str):
    turno = ATUAL.get()
    if turno is not None and len(turno.eventos) < 20:
        turno.eventos.append(nome[:80])


def marca(nome: str):
    turno = ATUAL.get()
    if turno is not None:
        turno.marca(nome)


def voz(caracteres: int, ms_fila: int, ms_rede: int):
    turno = ATUAL.get()
    if turno is not None:
        turno.voz(caracteres, ms_fila, ms_rede)
