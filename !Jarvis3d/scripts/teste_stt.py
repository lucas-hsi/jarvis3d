"""
Testa o reconhecimento de voz próprio (stt.py) de ponta a ponta, sem microfone: frases em português geradas pela voz offline
do Windows (SAPI) são tratadas como se viessem do microfone.

  1) Segmentador: acha começo e fim da fala (2 frases separadas, pausa curta no meio, clique, ruído de fundo, sala barulhenta)
  2) Whisper real: velocidade, dispositivo (NVIDIA ou CPU), acerto e filtro de alucinação em ruído
  3) SessaoSTT: o fluxo de quadros de 20 ms até o evento `transcricao`
  4) Servidor: WebSocket com quadros binários, como a interface vai mandar

Uso:  .venv\\Scripts\\python.exe -X utf8 scripts\\teste_stt.py
"""

import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.request
import wave
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import stt  # noqa: E402

ok = True
TMP = Path(tempfile.mkdtemp(prefix="jarvis_stt_"))
FRASES = [
    "Jarvis, toca Back in Black do AC DC no YouTube",
    "Quais são os meus compromissos de amanhã de manhã?",
    "Organiza a minha pasta de downloads e me avisa quando terminar",
    "Para",
]


def checar(cond, texto):
    global ok
    ok &= bool(cond)
    print("  [%s] %s" % ("OK" if cond else "FALHOU", texto))


def gerar_amostras():
    ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          "$s.SelectVoice('Microsoft Maria Desktop'); $f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono); ")
    for i, f in enumerate(FRASES):
        ps += f"$s.SetOutputToWaveFile('{TMP / f'f{i}.wav'}', $f); $s.Speak('{f}'); $s.SetOutputToNull(); "
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=120)
    saida = []
    for i in range(len(FRASES)):
        with wave.open(str(TMP / f"f{i}.wav"), "rb") as w:
            saida.append(np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768)
    return [aparar(x) for x in saida]


def aparar(x, limite_db=-48.0):
    """Tira o silêncio que a voz sintética embute no começo e no fim (senão a 'pausa' do teste é maior que a combinada)."""
    q = len(x) // 320 * 320
    db = 20 * np.log10(np.sqrt((x[:q].reshape(-1, 320) ** 2).mean(axis=1)) + 1e-7)
    ativos = np.where(db > limite_db)[0]
    return x[ativos[0] * 320: (ativos[-1] + 1) * 320] if len(ativos) else x


def ruido(seg, db=-65.0, semente=0):
    rng = np.random.default_rng(semente)
    return (rng.standard_normal(int(seg * stt.TAXA)) * 10 ** (db / 20)).astype(np.float32)


def palavras(t):
    return re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower())


def acerto(ref, hip):
    r, h = palavras(ref), palavras(hip)
    d = list(range(len(h) + 1))
    for i, a in enumerate(r, 1):
        novo = [i]
        for j, b in enumerate(h, 1):
            novo.append(min(d[j] + 1, novo[-1] + 1, d[j - 1] + (a != b)))
        d = novo
    return max(0.0, 1 - d[-1] / max(1, len(r)))


def eventos(x, **kw):
    seg = stt.Segmentador(**kw)
    return seg.alimentar(x)


