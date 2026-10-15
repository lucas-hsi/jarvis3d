"""
Voz LOCAL e gratuita (Kokoro, ONNX int8, português do Brasil): reserva quando a ElevenLabs falha ou acaba o crédito, ou voz principal se `"voz_local": "preferir"`.
Roda na CPU (~0,35x tempo real aqui). Sem emoção por marca: só a velocidade muda. Modelos em memoria\\modelos\\voz (baixados em /configurar, nunca sozinho).
"""

import asyncio
import io
import threading
import wave

import numpy as np

import caminhos

ARQUIVOS = ("kokoro-v1.0.int8.onnx", "voices-v1.0.bin")
URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
VELOCIDADE = {"neutro": 1.05, "animado": 1.12, "adrenalina": 1.2, "triunfante": 1.1, "preocupado": 0.98, "sarcastico": 1.0, "serio": 0.97, "risada": 1.08,
              "curioso": 1.04, "irritado": 1.1, "suspiro": 0.95}
_k = {"m": None, "falhou": False}
_trava = threading.Lock()


def pasta():
    return caminhos.DADOS / "memoria" / "modelos" / "voz"


def disponivel() -> bool:
    return not _k["falhou"] and all((pasta() / a).exists() for a in ARQUIVOS)


def _modelo():
    with _trava:
        if _k["m"] is None:
            from kokoro_onnx import Kokoro
            _k["m"] = Kokoro(str(pasta() / ARQUIVOS[0]), str(pasta() / ARQUIVOS[1]))
        return _k["m"]


def _wav(audio: np.ndarray, taxa: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def _sintetizar(texto: str, emocao: str | None, voz: str) -> bytes:
    audio, taxa = _modelo().create(texto, voice=voz, speed=VELOCIDADE.get(emocao or "neutro", 1.05), lang="pt-br")
    return _wav(audio, taxa)


async def sintetizar(texto: str, emocao: str | None = None, voz: str = "pm_alex") -> bytes:
    """WAV em bytes, ou b"" se a voz local não está instalada/falhou (aí o navegador fala com a voz dele)."""
    if not texto.strip() or not disponivel():
        return b""
    try:
        return await asyncio.to_thread(_sintetizar, texto[:600], emocao, voz)
    except Exception as e:
        print(f"[jarvis] voz local falhou ({type(e).__name__}: {str(e)[:80]})", flush=True)
        _k["falhou"] = True
        return b""
