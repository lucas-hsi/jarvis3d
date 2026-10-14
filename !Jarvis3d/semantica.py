"""
Memória SEMÂNTICA do Jarvis: achar por significado, não só por palavra.

Hoje a busca é FTS5 (palavras iguais/raízes): "meu carro quebrou" não acha "oficina do Zé". Aqui cada memória e cada
trecho do cofre do Obsidian ganha um vetor (embedding) e a busca soma duas listas: a das palavras (FTS5, que já
existia) e a do significado (similaridade de cosseno), fundidas por Reciprocal Rank Fusion. O que a busca por
palavras achava continua sendo achado; o semântico só ACRESCENTA (com limiar mínimo para não trazer lixo).

Tudo local: o modelo roda no CPU (ONNX, via fastembed), os vetores ficam no mesmo jarvis.db. Nenhum texto sai do PC.

Regras de segurança/robustez:
- O modelo NUNCA é baixado sozinho: o Jarvis roda em modo offline. Para baixar, rode scripts\\baixar_modelo_embeddings.py.
- Sem a biblioteca, sem o modelo ou com qualquer erro: `pronto` fica falso e a memória segue só com FTS5, como antes.
- Os vetores são recalculados só do que mudou (hash do texto); apagar/editar uma memória invalida o vetor dela.
"""

import hashlib
import os
import sqlite3
import threading
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np

MODELO_PADRAO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"   # 384 dims, ~220 MB, inclui português
# Medido com dados reais do Lucas (2026-10-13, MiniLM multilíngue): perguntas SEM relação tiraram até 0,40 contra memórias
# e até 0,55 contra notas longas (hubs como 'Bem-vindo'); os acertos ficaram em 0,45 a 0,53. Por isso os limiares são ALTOS:
# o significado só acrescenta quando está bem seguro. Para recall melhor, trocar por um modelo feito para busca
# (ex.: intfloat/multilingual-e5-large, ~2,2 GB) e recalibrar com scripts	este_semantica_real.py.
LIMIAR_MEMORIA = 0.45     # cosseno mínimo para uma memória entrar só pelo significado
LIMIAR_COFRE = 0.60       # idem para trechos de notas (textos longos: o ruído é maior)
RRF_K = 60


def _hash(*partes: str) -> str:
    return hashlib.sha1("\0".join(partes).encode("utf-8")).hexdigest()


def fundir(rankings: list[list], pesos: list[float] | None = None) -> list:
    """Reciprocal Rank Fusion: junta listas ordenadas de chaves; quem aparece bem em mais de uma sobe."""
    pesos = pesos or [1.0] * len(rankings)
    pontos: dict = {}
    for lista, peso in zip(rankings, pesos):
        for posicao, chave in enumerate(lista):
            pontos[chave] = pontos.get(chave, 0.0) + peso / (RRF_K + posicao + 1)
    return sorted(pontos, key=lambda c: -pontos[c])


class FastEmbedder:
    """Modelo real (fastembed/ONNX). `carregar` falha se o modelo não estiver em disco (modo offline)."""

    def __init__(self, modelo: str, pasta_modelos: Path, offline: bool = True):
        self.modelo, self.pasta, self.offline = modelo, str(pasta_modelos), offline
        self._m = None

    def carregar(self):
        if self.offline:
            os.environ["HF_HUB_OFFLINE"] = "1"          # impede qualquer download: o Jarvis só usa o que já está em disco
        from fastembed import TextEmbedding
        self._m = TextEmbedding(model_name=self.modelo, cache_dir=self.pasta)

    def embed(self, textos: list[str]) -> np.ndarray:
        vs = np.array(list(self._m.embed(textos)), dtype=np.float32)
        norma = np.linalg.norm(vs, axis=1, keepdims=True)
        norma[norma == 0] = 1
        return vs / norma