def segmentacao(audios):
    print("1) SEGMENTADOR (começo e fim da fala)")
    f0, f1, f2, f3 = audios
    x = np.concatenate([ruido(1), f0, ruido(1.2, semente=1), f1, ruido(1.2, semente=2)])
    fins = [e for e in eventos(x) if e[0] == "fim"]
    checar(len(fins) == 2, f"duas frases separadas por 1,2 s viram 2 trechos (achou {len(fins)})")
    if len(fins) == 2:
        for (e, ref) in zip(fins, (f0, f1)):
            dur, esperado = e[2] / 1000, len(ref) / stt.TAXA
            checar(0.9 * esperado <= dur <= esperado + 1.0, f"duração do trecho coerente: {dur:.1f} s (frase de {esperado:.1f} s)")
    x = np.concatenate([ruido(1), f0, ruido(0.4, semente=3), f1, ruido(1.2, semente=4)])
    fins = [e for e in eventos(x) if e[0] == "fim"]
    checar(len(fins) == 1, f"pausa de 0,4 s DENTRO da fala não corta em dois (achou {len(fins)})")
    clique = np.zeros(int(0.06 * stt.TAXA), dtype=np.float32) + 0.3 * np.random.default_rng(5).standard_normal(int(0.06 * stt.TAXA)).astype(np.float32)
    x = np.concatenate([ruido(1), clique, ruido(1.5, semente=6)])
    checar(not [e for e in eventos(x) if e[0] == "fim"], "um clique de 60 ms não vira fala")
    checar(not eventos(ruido(6, -62.0, 7)), "ruído de fundo constante (-62 dBFS) não dispara nada")
    x = np.concatenate([ruido(3, -50.0, 8), f2, ruido(1.2, -50.0, 9)])
    fins = [e for e in eventos(x) if e[0] == "fim"]
    checar(len(fins) == 1, f"sala barulhenta (-50 dBFS): a fala ainda é achada (achou {len(fins)})")
    x = np.concatenate([ruido(1), f3, ruido(1.2, semente=10)])
    fins = [e for e in eventos(x) if e[0] == "fim"]
    checar(len(fins) == 1, f"palavra curta ('Para', {len(f3) / stt.TAXA:.1f} s) é achada (achou {len(fins)})")
    # blocos de tamanho irregular (como chegam do navegador)
    seg = stt.Segmentador()
    x = np.concatenate([ruido(1), f1, ruido(1.2, semente=11)])
    cont, i = [], 0
    rng = np.random.default_rng(12)
    while i < len(x):
        n = int(rng.integers(100, 900))
        cont += seg.alimentar(x[i:i + n])
        i += n
    checar(len([e for e in cont if e[0] == "fim"]) == 1, "blocos de tamanhos irregulares dão o mesmo resultado")


def p90_voz(x):
    q = len(x) // 320 * 320
    db = 20 * np.log10(np.sqrt((x[:q].reshape(-1, 320) ** 2).mean(axis=1)) + 1e-7)
    return float(np.percentile(db[db > -50], 90))


def escalar(x, alvo_db):
    """Ajusta o volume para que o nível da voz (p90 dos quadros com voz) fique em alvo_db dBFS."""
    return (x * 10 ** ((alvo_db - p90_voz(x)) / 20)).astype(np.float32)


