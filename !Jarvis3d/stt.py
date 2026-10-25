"""
Reconhecimento de voz PRÓPRIO do Jarvis (não depende do Chrome): detecção de fala + faster-whisper.

Por que existe: o reconhecedor do Chrome (Web Speech) NÃO funciona dentro de um app nativo (Electron: erro 'network',
medido em 2026-10-13), e o Chrome decide sozinho quando você parou de falar. Aqui o navegador/casca só captura o
microfone (com cancelamento de eco do Chromium) e manda pedaços de 20 ms por WebSocket; o servidor decide o fim da fala
e transcreve. O navegador continua sendo a camada de decisão (nome "Jarvis", janela de conversa, confirmação, corte
por voz): ele recebe `transcricao` no mesmo formato que o Chrome entregava.

Sensibilidade (2026-10-14): o detector antigo tratava ruído contínuo e a própria voz do Jarvis nos alto-falantes como fala
(395 transcrições para 21 conversas, trechos de 8 a 20 s). Agora um trecho só vira fala se passar em TODAS as provas:
relação sinal/ruído, nível mínimo absoluto, razão de quadros com voz, planura espectral (voz é tonal; teclado e chiado são
planos) e duração. Enquanto o Jarvis fala, as provas ficam mais rígidas (eco residual).

Velocidade (2026-10-14): fim de fala em 480 ms (era 650) e transcrição ESPECULATIVA: com 240 ms de silêncio já começa a
transcrever; se a fala retoma, descarta; se o silêncio se confirma, o texto já está pronto.

Placa: GTX 1650 com int8_float16 (small = ~0,6 s por frase), com queda automática para a CPU (int8, ~2 s).
O modelo NUNCA é baixado aqui (offline); veja scripts\\baixar_modelo_whisper.py.
"""

import asyncio
import math
import os
import re
import site
import threading
import time
import unicodedata
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

import caminhos

TAXA = 16000
QUADRO = 320                                  # 20 ms a 16 kHz
MODELO_PADRAO = "small"
MODELO_PRECISO = "large-v3-turbo"            # ~1,6 GB, entende bem melhor o português; vale com placa NVIDIA (baixado só se o usuário pedir em /configurar)
VOCABULARIO = ("YouTube, Gmail, Obsidian, Mercado Livre, WhatsApp, "
               "Spotify, Chrome, Bloco de Notas, agenda, e-mail, Downloads, Documentos, PowerShell, Python, VS Code, GitHub, Oficina.")
HOTWORDS = "Jarvis"

# Termos técnicos que o Whisper costuma ouvir torto em português (só palavras inteiras; o resto do texto não muda)
CORRECOES = [
    (re.compile(r"\b(pai ?t[oô]n|paiton|p[aá]iton|piton|python)\b", re.IGNORECASE), "Python"),
    (re.compile(r"\b(p[aáo]u?w?[eê]r ?(x|sh|ch)[eé]l+)\b", re.IGNORECASE), "PowerShell"),
    (re.compile(r"\b(e?scr[ií]pi?t[ei]?|iscript|scripit)(s?)\b", re.IGNORECASE), r"script\2"),
    (re.compile(r"\b(vs ?code|vi ?es ?code|v[eê] ?esse ?code|visual studio code)\b", re.IGNORECASE), "VS Code"),
    (re.compile(r"\b(git ?hub|guit ?hub|guiti ?hub)\b", re.IGNORECASE), "GitHub"),
    (re.compile(r"\bjava ?script\b", re.IGNORECASE), "JavaScript"),
    (re.compile(r"\b(of[ií]cina do jarvis|oficina do jarves)\b", re.IGNORECASE), "Oficina do Jarvis"),
]


def corrigir_termos(texto: str) -> str:
    for rx, certo in CORRECOES:
        texto = rx.sub(certo, texto)
    return texto


def modelo_escolhido(cfg: dict) -> str:
    """O que o usuário escolheu ("stt_modelo"); sem escolha, o preciso se ele já foi baixado; senão o small."""
    if cfg.get("stt_modelo"):
        return str(cfg["stt_modelo"])
    return MODELO_PRECISO if modelo_em_disco(MODELO_PRECISO) else MODELO_PADRAO
