"""
Voz do Gemini (TTS) com a mesma chave do cérebro: reserva GRATUITA e natural para quando a ElevenLabs falha ou acaba o crédito
(ordem: ElevenLabs -> Gemini -> Kokoro local -> voz do navegador). A emoção entra como marca de áudio no começo da frase ([excited] etc.).
Medido em 2026-10-25 nesta máquina: ~3,5 s por frase curta (a ElevenLabs leva ~0,8 s), sem streaming; cada modelo tem a SUA cota,
então ao dar 429 o próximo modelo da lista assume. Devolve WAV pronto (o Gemini já manda com cabeçalho) ou b"" se nada deu.
"""

import asyncio
import base64
import io
import time
import wave

import httpx

MODELOS = ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-3.1-flash-tts-preview"]
BASE = "https://generativelanguage.googleapis.com/v1beta/models"
# Marca de áudio por emoção do Jarvis. Medido: o modelo NÃO lê a marca em voz alta (instrução em texto corrido, sim: por isso não se usa).
TAGS = {"neutro": "", "animado": "[excited] ", "adrenalina": "[excited] ", "triunfante": "[proud] ", "preocupado": "[worried] ",
        "sarcastico": "[sarcastic] ", "serio": "[serious] ", "risada": "[laughs] ", "curioso": "[curious] ", "irritado": "[annoyed] ",
        "suspiro": "[sighs] "}
_suspenso: dict[str, float] = {}            # modelo -> até quando está sem cota / indisponível
_estado = {"cliente": None, "limite": None}


def _cliente() -> httpx.AsyncClient:
    if _estado["cliente"] is None:
        _estado["cliente"] = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=4, max_keepalive_connections=4, keepalive_expiry=300))
    return _estado["cliente"]


def _limite() -> asyncio.Semaphore:
    if _estado["limite"] is None:
        _estado["limite"] = asyncio.Semaphore(2)        # poucas frases ao mesmo tempo: a cota grátis é por minuto
    return _estado["limite"]


def _wav(pcm: bytes, taxa: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm)
    return buf.getvalue()


def _extrair(dados: dict) -> bytes:
    for p in (dados.get("candidates") or [{}])[0].get("content", {}).get("parts", []):
        inline = p.get("inlineData")
        if inline and inline.get("data"):
            audio = base64.b64decode(inline["data"])
            return audio if audio[:4] == b"RIFF" else _wav(audio)
    return b""


async def sintetizar(texto: str, emocao: str | None, chave: str, voz: str = "Orus", modelos: list[str] | None = None) -> bytes:
    """WAV da frase, ou b"" (aí a Kokoro/navegador falam)."""
    if not texto.strip() or len(chave) < 20:
        return b""
    corpo = {"contents": [{"parts": [{"text": TAGS.get(emocao or "neutro", "") + texto[:700]}]}],
             "generationConfig": {"responseModalities": ["AUDIO"],
                                  "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}}}}
    async with _limite():
        for modelo in (modelos or MODELOS):
            if _suspenso.get(modelo, 0.0) > time.monotonic():
                continue
            try:
                r = await _cliente().post(f"{BASE}/{modelo}:generateContent", json=corpo, headers={"x-goog-api-key": chave})
            except httpx.HTTPError as e:
                print(f"[jarvis] voz gemini: erro de rede {type(e).__name__}", flush=True)
                return b""
            if r.status_code == 200:
                try:
                    audio = _extrair(r.json())
                except Exception:
                    audio = b""
                if audio:
                    return audio
                continue                                   # respondeu sem áudio: tenta o próximo modelo
            if r.status_code == 429:
                diaria = "PerDay" in r.text
                _suspenso[modelo] = time.monotonic() + (3600 if diaria else 60)
                print(f"[jarvis] voz gemini: {modelo} sem cota ({'dia' if diaria else 'minuto'}); tentando o próximo", flush=True)
                continue
            _suspenso[modelo] = time.monotonic() + 600       # 400/404/5xx: deixa esse modelo de lado por um tempo
            print(f"[jarvis] voz gemini: {modelo} HTTP {r.status_code}", flush=True)
    return b""