def sensibilidade(audios):
    print("1b) SENSIBILIDADE E RUÍDO (o que NÃO pode virar fala)")
    f0, f1, f2, f3 = audios
    rng = np.random.default_rng(21)
    rajada = (rng.standard_normal(int(0.8 * stt.TAXA)) * 10 ** (-30 / 20)).astype(np.float32)               # teclado/chiado forte, banda larga
    x = np.concatenate([ruido(1), rajada, ruido(1.5, semente=22)])
    ev = eventos(x)
    checar(not [e for e in ev if e[0] == "fim"], "rajada forte de ruído de banda larga (-30 dBFS) NÃO vira fala")
    d = [e for e in ev if e[0] == "descartado"]
    checar(d and "plano" in (d[0][1] or ""), f"e o motivo registrado é 'som plano': {d[0][1] if d else None}")

    t = np.arange(int(3.5 * stt.TAXA)) / stt.TAXA
    zumbido = (0.0056 * np.sin(2 * np.pi * 120 * t) + 0.0032 * np.sin(2 * np.pi * 240 * t) + 0.0018 * rng.standard_normal(len(t))).astype(np.float32)   # ventilador, ~-44 dBFS
    x = np.concatenate([zumbido, f2, zumbido[: int(1.3 * stt.TAXA)]])
    fins = [e for e in eventos(x) if e[0] == "fim"]
    checar(len(fins) == 1, f"ventilador constante (~-44 dBFS) é aprendido como fundo e a fala ainda é achada (achou {len(fins)})")

    distante = escalar(f0, -52.0)
    x = np.concatenate([ruido(1), distante, ruido(1.2, semente=23)])
    ev = eventos(x)
    checar(not [e for e in ev if e[0] == "fim"], "voz muito distante/fraca (-52 dBFS) é ignorada")
    muito = [e for e in ev if e[0] == "descartado"]
    checar(not muito or "fraco" in (muito[0][1] or ""), f"nem começa um trecho (ou é descartado como 'fraco'): {muito[0][1] if muito else 'sem trecho'}")

    eco = escalar(f0, -36.0)
    x = np.concatenate([ruido(1), eco, ruido(1.2, semente=24)])
    seg = stt.Segmentador(); fins = [e for e in seg.alimentar(x) if e[0] == "fim"]
    checar(len(fins) >= 1, "voz normal (-36 dBFS) com o Jarvis calado é aceita (pausas longas da frase podem dividir em dois pedaços: é a troca do fim de fala rápido)")
    seg = stt.Segmentador(); seg.alimentar(ruido(1)); seg.falando(True)
    fins = [e for e in seg.alimentar(np.concatenate([eco, ruido(1.2, semente=25)])) if e[0] == "fim"]
    checar(not fins, "a MESMA voz enquanto o Jarvis fala (eco residual possível) é ignorada: o detector fica mais rígido")
    forte = escalar(f0, -22.0)
    seg = stt.Segmentador(); seg.alimentar(ruido(1)); seg.falando(True)
    fins = [e for e in seg.alimentar(np.concatenate([forte, ruido(1.2, semente=26)])) if e[0] == "fim"]
    checar(len(fins) == 1, "você falando forte, perto do microfone, por cima do Jarvis (-22 dBFS) ainda o interrompe")

    meio = escalar(f1, -42.0)
    for nome, esperado in (("baixa", 0), ("media", 0), ("alta", 1)):
        seg = stt.Segmentador(sensibilidade=nome)
        fins = [e for e in seg.alimentar(np.concatenate([ruido(1), meio, ruido(1.2, semente=27)])) if e[0] == "fim"]
        checar(len(fins) == esperado, f"sensibilidade '{nome}': voz a -42 dBFS {'aceita' if esperado else 'ignorada'} (achou {len(fins)})")

    x = np.concatenate([ruido(1), f0, ruido(0.3, semente=28), f1, ruido(1.2, semente=29)])
    tipos = [e[0] for e in eventos(x)]
    checar("pre-fim" in tipos and "retomou" in tipos and tipos.count("fim") == 1, f"pausa de 0,3 s: começa a transcrever (pre-fim), a fala volta (retomou) e sai UMA fala só: {tipos}")
    x = np.concatenate([ruido(1), f0, ruido(1.2, semente=30)])
    tipos = [e[0] for e in eventos(x)]
    checar(tipos[-2:] == ["pre-fim", "fim"] and tipos.count("fim") == 1, f"fala que termina de verdade: o pre-fim vem logo antes do fim (pausas naturais da frase também disparam e são descartadas): {tipos}")
    seg = stt.Segmentador(); ev = seg.alimentar(np.concatenate([ruido(1), f2, ruido(1.2, semente=31)]))
    checar(seg.fim_q * 20 == 480 and seg.spec_q * 20 == 240, "fim de fala em 480 ms, com a transcrição especulativa começando em 240 ms")


def whisper(audios):
    print("\n2) WHISPER REAL")
    if not stt.disponivel() or not stt.modelo_em_disco():
        print("  (faster-whisper ou o modelo 'small' ausente: etapa ignorada; rode scripts\\baixar_modelo_whisper.py)")
        return None
    t = stt.Transcritor(log=lambda *a: None)
    t0 = time.perf_counter()
    t._carregar()
    checar(t.pronto, f"modelo carregou em {t.dispositivo}/{t.tipo} ({time.perf_counter() - t0:.1f} s)" + ("" if t.pronto else f": {t.erro}"))
    if not t.pronto:
        return None
    checar(t.dispositivo == "cuda", "usa a NVIDIA (GTX 1650)" if t.dispositivo == "cuda" else f"AVISO: caiu para {t.dispositivo}")
    tempos, acertos = [], []
    for ref, x in zip(FRASES[:3], audios[:3]):
        t1 = time.perf_counter()
        texto, conf, _motivo = t.transcrever(x)
        tempos.append(time.perf_counter() - t1)
        acertos.append(acerto(ref, texto))
        print(f"      {tempos[-1] * 1000:5.0f} ms  conf {conf:.2f}  \"{texto}\"")
    checar(sum(acertos) / len(acertos) >= 0.55, f"acerto médio de palavras {100 * sum(acertos) / len(acertos):.0f}% (voz sintética com nomes em inglês)")
    limite = 1.5 if t.dispositivo == "cuda" else 3.5
    checar(max(tempos) < limite, f"cada frase transcreve em menos de {limite} s (pior: {max(tempos):.2f} s)")
    texto, _, _m = t.transcrever(ruido(3, -55.0, 13))
    checar(texto == "", f"ruído não vira texto inventado (veio: {texto!r})")
    texto, _, _m = t.transcrever(audios[3])
    print(f"      palavra curta 'Para' -> {texto!r}")
    return t


