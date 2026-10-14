"""
Diagnóstico do Jarvis na linha de comando: está tudo pronto nesta máquina?

Uso:  .venv\\Scripts\\python.exe -X utf8 scripts\\diagnostico.py [--mic] [--chaves] [--rede] [--json]
  --mic     grava ~1,5 s do microfone SÓ para medir o nível (nada é salvo nem enviado)
  --chaves  valida as chaves de API online (chamadas gratuitas; as chaves nunca são mostradas)
  --rede    testa o acesso a Anthropic, ElevenLabs, Hugging Face e Google
  --json    saída para outros programas
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")
import diagnostico  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mic", action="store_true")
    ap.add_argument("--chaves", action="store_true")
    ap.add_argument("--rede", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--porta", type=int, default=8340)
    a = ap.parse_args()
    r = diagnostico.rodar(a.porta, a.mic, a.chaves, a.rede)
    print(json.dumps(r, ensure_ascii=False, indent=1) if a.json else diagnostico.formatar(r))
    sys.exit(1 if any(x["estado"] == "erro" for x in r) else 0)


if __name__ == "__main__":
    main()