# Como o Whisper costuma errar o nome no INÍCIO da fala (nunca mexe no meio do texto)
_NOME_ERRADO = re.compile(r"^\W*(jarves|j[aá]rvi|g[aá]rvis|g[eé]rvis|j[aá]rbis|d?j[aá]rvez|servis|reci|jarvice|jarvi?s)\b[\s,.!?:;-]*", re.IGNORECASE)


def corrigir_nome(texto: str) -> str:
    m = _NOME_ERRADO.match(texto)
    if m and not texto[:m.end()].lower().startswith("jarvis"):
        return "Jarvis, " + texto[m.end():].lstrip()
    # parecido com "Jarvis" por semelhança de som/grafia (Garvis, Jarvez, Charvis...): só a PRIMEIRA palavra
    import difflib
    primeira = re.match(r"^\W*(\w+)\b[\s,.!?:;-]*", texto)
    if primeira:
        palavra = _norm(primeira.group(1))
        if palavra and palavra[0] != "jarvis" and difflib.SequenceMatcher(None, palavra[0], "jarvis").ratio() >= 0.74 and len(palavra[0]) >= 5:
            return "Jarvis, " + texto[primeira.end():].lstrip()
    return texto


# Frases que o Whisper inventa em silêncio/ruído: nunca são fala de verdade
ALUCINACOES = re.compile(r"legendas? (pela|por|de) |amara\.org|obrigad[oa] por assistir|inscreva-se|^\W*$|transcri[cç][aã]o por|"
                         r"^(tchau\.?|ok\.?|hum+\.?|ah+\.?|uh+\.?|obrigad[oa]\.?|e aí\.?|então\.?)$", re.IGNORECASE)
# Falas de uma palavra só que valem como comando (o resto de uma palavra sozinha é quase sempre ruído)
UMA_PALAVRA_OK = {"para", "pare", "parar", "chega", "espera", "espere", "aguarda", "aguarde", "calma", "sim", "nao", "confirmo", "cancela",
                  "cancelar", "jarvis", "silencio", "continua", "continue", "proxima", "anterior", "pausa", "pausar",
                  "confirma", "confirmado", "autorizo", "pode", "negativo", "cancelado", "isso", "beleza", "claro", "positivo"}

# Provas de "isto é fala": quanto maior a sensibilidade, mais permissivas (e mais falsos disparos)
PRESETS = {
    "baixa": dict(snr_liga=12.0, abs_liga=-44.0, snr_desliga=6.0, abs_desliga=-50.0, abs_pico=-39.0, razao_voz=0.30, planura=0.46),
    "media": dict(snr_liga=9.0,  abs_liga=-48.0, snr_desliga=5.0, abs_desliga=-53.0, abs_pico=-44.0, razao_voz=0.20, planura=0.52),
    "alta":  dict(snr_liga=7.0,  abs_liga=-52.0, snr_desliga=4.0, abs_desliga=-56.0, abs_pico=-47.0, razao_voz=0.16, planura=0.58),
}
EXTRA_FALANDO_DB = 6.0                       # enquanto o Jarvis fala, tudo precisa ser 6 dB mais forte (eco residual dos alto-falantes)

# Registro em memória (nunca em disco) das últimas falas ouvidas e o que se decidiu: serve para entender "por que ele me chamou?"
RECENTES: deque = deque(maxlen=60)
_ID = [0]


def registrar(evento: dict) -> int:
    _ID[0] += 1
    evento = {"id": _ID[0], "hora": time.strftime("%H:%M:%S"), **evento}
    RECENTES.append(evento)
    return _ID[0]


def atualizar_decisao(id_: int, acao: str, motivo: str):
    for e in reversed(RECENTES):
        if e["id"] == id_:
            e["decisao"] = acao
            e["motivo_decisao"] = motivo[:80]
            return


