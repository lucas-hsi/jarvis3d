"""
Baixa UMA VEZ o modelo de embeddings da memória semântica para memoria\\modelos\\ (o Jarvis em si roda offline e
nunca baixa nada sozinho).

  Fonte:    Hugging Face (modelo ONNX via fastembed)
  Modelo:   sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2  (384 dimensões, português incluso)
  Tamanho:  ~220 MB em disco

Uso:  .venv\\Scripts\\python.exe -X utf8 scripts\\baixar_modelo_embeddings.py [nome-do-modelo]
"""

import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import semantica  # noqa: E402

modelo = sys.argv[1] if len(sys.argv) > 1 else semantica.MODELO_PADRAO
destino = BASE / "memoria" / "modelos"
destino.mkdir(parents=True, exist_ok=True)
print(f"Baixando {modelo} para {destino} ...")
t0 = time.time()
from fastembed import TextEmbedding  # noqa: E402

try:
    suportados = {m["model"]: m for m in TextEmbedding.list_supported_models()}
    if modelo not in suportados:
        print("ATENÇÃO: esse modelo não está na lista do fastembed. Suportados multilíngues:")
        for nome, info in suportados.items():
            if "multilingual" in nome.lower():
                print(f"  - {nome} ({info.get('dim')} dims, {info.get('size_in_GB')} GB)")
        sys.exit(1)
    print(f"Tamanho informado: {suportados[modelo].get('size_in_GB')} GB, {suportados[modelo].get('dim')} dimensões")
except Exception as e:
    print(f"(não consegui listar os modelos suportados: {type(e).__name__})")

m = TextEmbedding(model_name=modelo, cache_dir=str(destino))
vetor = list(m.embed(["teste de português: acentuação, ç e ã"]))[0]
print(f"Pronto em {round(time.time() - t0)} s. Vetor de teste com {len(vetor)} dimensões.")
print("Agora reinicie o Jarvis: ele passa a usar a memória semântica sozinho (confira o log: 'memória semântica pronta').")
