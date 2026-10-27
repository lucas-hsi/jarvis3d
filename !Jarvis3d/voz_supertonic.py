"""
Voz LOCAL, gratuita e sem limite de uso: Supertonic 3 (ONNX, CPU, português). Voz principal quando a ElevenLabs não está disponível
(ordem: ElevenLabs -> Supertonic -> Gemini -> Kokoro -> navegador). Medido em 2026-10-25 nesta máquina: 1,5 a 2 s por frase de ~5 s (≈0,3x do
tempo real), sem streaming, sem emoção por marca (só a velocidade muda). Modelo (~385 MB) em memoria\\modelos\\supertonic3, baixado de
`~/.cache/supertonic3` ou por `scripts\\baixar_modelo_supertonic.py`; o Jarvis nunca baixa sozinho.
"""

import asyncio
import io
import threading
import wave

import numpy as np

import caminhos

VELOCIDADE = {"neutro": 1.05, "animado": 1.12, "adrenalina": 1.2, "triunfante": 1.1, "preocupado": 0.98, "sarcastico": 1.0, "serio": 0.97,
              "risada": 1.08, "curioso": 1.04, "irritado": 1.1, "suspiro": 0.95}
_s = {"tts": None, "falhou": False, "estilos": {}}
_trava = threading.Lock()
_fila = asyncio.Lock()


def pasta():
    return caminhos.DADOS / "memoria" / "modelos" / "supertonic3"


def disponivel() -> bool:
    return not _s["falhou"] and (pasta() / "config.json").exists() and (pasta() / "onnx").is_dir()


def _tts():
    with _trava:
        if _s["tts"] is None:
            from supertonic import TTS
            _s["tts"] = TTS(model="supertonic-3", model_dir=str(pasta()), auto_download=False, intra_op_num_threads=8)
        return _s["tts"]


def _estilo(tts, voz: str):
    if voz not in _s["estilos"]:
        _s["estilos"][voz] = tts.get_voice_style(voice_name=voz)
    return _s["estilos"][voz]


def _wav(audio: np.ndarray, taxa: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes((np.clip(np.asarray(audio, dtype=np.float32).squeeze(), -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def _sintetizar(texto: str, emocao: str | None, voz: str) -> bytes:
    tts = _tts()
    audio, _ = tts.synthesize(texto, voice_style=_estilo(tts, voz), lang="pt", speed=VELOCIDADE.get(emocao or "neutro", 1.05))
    return _wav(audio, tts.sample_rate)


async def sintetizar(texto: str, emocao: str | None = None, voz: str = "M1") -> bytes:
    """WAV em bytes, ou b"" se o modelo não está instalado/falhou (aí cai na próxima voz)."""
    if not texto.strip() or not disponivel():
        return b""
    try:
        async with _fila:                       # uma frase por vez: em paralelo disputariam a CPU
            return await asyncio.to_thread(_sintetizar, texto[:600], emocao, voz)
    except Exception as e:
        print(f"[jarvis] voz supertonic falhou ({type(e).__name__}: {str(e)[:80]})", flush=True)
        _s["falhou"] = True
        return b""