async def sessao(audios, t):
    print("\n3) SESSÃO (quadros de 20 ms até o texto)")
    recebidos, metricas = [], []

    async def emitir(m):
        recebidos.append(m)

    s = stt.SessaoSTT(t, emitir, registrar_metrica=metricas.append)
    s.ligar(True)
    x = np.concatenate([ruido(1), audios[1], ruido(1.2, semente=14)])
    pcm = (x * 32767).astype("<i2").tobytes()
    t0 = time.perf_counter()
    for i in range(0, len(pcm), 640):                      # 20 ms = 320 amostras = 640 bytes
        await s.alimentar(pcm[i:i + 640])
    for _ in range(100):
        if any(m["tipo"] == "transcricao" for m in recebidos):
            break
        await asyncio.sleep(0.05)
    tr = next((m for m in recebidos if m["tipo"] == "transcricao"), None)
    checar(any(m["tipo"] == "vad" and m.get("fala") for m in recebidos), "avisou que a fala começou (vad)")
    checar(tr is not None, "entregou a transcrição final")
    if tr:
        checar(acerto(FRASES[1], tr["texto"]) >= 0.6, f"texto: \"{tr['texto']}\"")
        checar(0 <= tr["confianca"] <= 1 and tr["transcricao_ms"] > 0, f"confiança {tr['confianca']} e tempo {tr['transcricao_ms']} ms")
        checar(bool(metricas) and "stt_transcricao_ms" in metricas[0], "registrou a métrica de transcrição")
    s.ligar(False)
    antes = len(recebidos)
    await s.alimentar(pcm[:64000])
    checar(len(recebidos) == antes, "desligado (mudo): ignora o áudio")


async def servidor(audios):
    print("\n4) SERVIDOR (WebSocket com quadros binários)")
    import websockets
    porta = 8354
    with socket.socket() as sk:
        if sk.connect_ex(("127.0.0.1", porta)) == 0:
            print("  porta ocupada: etapa ignorada")
            return
    env = dict(os.environ, JARVIS_PORTA=str(porta), JARVIS_MEMORIA_DIR=str(TMP / "mem"), JARVIS_SEM_VOZ="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen([sys.executable, str(BASE / "server.py")], cwd=BASE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/saude", timeout=1)
                break
            except Exception:
                await asyncio.sleep(0.5)
        async with websockets.connect(f"ws://127.0.0.1:{porta}/ws", max_size=None, origin=f"http://127.0.0.1:{porta}") as ws:
            painel = json.loads(await ws.recv())
            checar(painel.get("tipo") == "painel" and painel.get("stt_disponivel") is True, f"painel informa stt_disponivel={painel.get('stt_disponivel')} (modo '{painel.get('stt')}')")
            await ws.send(json.dumps({"tipo": "stt", "ligar": True}))
            estado = None
            t0 = time.time()
            while time.time() - t0 < 90:
                m = json.loads(await asyncio.wait_for(ws.recv(), 90))
                if m.get("tipo") == "stt_estado" and m["estado"] in ("pronto", "erro", "indisponivel"):
                    estado = m
                    break
            checar(estado and estado["estado"] == "pronto", f"servidor liga a escuta: {estado}")
            if not estado or estado["estado"] != "pronto":
                return
            x = np.concatenate([ruido(0.8), audios[2], ruido(1.2, semente=15)])
            pcm = (x * 32767).astype("<i2").tobytes()
            t_envio = time.perf_counter()
            for i in range(0, len(pcm), 640):
                await ws.send(pcm[i:i + 640])
            tr, vad = None, False
            while time.perf_counter() - t_envio < 25:
                m = json.loads(await asyncio.wait_for(ws.recv(), 25))
                vad = vad or (m.get("tipo") == "vad" and m.get("fala"))
                if m.get("tipo") == "transcricao":
                    tr = m
                    break
            checar(vad, "o servidor mandou o evento vad")
            checar(tr is not None, "o servidor devolveu a transcrição pelo WebSocket")
            if tr:
                checar(acerto(FRASES[2], tr["texto"]) >= 0.6, f"texto: \"{tr['texto']}\" ({tr['transcricao_ms']} ms)")
            await ws.send(json.dumps({"tipo": "stt", "ligar": False}))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def principal():
    audios = gerar_amostras()
    print(f"amostras: {[round(len(a) / stt.TAXA, 1) for a in audios]} s\n")
    segmentacao(audios)
    sensibilidade(audios)
    t = whisper(audios)
    if t is not None:
        asyncio.run(sessao(audios, t))
        asyncio.run(servidor(audios))
    print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    principal()