def _preparar_cuda():
    """DLLs do CUDA instaladas por pip (cublas/cudnn) precisam estar no caminho de busca do Windows."""
    try:
        bases = list(site.getsitepackages())
    except Exception:
        bases = []
    bases.append(str(caminhos.DADOS / "cuda"))             # bibliotecas baixadas pelo assistente de configuração (instalação como produto)
    for base in bases:
        for sub in list((Path(base) / "nvidia").glob("*/bin")) + list(Path(base).glob("*/bin")):
            try:
                os.add_dll_directory(str(sub))
            except (OSError, AttributeError):
                pass
            os.environ["PATH"] = str(sub) + os.pathsep + os.environ.get("PATH", "")


def disponivel() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def pasta_modelos() -> Path:
    return caminhos.DADOS / "memoria" / "modelos" / "whisper"


def modelo_em_disco(nome: str = MODELO_PADRAO) -> bool:
    p = pasta_modelos()
    return p.exists() and any(p.glob(f"models--*faster-whisper-{nome}*/snapshots/*/model.bin"))


def _norm(t: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower())


# ------------------------------------------------------------------ transcrição

class Transcritor:
    def __init__(self, modelo: str = MODELO_PADRAO, dispositivo: str = "auto", vocabulario: str = VOCABULARIO, log=print):
        self.modelo, self.pedido, self.vocabulario, self.log = modelo, dispositivo, vocabulario, log
        self.m = None
        self.dispositivo = ""
        self.tipo = ""
        self.erro = ""
        self.pronto = False
        self._carregando = False
        self._lock = threading.Lock()
        self._vocab_palavras = set(_norm(vocabulario or ""))

    def estado(self) -> str:
        return "pronto" if self.pronto else ("erro" if self.erro else "carregando")

    def carregar_em_segundo_plano(self):
        with self._lock:
            if self.pronto or self._carregando:
                return
            self._carregando = True
        threading.Thread(target=self._carregar, daemon=True, name="stt-carga").start()

    def _carregar(self):
        t0 = time.perf_counter()
        try:
            os.environ["HF_HUB_OFFLINE"] = "1"               # o Jarvis nunca baixa nada sozinho
            _preparar_cuda()
            from faster_whisper import WhisperModel
            opcoes = {"auto": [("cuda", "int8_float16"), ("cpu", "int8")], "cuda": [("cuda", "int8_float16")], "cpu": [("cpu", "int8")]}.get(self.pedido, [("cpu", "int8")])
            ultimo = ""
            for disp, tipo in opcoes:
                try:
                    m = WhisperModel(self.modelo, device=disp, compute_type=tipo, download_root=str(pasta_modelos()),
                                     local_files_only=True, cpu_threads=8 if disp == "cpu" else 4)
                    list(m.transcribe(np.zeros(TAXA, dtype=np.float32), language="pt", beam_size=1)[0])   # aquecimento: falha de CUDA aparece aqui
                    self.m, self.dispositivo, self.tipo = m, disp, tipo
                    break
                except Exception as e:                        # sem CUDA/DLL/VRAM: tenta a próxima (CPU)
                    ultimo = f"{disp}: {type(e).__name__}: {str(e)[:120]}"
                    self.log(f"[jarvis] voz: {ultimo}")
            if self.m is None:
                raise RuntimeError(ultimo or "nenhum dispositivo funcionou")
            self.pronto = True
            self.log(f"[jarvis] reconhecimento de voz próprio pronto: {self.modelo} em {self.dispositivo}/{self.tipo} ({round(time.perf_counter() - t0, 1)} s)")
        except Exception as e:
            self.erro = f"{type(e).__name__}: {str(e)[:160]}"
            self.log(f"[jarvis] reconhecimento de voz próprio indisponível ({self.erro})")
        finally:
            self._carregando = False

    def transcrever(self, x: np.ndarray) -> tuple[str, float, str]:
        """(texto, confiança 0 a 1, motivo se descartado). Texto vazio = descartado."""
        curto = len(x) < 1.5 * TAXA                             # "para", "chega": o VAD do Whisper descarta; nosso detector já aparou
        if curto:
            folga = np.zeros(int(0.3 * TAXA), dtype=np.float32)
            x = np.concatenate([folga, x, folga])
        segs, _info = self.m.transcribe(
            x, language="pt", beam_size=2 if curto else 4, hotwords=HOTWORDS, vad_filter=not curto, vad_parameters={"min_silence_duration_ms": 300},
            condition_on_previous_text=False, temperature=0.0, no_speech_threshold=0.5, log_prob_threshold=-1.0,
            compression_ratio_threshold=2.2, without_timestamps=True, initial_prompt=self.vocabulario or None)
        lista = list(segs)
        if not lista:
            return "", 0.0, "sem fala reconhecida"
        texto = corrigir_termos(corrigir_nome(" ".join(s.text.strip() for s in lista).strip()))
        logprob = sum(s.avg_logprob for s in lista) / len(lista)
        sem_fala = max(s.no_speech_prob for s in lista)
        confianca = max(0.0, min(1.0, math.exp(logprob)))
        pal = _norm(texto)
        if sem_fala > 0.5:
            return "", confianca, f"provavelmente não é fala (no_speech {sem_fala:.2f})"
        if ALUCINACOES.search(texto):
            return "", confianca, "frase típica de alucinação do Whisper"
        if confianca < 0.30:
            return "", confianca, f"confiança baixa ({confianca:.2f})"
        if pal == ["jarvis"] and confianca < 0.40:
            return "", confianca, f"só o nome, com pouca certeza ({confianca:.2f}): provável alucinação"
        if len(pal) == 1 and pal[0] not in UMA_PALAVRA_OK:
            return "", confianca, "uma palavra solta que não é comando"
        if len(pal) >= 3 and all(p in self._vocab_palavras for p in pal):
            return "", confianca, "só repete o vocabulário do prompt (alucinação)"
        return texto, confianca, ""


