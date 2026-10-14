"""
Teste de ponta a ponta DENTRO do app Electron: o "microfone" é um arquivo de áudio com uma frase em português (voz offline do
Windows), tocado pelo microfone falso do Chromium. Passa por: captura com cancelamento de eco -> AudioWorklet (16 kHz) ->
WebSocket binário -> servidor (detecção de fala + Whisper na NVIDIA) -> texto -> regras da interface (nome "Jarvis") -> fala
que iria ao modelo (capturada, NÃO enviada: sem gasto de API).

Uso:  .venv\\Scripts\\python.exe -X utf8 scripts\\teste_voz_casca.py
"""

import json
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="jarvis_vozcasca_"))
FRASE = "Jarvis, toca Back in Black do AC DC no YouTube"


def gerar_audio() -> Path:
    bruto = TMP / "frase.wav"
    ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.SelectVoice('Microsoft Maria Desktop'); "
          "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono); "
          f"$s.SetOutputToWaveFile('{bruto}', $f); $s.Speak('{FRASE}'); $s.SetOutputToNull();")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=120)
    with wave.open(str(bruto), "rb") as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    rng = np.random.default_rng(1)
    ruido = lambda seg: (rng.standard_normal(int(seg * 16000)) * 10 ** (-66 / 20) * 32767).astype(np.int16)  # noqa: E731
    final = np.concatenate([ruido(2.0), x, ruido(3.0)])
    arq = TMP / "microfone_falso.wav"
    with wave.open(str(arq), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(final.tobytes())
    return arq


def principal():
    arq = gerar_audio()
    electron = BASE / "desktop" / "node_modules" / "electron" / "dist" / "electron.exe"
    if not electron.exists():
        sys.exit("Electron não instalado (cd desktop && npm install).")
    env = dict(os.environ, JARVIS_TESTE_AUDIO=str(arq), JARVIS_PORTA="8356", JARVIS_MEMORIA_DIR=str(TMP / "mem"), JARVIS_SEM_VOZ="1",
               PYTHONUTF8="1")
    r = subprocess.run([str(electron), str(BASE / "desktop"), "--teste-voz", f"--user-data-dir={TMP / 'ud'}"], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180, env=env, cwd=str(BASE / "desktop"))
    linha = next((l for l in r.stdout.splitlines() if l.startswith("RESULTADO_VOZ ")), None)
    if not linha:
        print("sem resultado. Saída do Electron:\n", r.stdout[-1500:], r.stderr[-800:])
        sys.exit(1)
    d = json.loads(linha.split(" ", 1)[1])
    ok = True

    def checar(cond, texto):
        nonlocal ok
        ok &= bool(cond)
        print("  [%s] %s" % ("OK" if cond else "FALHOU", texto))

    print("VOZ DENTRO DO ELECTRON (microfone falso)")
    checar(d.get("servidor"), "servidor ligado pela casca")
    checar(d.get("motor") == "local", f"motor de voz = {d.get('motor')} (no Electron tem que ser o próprio)")
    checar(d.get("sttPronto"), "o servidor avisou que a escuta própria está pronta")
    checar((d.get("quadros") or 0) > 100, f"o navegador mandou {d.get('quadros')} quadros de áudio de 20 ms")
    cap = d.get("capturadas") or []
    checar(len(cap) == 1 and cap[0].get("tipo") == "fala", f"a interface entregou UMA fala ao servidor (capturadas: {len(cap)})")
    if not cap:
        print("   recentes:", json.dumps(d.get("recentes"), ensure_ascii=False)[:900])
    if cap:
        texto = cap[0].get("texto", "")
        print(f"      texto reconhecido: \"{texto}\"   (após {d.get('apos_ms')} ms desde ligar a escuta; o áudio tem 2 s de silêncio + a frase + 3 s de silêncio)")
        checar("toca" in texto.lower() and "black" in texto.lower(), "reconheceu a frase pedida")
    if d.get("erro"):
        print("      erro:", d["erro"])
    print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    principal()
