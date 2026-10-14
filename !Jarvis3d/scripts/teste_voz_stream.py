"""
Testa, DENTRO do Electron e com a janela MUDA, a voz em streaming: pedaços de MP3 real (Lax) chegando como o servidor os manda
(fala_ini / fala_chunk / fala_fim). Confere que o som COMEÇA no primeiro pedaço (não no último), que a 2ª frase pré-carregada
toca em seguida, que no fim tudo é liberado e que interromper no meio limpa tudo (inclusive pedaços atrasados).

Uso:  .venv\\Scripts\\python.exe -X utf8 scripts\\teste_voz_stream.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MP3 = BASE / "vozes-teste" / "comparacao" / "LAX_eleven_v4_turbo.mp3"


def principal():
    electron = BASE / "desktop" / "node_modules" / "electron" / "dist" / "electron.exe"
    if not electron.exists() or not MP3.exists():
        sys.exit("faltam o Electron instalado ou a amostra de voz em vozes-teste\\comparacao")
    tmp = Path(tempfile.mkdtemp(prefix="jarvis_vstream_"))
    env = dict(os.environ, JARVIS_PORTA="8359", JARVIS_MEMORIA_DIR=str(tmp / "mem"), JARVIS_SEM_VOZ="1", PYTHONUTF8="1")
    r = subprocess.run([str(electron), str(BASE / "desktop"), f"--user-data-dir={tmp / 'ud'}", "--teste-stream", str(MP3)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, env=env, cwd=str(BASE / "desktop"))
    linha = next((l for l in r.stdout.splitlines() if l.startswith("RESULTADO_STREAM ")), None)
    if not linha:
        print("sem resultado:\n", r.stdout[-1200:], r.stderr[-600:])
        sys.exit(1)
    d = json.loads(linha.split(" ", 1)[1])
    if d.get("erro") or not d.get("dados"):
        print("erro:", d.get("erro"))
        sys.exit(1)
    x = d["dados"]
    ok = True

    def checar(cond, texto):
        nonlocal ok
        ok &= bool(cond)
        print("  [%s] %s" % ("OK" if cond else "FALHOU", texto))

    print("VOZ EM STREAMING (janela muda)")
    checar(x["suporta"], "o Chromium do app suporta MediaSource com audio/mpeg")
    p1, ult = x.get("playing1_ms"), x.get("t_ultimo_pedaco")
    checar(p1 is not None and ult is not None and p1 < ult, f"o som da 1ª frase COMEÇOU em {p1} ms, antes de o último pedaço chegar ({ult:.0f} ms)")
    checar(p1 is not None and p1 < 900, f"e rápido: {p1} ms do primeiro pedaço até tocar")
    checar(x.get("ended1_ms") and x["duracao1_s"] > 1.0, f"a 1ª frase tocou até o fim ({x.get('duracao1_s', 0):.1f} s de áudio)")
    checar(x.get("playing2_ms") is not None and x.get("ended2_ms") and x["duracao2_s"] > 1.0, f"a 2ª frase (pré-carregada) também tocou ({x.get('duracao2_s', 0):.1f} s)")
    if x.get("playing2_ms") is not None and x.get("ended1_ms") is not None:
        folga = x["playing2_ms"] - x["ended1_ms"]
        checar(-200 <= folga <= 700, f"a 2ª começa logo depois da 1ª (intervalo de {folga} ms)")
    checar(x["streams_abertos_durante"] >= 1 and x["estado_durante"] == "falando", f"durante a fala: estado '{x['estado_durante']}' e {x['streams_abertos_durante']} stream(s) abertos")
    checar(x["streams_depois"] == 0 and x["estado_depois"] != "falando", f"no fim tudo é liberado: {x['streams_depois']} streams, estado '{x['estado_depois']}'")
    checar(x["cortada_tocou"], "a frase que seria cortada começou a tocar")
    checar(x["streams_apos_corte"] == 0 and not x["tocando_apos_corte"] and x["estado_apos_corte"] != "falando",
           f"interromper limpa tudo (streams {x['streams_apos_corte']}, tocando {x['tocando_apos_corte']}, estado '{x['estado_apos_corte']}') e ignora pedaços atrasados")
    checar(not x["erros"], f"sem erros na página: {x['erros']}")
    print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    principal()