class Indice:
    def __init__(self, caminho_db: Path, embedder, log=print):
        self.db_path, self.emb, self.log = str(caminho_db), embedder, log
        self.pronto = False
        self.erro = ""
        self._lock = threading.RLock()
        self._flag = threading.Lock()
        self._rodando = False
        self._de_novo = False
        self._pendente_inicial = False          # alguém pediu sincronização enquanto o modelo ainda carregava
        self._mem_ids: list[int] = []
        self._mem_mat = np.zeros((0, 1), dtype=np.float32)
        self._cofre_meta: list[tuple[str, str, str]] = []      # (caminho, titulo, trecho)
        self._cofre_mat = np.zeros((0, 1), dtype=np.float32)
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        con = self._con()
        con.executescript("""
            CREATE TABLE IF NOT EXISTS emb_mem (id INTEGER PRIMARY KEY, hash TEXT NOT NULL, vetor BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS emb_cofre (chave TEXT PRIMARY KEY, caminho TEXT NOT NULL, titulo TEXT NOT NULL,
                                                  trecho TEXT NOT NULL, vetor BLOB NOT NULL);
        """)
        con.commit()
        con.close()

    def _con(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=15)
        con.execute("PRAGMA busy_timeout=15000")
        return con

    # ------------------------------------------------------------ ciclo de vida
    def iniciar(self):
        """Carrega o modelo e sincroniza os vetores numa thread (não segura o servidor)."""
        threading.Thread(target=self._partida, daemon=True, name="semantica").start()

    def _partida(self):
        t0 = time.perf_counter()
        try:
            self.emb.carregar()
        except Exception as e:                    # sem biblioteca, sem modelo em disco, offline: segue só com FTS5
            self.erro = f"{type(e).__name__}: {str(e).splitlines()[0][:160] if str(e) else ''}"
            self.log(f"[jarvis] memória semântica indisponível ({self.erro}); busca só por palavras")
            return
        try:
            self.sincronizar()
            self.pronto = True
            if self._pendente_inicial:            # o cofre/memórias mudaram durante a carga
                self._pendente_inicial = False
                self.sincronizar()
            self.log(f"[jarvis] memória semântica pronta: {len(self._mem_ids)} memórias, {len(self._cofre_meta)} trechos de notas "
                     f"({round(time.perf_counter() - t0, 1)} s)")
        except Exception as e:
            self.erro = f"{type(e).__name__}: {str(e)[:160]}"
            self.log(f"[jarvis] memória semântica falhou ao indexar ({self.erro}); busca só por palavras")

    def estado(self) -> str:
        return "pronta" if self.pronto else ("indisponível" if self.erro else "carregando")

    def pedir_sincronizacao(self):
        """Chamado depois de salvar/editar/esquecer memória ou reindexar o cofre. Não bloqueia; agrupa pedidos seguidos."""
        if not self.pronto:
            self._pendente_inicial = True         # o modelo ainda carrega: sincroniza de novo assim que ficar pronto
            return
        with self._flag:
            if self._rodando:
                self._de_novo = True
                return
            self._rodando = True
        threading.Thread(target=self._ciclo, daemon=True, name="semantica-sync").start()

    def _ciclo(self):
        while True:
            try:
                self.sincronizar()
            except Exception as e:
                self.log(f"[jarvis] semântica: erro ao sincronizar ({type(e).__name__}: {str(e)[:100]})")
            with self._flag:
                if self._de_novo:
                    self._de_novo = False
                    continue
                self._rodando = False
                return

    # ------------------------------------------------------------ sincronizar vetores com o banco
    def sincronizar(self):
        with self._lock:
            con = self._con()
            try:
                # memórias
                atuais = {i: t for i, t in con.execute("SELECT id, texto FROM memorias")}
                guardados = {i: h for i, h in con.execute("SELECT id, hash FROM emb_mem")}
                faltam = [(i, t) for i, t in atuais.items() if guardados.get(i) != _hash(t)]
                for lote in range(0, len(faltam), 32):
                    parte = faltam[lote:lote + 32]
                    vs = self.emb.embed([t for _, t in parte])
                    con.executemany("INSERT OR REPLACE INTO emb_mem(id, hash, vetor) VALUES (?,?,?)",
                                    [(i, _hash(t), v.tobytes()) for (i, t), v in zip(parte, vs)])
                con.executemany("DELETE FROM emb_mem WHERE id=?", [(i,) for i in guardados if i not in atuais])

                # trechos do cofre
                # trechos só de título ("# Índice") não têm conteúdo: o vetor deles casaria com qualquer coisa
                chunks = {_hash(c, t): (c, ti, t) for c, ti, t in con.execute("SELECT caminho, titulo, trecho FROM cofre_fts")
                          if len(t.strip().lstrip("#").strip()) >= 40}
                ja = {r[0] for r in con.execute("SELECT chave FROM emb_cofre")}
                novos = [(k, v) for k, v in chunks.items() if k not in ja]
                for lote in range(0, len(novos), 32):
                    parte = novos[lote:lote + 32]
                    vs = self.emb.embed([f"{v[1]}. {v[2]}"[:1200] for _, v in parte])
                    con.executemany("INSERT OR REPLACE INTO emb_cofre(chave, caminho, titulo, trecho, vetor) VALUES (?,?,?,?,?)",
                                    [(k, v[0], v[1], v[2], vec.tobytes()) for (k, v), vec in zip(parte, vs)])
                con.executemany("DELETE FROM emb_cofre WHERE chave=?", [(k,) for k in ja if k not in chunks])
                con.commit()

                # matrizes em memória (busca = uma multiplicação)
                linhas = con.execute("SELECT id, vetor FROM emb_mem ORDER BY id").fetchall()
                self._mem_ids = [r[0] for r in linhas]
                self._mem_mat = (np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in linhas])
                                 if linhas else np.zeros((0, 1), dtype=np.float32))
                linhas = con.execute("SELECT caminho, titulo, trecho, vetor FROM emb_cofre ORDER BY chave").fetchall()
                self._cofre_meta = [(r[0], r[1], r[2]) for r in linhas]
                self._cofre_mat = (np.vstack([np.frombuffer(r[3], dtype=np.float32) for r in linhas])
                                   if linhas else np.zeros((0, 1), dtype=np.float32))
            finally:
                con.close()

    # ------------------------------------------------------------ busca
    def _vetor(self, texto: str) -> np.ndarray:
        texto = " ".join(texto.split())[:500]
        if texto in self._cache:
            self._cache.move_to_end(texto)
            return self._cache[texto]
        v = self.emb.embed([texto])[0]
        self._cache[texto] = v
        if len(self._cache) > 64:
            self._cache.popitem(last=False)
        return v

    def buscar_memorias(self, consulta: str, k: int = 8, limiar: float = LIMIAR_MEMORIA) -> list[tuple[int, float]]:
        """[(id, similaridade)] das memórias mais próximas em significado, acima do limiar."""
        if not self.pronto or len(consulta.strip()) < 3 or not len(self._mem_ids):
            return []
        try:
            q = self._vetor(consulta)
            with self._lock:
                notas = self._mem_mat @ q
                ids = list(self._mem_ids)
        except Exception:
            return []
        ordem = np.argsort(-notas)[:k]
        return [(ids[i], float(notas[i])) for i in ordem if notas[i] >= limiar]

    def buscar_cofre(self, consulta: str, k: int = 6, limiar: float = LIMIAR_COFRE) -> list[dict]:
        """Trechos de notas mais próximos em significado (no máximo um por nota)."""
        if not self.pronto or len(consulta.strip()) < 3 or not len(self._cofre_meta):
            return []
        try:
            q = self._vetor(consulta)
            with self._lock:
                notas = self._cofre_mat @ q
                meta = list(self._cofre_meta)
        except Exception:
            return []
        saida, vistas = [], set()
        for i in np.argsort(-notas):
            if notas[i] < limiar or len(saida) >= k:
                break
            caminho, titulo, trecho = meta[i]
            if caminho in vistas:
                continue
            vistas.add(caminho)
            saida.append({"caminho": caminho, "titulo": titulo, "trecho": trecho, "score": float(notas[i])})
        return saida
