"""
Baixa UMA VEZ o modelo do reconhecimento de voz próprio (Whisper, formato faster-whisper) para memoria\\modelos\\whisper.
O Jarvis em si roda offline e nunca baixa nada sozinho.

  Fonte:    Hugging Face (Systran/faster-whisper-<modelo>)
  small:    ~480 MB  (recomendado: ~0,6 s por frase na GTX 1650, ~2 s na CPU)
  base:     ~145 MB  (mais rápido, mas erra bem mais)
  medium:   ~1,5 GB  (mais preciso; pesado para 4 GB de VRAM)
  large-v3-turbo: ~1,6 GB (preciso e rápido, mas o uso de VRAM ainda não foi medido neste notebook)

Uso:  .venv\\Scripts\\python.exe -X utf8 scripts\\baixar_modelo_whisper.py [small|base|medium|large-v3-turbo]
"""

import os
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import stt  # noqa: E402

modelo = sys.argv[1] if len(sys.argv) > 1 else stt.MODELO_PADRAO
destino = stt.pasta_modelos()
destino.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
print(f"Baixando o modelo Whisper '{modelo}' para {destino} ...")
t0 = time.time()
from faster_whisper.utils import download_model  # noqa: E402

for tentativa in range(1, 5):
    try:
        pasta = download_model(modelo, cache_dir=str(destino))
        print(f"Pronto em {round(time.time() - t0)} s: {pasta}")
        print("Para o Jarvis usar a voz própria: em ajustes.json ponha \"stt\": \"local\" (a casca Electron já usa).")
        break
    except Exception as e:                                          # o Hugging Face às vezes dá 429/500: espera e tenta de novo
        print(f"tentativa {tentativa} falhou ({type(e).__name__}); aguardando {15 * tentativa} s...")
        time.sleep(15 * tentativa)
else:
    sys.exit("Não consegui baixar agora. Tente de novo mais tarde.")