# ------------------------------------------------------------------ onde começa e termina a fala

def planura_espectral(audio: np.ndarray) -> float:
    """0 = tonal (voz), 1 = ruído plano (chiado, teclado, estática). Média sobre janelas de 32 ms, na faixa 100 a 4000 Hz."""
    n = 512
    if len(audio) < n:
        return 1.0
    quadros = audio[: len(audio) // n * n].reshape(-1, n) * np.hanning(n)
    potencia = np.abs(np.fft.rfft(quadros, axis=1)) ** 2 + 1e-12
    faixa = potencia[:, 4:128]                                   # 125 Hz a 4 kHz
    forte = faixa.sum(axis=1) > np.percentile(faixa.sum(axis=1), 35)   # só os quadros com energia (ignora as pausas)
    faixa = faixa[forte] if forte.any() else faixa
    geo = np.exp(np.mean(np.log(faixa), axis=1))
    return float(np.mean(geo / np.mean(faixa, axis=1)))


class Segmentador:
    """Quadros de 20 ms -> eventos ('inicio',), ('pre-fim', audio), ('retomou',), ('fim', audio, duracao_ms, nivel_db),
    ('descartado', motivo, dur_ms, nivel_db). Piso de ruído calibrado nos primeiros 0,5 s e adaptativo."""

    CALIBRACAO_Q = 25                                           # 0,5 s de escuta para descobrir o ruído de fundo da sala

    def __init__(self, fim_ms: int = 480, inicio_ms: int = 100, pre_ms: int = 600, max_s: float = 14.0, min_ms: int = 200,
                 sensibilidade: str = "media", especulativo_ms: int = 240):
        self.fim_q, self.ini_q, self.pre_q = fim_ms // 20, max(1, inicio_ms // 20), pre_ms // 20
        self.max_q, self.min_q = int(max_s * 1000 / 20), max(1, min_ms // 20)
        self.spec_q = min(self.fim_q - 1, max(1, especulativo_ms // 20))
        self.piso = -62.0
        self.p = PRESETS.get(sensibilidade, PRESETS["media"])
        self.extra = 0.0                                        # dB a mais enquanto o Jarvis fala
        self.calibrando: list[float] | None = []                # níveis dos primeiros quadros (sala barulhenta desde o início)
        self.reiniciar()

    def definir_sensibilidade(self, nome: str):
        self.p = PRESETS.get(nome, self.p)

    def falando(self, sim: bool):
        self.extra = EXTRA_FALANDO_DB if sim else 0.0

    def reiniciar(self):
        self.pre: list[np.ndarray] = []
        self.fala: list[np.ndarray] = []
        self.dentro = False
        self.acima = 0
        self.silencio = 0
        self.voz_q = 0
        self.niveis: list[float] = []
        self.acima_ruido_q = 0                                  # quadros claramente acima do ruído de fundo (voz baixa também conta)
        self.pre_emitido = False

    @staticmethod
    def _db(q: np.ndarray) -> float:
        return 20 * math.log10(float(np.sqrt(np.mean(q * q))) + 1e-7)

    def _recortar(self) -> np.ndarray:
        return np.concatenate(self.fala[: len(self.fala) - max(0, self.silencio - 8)])      # corta o silêncio final (deixa ~160 ms)

    def quadro(self, q: np.ndarray) -> list[tuple]:
        eventos = []
        db = self._db(q)
        if self.calibrando is not None:                          # piso = nível típico dos primeiros 0,5 s; sem eventos até lá
            self.calibrando.append(db)
            self.pre.append(q)
            self.pre = self.pre[-self.pre_q:]
            if len(self.calibrando) >= self.CALIBRACAO_Q:
                self.piso = min(-30.0, max(-75.0, float(np.percentile(self.calibrando, 40))))
                self.calibrando = None
            return eventos
        p = self.p
        liga = max(self.piso + p["snr_liga"], p["abs_liga"]) + self.extra
        desliga = max(self.piso + p["snr_desliga"], p["abs_desliga"]) + self.extra
        if not self.dentro:
            if db < liga:                                       # só aprende o piso com ruído (nunca com voz)
                self.piso = min(-30.0, max(-75.0, 0.97 * self.piso + 0.03 * db))
            self.pre.append(q)
            self.pre = self.pre[-self.pre_q:]
            self.acima = self.acima + 1 if db >= liga else 0
            if self.acima >= self.ini_q + (int(self.extra) // 6):       # falando: pede mais tempo seguido acima do limite
                self.dentro = True
                self.fala = list(self.pre)                      # inclui o começo da palavra que veio antes de passar do limite
                self.silencio = 0
                self.voz_q = self.acima
                self.acima_ruido_q = self.acima
                self.niveis = [db]
                eventos.append(("inicio",))
            return eventos
        self.fala.append(q)
        if db >= self.piso + 8.0:
            self.acima_ruido_q += 1
        if db >= desliga:
            if self.pre_emitido and self.silencio > 0:
                eventos.append(("retomou",))                    # a pausa era só respiro: a transcrição especulativa é descartada
                self.pre_emitido = False
            self.silencio = 0
            self.voz_q += 1
            self.niveis.append(db)
        else:
            self.silencio += 1
            if self.silencio == self.spec_q and not self.pre_emitido and self.voz_q >= self.min_q:
                self.pre_emitido = True
                eventos.append(("pre-fim", self._recortar()))
        if self.silencio >= self.fim_q or len(self.fala) >= self.max_q:
            audio = self._recortar()
            duracao = int(len(audio) / TAXA * 1000)
            nivel = float(np.percentile(self.niveis, 90)) if self.niveis else -99.0
            total = max(1, len(self.fala) - self.silencio)
            ruim = None
            if self.voz_q < self.min_q + (self.extra > 0) * 5:
                ruim = f"curto demais ({self.voz_q * 20} ms de voz)"
            elif self.acima_ruido_q / total < p["razao_voz"]:
                ruim = f"pouca voz no trecho ({self.acima_ruido_q / total:.0%} dos quadros acima do ruído)"
            elif nivel < p["abs_pico"] + self.extra:
                ruim = f"fraco demais ({nivel:.0f} dBFS)"
            elif nivel - self.piso < 14.0:
                ruim = f"quase no nível do ruído ({nivel - self.piso:.0f} dB acima do piso)"
            else:
                planura = planura_espectral(audio)
                if planura > p["planura"]:
                    ruim = f"som plano, não é voz (planura {planura:.2f})"
            self.reiniciar()
            eventos.append(("descartado", ruim, duracao, nivel, audio) if ruim else ("fim", audio, duracao, nivel))
        return eventos

    def alimentar(self, pcm: np.ndarray) -> list[tuple]:
        """pcm: float32 em [-1, 1]. Aceita blocos de qualquer tamanho; guarda o resto para o próximo quadro."""
        self._resto = np.concatenate([getattr(self, "_resto", np.zeros(0, np.float32)), pcm])
        saida = []
        while len(self._resto) >= QUADRO:
            saida += self.quadro(self._resto[:QUADRO])
            self._resto = self._resto[QUADRO:]
        return saida


# ------------------------------------------------------------------ uma sessão (uma conexão com a interface)

DEBUG_DIR = os.environ.get("JARVIS_STT_DEBUG")             # só para diagnóstico: guarda os últimos trechos ouvidos (áudio) NESTA pasta, localmente


def _despejar(audio: np.ndarray, rotulo: str):
    if not DEBUG_DIR or audio is None:
        return
    import wave
    pasta = Path(DEBUG_DIR)
    pasta.mkdir(parents=True, exist_ok=True)
    nome = pasta / (time.strftime("%H%M%S") + "_" + re.sub(r"\W+", "_", rotulo)[:40] + ".wav")
    with wave.open(str(nome), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(TAXA)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    for velho in sorted(pasta.glob("*.wav"))[:-24]:
        velho.unlink(missing_ok=True)


ARQUIVOS_CHAMADO = ("hey_jarvis_v0.1.onnx", "melspectrogram.onnx", "embedding_model.onnx")


def pasta_chamado() -> Path:
    return caminhos.DADOS / "memoria" / "modelos" / "voz"


class Chamado:
    """Palavra de ativação LOCAL ("hey Jarvis", modelo openWakeWord em ONNX, ~2 ms por 80 ms de áudio na CPU). Não substitui o nome dito
    (que o Whisper continua achando): soma, e responde mesmo quando a transcrição erra o nome."""

    def __init__(self, limiar: float = 0.5):
        from openwakeword.model import Model
        d = str(pasta_chamado()) + os.sep
        self.m = Model(wakeword_models=[d + ARQUIVOS_CHAMADO[0]], inference_framework="onnx",
                       melspec_model_path=d + ARQUIVOS_CHAMADO[1], embedding_model_path=d + ARQUIVOS_CHAMADO[2])
        self.limiar = limiar
        self.buf = np.zeros(0, np.int16)
        self.ultimo = 0.0

    @classmethod
    def criar(cls, limiar: float = 0.5):
        try:
            if all((pasta_chamado() / a).exists() for a in ARQUIVOS_CHAMADO):
                return cls(limiar)
        except Exception as e:
            print(f"[jarvis] palavra de ativação indisponível ({type(e).__name__})", flush=True)
        return None

    def alimentar(self, pcm: np.ndarray) -> float | None:
        self.buf = np.concatenate([self.buf, (np.clip(pcm, -1, 1) * 32767).astype(np.int16)])
        pico = 0.0
        while len(self.buf) >= 1280:
            bloco, self.buf = self.buf[:1280], self.buf[1280:]
            pico = max(pico, max(self.m.predict(bloco).values()))
        agora = time.monotonic()
        if pico >= self.limiar and agora - self.ultimo > 2.5:
            self.ultimo = agora
            return float(pico)
        return None


PALAVRAS_PENDENTES = {"e", "que", "de", "do", "da", "dos", "das", "no", "na", "para", "pra", "com", "mas", "ou", "a", "o", "um", "uma", "se", "porque", "quando",
                      "como", "em", "por", "ao", "aos", "entao", "tambem", "depois", "tipo", "ai", "jarvis"}
ESPERA_CONTINUACAO_S = 1.1


def texto_incompleto(texto: str) -> bool:
    """Parece que a pessoa parou NO MEIO da frase (termina em vírgula, conjunção/preposição, ou só o nome "Jarvis")?"""
    t = (texto or "").strip()
    if not t:
        return False
    if t.endswith((",", ":", ";", "-", "—")):
        return True
    palavras = _norm(t)
    if not palavras:
        return False
    return palavras[-1] in PALAVRAS_PENDENTES and not t.endswith(("?", "!"))


def texto_completo(texto: str) -> bool:
    t = (texto or "").strip()
    return t.endswith((".", "?", "!", "…")) and not texto_incompleto(t) and len(_norm(t)) >= 2


class SessaoSTT:
    def __init__(self, transcritor: Transcritor, emitir, fim_ms: int = 480, registrar_metrica=None, sensibilidade: str = "media", chamado: "Chamado | None" = None):
        self.t = transcritor
        self.chamado = chamado
        self.emitir = emitir                       # async: emitir(dict)
        self.seg = Segmentador(fim_ms=fim_ms, sensibilidade=sensibilidade)
        self.ligado = False
        self.registrar_metrica = registrar_metrica
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt")
        self._pendentes = 0
        self._spec: dict | None = None             # transcrição especulativa em andamento: {"tarefa": Task, "valida": bool}
        self.ao_iniciar = None                     # async: chamado quando uma fala COMEÇA (aquece as conexões de rede)
        self._seguro: dict | None = None           # fala que parece cortada no meio: espera ~1 s para juntar com a continuação
        self.continuacao_s = ESPERA_CONTINUACAO_S
        self._cadeia = None

    def ligar(self, ligado: bool):
        if ligado == self.ligado:
            return
        self.ligado = ligado
        if not ligado:
            self.seg.reiniciar()
            self.seg._resto = np.zeros(0, np.float32)
            self._spec = None

    def falando(self, sim: bool):
        self.seg.falando(sim)

    async def alimentar(self, dados: bytes):
        if not self.ligado or len(dados) < 2:
            return
        pcm = np.frombuffer(dados[: len(dados) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
        if self.chamado is not None:
            try:
                pontuacao = self.chamado.alimentar(pcm)
            except Exception:
                pontuacao = None
            if pontuacao:
                await self.emitir({"tipo": "chamado", "pontuacao": round(pontuacao, 2)})
        if not self.t.pronto:
            return
        for ev in self.seg.alimentar(pcm):
            tipo = ev[0]
            if tipo == "inicio":
                await self.emitir({"tipo": "vad", "fala": True})
                if self.ao_iniciar:
                    asyncio.get_running_loop().create_task(self.ao_iniciar())
            elif tipo == "pre-fim":                    # silêncio de 240 ms: já começa a transcrever (se a fala não voltar, o texto sai pronto)
                tarefa = asyncio.get_running_loop().create_task(self._transcrever(ev[1]))
                self._spec = {"tarefa": tarefa, "valida": True, "audio": ev[1], "usada": False}
                tarefa.add_done_callback(lambda t, spec=self._spec: asyncio.get_running_loop().create_task(self._spec_pronta(spec, t)))
            elif tipo == "retomou":
                if self._spec:
                    self._spec["valida"] = False
            elif tipo == "descartado":
                self._spec = None
                registrar({"tipo": "ruido", "motivo": ev[1], "dur_ms": ev[2], "nivel_db": round(ev[3], 1)})
                if len(ev) > 4:
                    _despejar(ev[4], "desc_" + ev[1])
                await self.emitir({"tipo": "vad", "fala": False, "descartado": ev[1]})
            elif tipo == "fim":
                await self.emitir({"tipo": "vad", "fala": False, "transcrevendo": True})
                spec, self._spec = self._spec, None
                if spec and spec.get("usada"):
                    continue                              # já foi entregue antes (fim antecipado pelo texto)
                anterior = self._cadeia                 # as falas são concluídas EM ORDEM (uma continuação nunca passa na frente da fala que ela completa)
                self._cadeia = asyncio.get_running_loop().create_task(self._concluir(spec, ev[1], ev[2], ev[3], anterior))

    async def _spec_pronta(self, spec: dict, tarefa):
        """A transcrição especulativa terminou. Se a frase está COMPLETA (termina em ponto) e a pessoa continua calada, entrega já, sem esperar o resto do silêncio."""
        try:
            r = tarefa.result()
        except Exception:
            return
        if not r or not r["texto"] or spec is not self._spec or not spec["valida"] or spec["usada"] or self._seguro:
            return
        if not texto_completo(r["texto"]) or not self.seg.dentro or self.seg.silencio < self.seg.spec_q:
            return
        spec["usada"] = True
        audio = spec["audio"]
        dur = int(len(audio) / TAXA * 1000)
        nivel = float(np.percentile(self.seg.niveis, 90)) if self.seg.niveis else -60.0
        self.seg.reiniciar()
        self._spec = None
        await self.emitir({"tipo": "vad", "fala": False, "transcrevendo": True})
        await self._concluir({"tarefa": tarefa, "valida": True}, audio, dur, nivel)

    async def _transcrever(self, audio: np.ndarray):
        if self._pendentes >= 3:                   # fila cheia: a máquina não está dando conta; descarta em vez de atrasar tudo
            return None
        self._pendentes += 1
        t0 = time.perf_counter()
        try:
            texto, confianca, motivo = await asyncio.get_running_loop().run_in_executor(self._pool, self.t.transcrever, audio)
        except Exception as e:
            await self.emitir({"tipo": "aviso", "texto": f"Falha ao reconhecer a voz ({type(e).__name__})."})
            return None
        finally:
            self._pendentes -= 1
        return {"texto": texto, "confianca": confianca, "motivo": motivo, "ms": round((time.perf_counter() - t0) * 1000)}

    async def _soltar_seguro(self, seguro: dict):
        await asyncio.sleep(self.continuacao_s)
        while self._seguro is seguro and self.seg.dentro:     # ele está falando de novo agora: espera terminar para juntar
            await asyncio.sleep(0.3)
        if self._seguro is seguro:
            self._seguro = None
            await self._entregar(seguro["r"], seguro["audio"], seguro["dur"], seguro["nivel"], seguro["spec"])

    async def _concluir(self, spec, audio: np.ndarray, duracao_ms: int, nivel_db: float, anterior=None):
        if anterior is not None and not anterior.done():
            try:
                await anterior
            except Exception:
                pass
        seguro, self._seguro = self._seguro, None
        if seguro:                                   # continuação de uma fala cortada no meio: junta os dois trechos e transcreve de novo
            audio = np.concatenate([seguro["audio"], np.zeros(int(0.25 * TAXA), np.float32), audio])
            duracao_ms += seguro["dur"] + 250
            spec = None
        if spec and spec["valida"]:
            r = await spec["tarefa"]                # a transcrição especulativa já estava rodando: normalmente já terminou
            especulativa = True
        else:
            r = await self._transcrever(audio)
            especulativa = False
        if r is None:
            return
        if r["texto"] and texto_incompleto(r["texto"]) and duracao_ms < 10000 and not seguro:
            seg = {"r": r, "audio": audio, "dur": duracao_ms, "nivel": nivel_db, "spec": especulativa}
            self._seguro = seg                       # parece que ele vai continuar: espera ~1 s antes de responder
            asyncio.get_running_loop().create_task(self._soltar_seguro(seg))
            return
        await self._entregar(r, audio, duracao_ms, nivel_db, especulativa)

    async def _entregar(self, r, audio: np.ndarray, duracao_ms: int, nivel_db: float, especulativa: bool):
        if self.registrar_metrica:
            self.registrar_metrica({"stt_audio_ms": duracao_ms, "stt_transcricao_ms": r["ms"]})
        if r["texto"]:
            _despejar(audio, "ok_" + r["texto"])
            id_ = registrar({"tipo": "fala", "texto": r["texto"], "confianca": round(r["confianca"], 2), "dur_ms": duracao_ms,
                             "nivel_db": round(nivel_db, 1), "ms": r["ms"], "especulativa": especulativa})
            await self.emitir({"tipo": "transcricao", "id": id_, "texto": r["texto"], "final": True, "confianca": round(r["confianca"], 2),
                               "duracao_ms": duracao_ms, "transcricao_ms": r["ms"], "nivel_db": round(nivel_db, 1)})
        else:
            _despejar(audio, "whisper_" + r["motivo"])
            registrar({"tipo": "ruido", "motivo": r["motivo"], "dur_ms": duracao_ms, "nivel_db": round(nivel_db, 1), "ms": r["ms"]})
            await self.emitir({"tipo": "vad", "fala": False, "descartado": r["motivo"]})
