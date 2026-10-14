"""
Ouvinte de palmas do Jarvis.

Fica de ouvido no microfone medindo só o volume (nada é gravado nem enviado).
Duas palmas seguidas:
  - se o Jarvis já está aberto, ele acorda de novo e cumprimenta;
  - se não está, sobe o servidor e abre a tela dele.

Uso:  .venv\\Scripts\\pythonw.exe palmas.py          (sem janela)
      .venv\\Scripts\\python.exe palmas.py --calibrar (mostra o volume para ajustar)
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import sounddevice as sd

BASE = Path(__file__).parent
if sys.stdout is None:  # rodando com pythonw (sem janela): guarda o log num arquivo
    sys.stdout = sys.stderr = open(BASE / "palmas.log", "a", encoding="utf-8", buffering=1)
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
PORTA = int(CFG.get("porta", 8340))
SENSIBILIDADE = float(CFG.get("palmas_sensibilidade", 1.0))  # maior = mais sensível
URL = f"http://127.0.0.1:{PORTA}"
PERFIL_CHROME = Path(os.environ.get("LOCALAPPDATA", str(BASE))) / "JarvisPerfil"

TAXA = 44100
BLOCO = 512                 # ~11 ms: palmas são picos curtos
PICO_MINIMO = 0.045         # volume mínimo de uma palma (as suas medidas: 0,05 a 0,35; clique de teclado ~0,03)
SALTO = 10.0                # quantas vezes acima do ruído de fundo
AGUDO_MINIMO = 0.15         # fatia da energia acima de 1,5 kHz: palma é "seca" e aguda; batida em mesa e grave de caixa de som não
DURACAO_MAX_PALMA = 0.45    # o eco do microfone do notebook estica a palma (medido: até ~330 ms)
SILENCIO_ANTES_1A = 0.5     # a 1ª palma precisa vir depois de silêncio (descarta música e conversa)
SILENCIO_ANTES_2A = 0.10    # a 2ª, depois do eco da 1ª
INTERVALO_MIN, INTERVALO_MAX = 0.20, 0.90
RAZAO_MAX_ENTRE_PALMAS = 4.0  # as duas palmas têm força parecida
CONFIRMACAO = 0.65          # espera isso após a 2ª palma: se vier uma 3ª é aplauso/ritmo, não dispara
RESFRIAMENTO = 20.0         # depois de disparar, ignora por tantos segundos

CALIBRAR = "--calibrar" in sys.argv


def servidor_no_ar() -> dict | None:
    try:
        with urllib.request.urlopen(f"{URL}/api/saude", timeout=1.5) as r:
            return json.loads(r.read())
    except Exception:
        return None


def achar_chrome() -> str | None:
    for caminho in (
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
    ):
        if os.path.exists(caminho):
            return caminho
    return None


def subir_servidor():
    python = BASE / ".venv" / "Scripts" / "python.exe"
    log = open(BASE / "jarvis.log", "a", encoding="utf-8", buffering=1)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    comando = [str(python), str(BASE / "server.py")]
    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        # Sai do "job" do terminal que chamou, para fechar o terminal não derrubar o servidor.
        subprocess.Popen(comando, cwd=BASE, stdout=log, stderr=log, env=env,
                         creationflags=flags | 0x01000000)  # CREATE_BREAKAWAY_FROM_JOB
    except OSError:
        subprocess.Popen(comando, cwd=BASE, stdout=log, stderr=log, env=env, creationflags=flags)
    for _ in range(40):
        time.sleep(0.5)
        if servidor_no_ar():
            return True
    return False


def abrir_tela():
    navegador = achar_chrome()
    if navegador is None:
        os.startfile(f"{URL}/?auto=1")
        return
    # Perfil próprio: as opções valem de verdade (mesmo com o Chrome aberto) e o
    # microfone liberado uma vez fica liberado. A janela vem sem barras, tipo aplicativo.
    PERFIL_CHROME.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([
        navegador, f"--user-data-dir={PERFIL_CHROME}", f"--app={URL}/?auto=1",
        "--autoplay-policy=no-user-gesture-required", "--start-maximized",
        "--no-first-run", "--no-default-browser-check",
    ])


def disparar():
    estado = servidor_no_ar()
    if estado and estado.get("janelas", 0) > 0:
        # Já está aberto: só vale como "acordar" se ele estiver em espera (depois de "pode dormir").
        # Palma, aplauso ou barulho com ele ativo não deve fazer nada.
        if estado.get("janelas_em_espera", 0) == 0:
            print("[palmas] ignorado: o Jarvis já está aberto e ativo.", flush=True)
            return
        req = urllib.request.Request(f"{URL}/api/ativar", method="POST", data=b"")
        try:
            urllib.request.urlopen(req, timeout=3).read()
            print("[palmas] Jarvis em espera: acordando.", flush=True)
            return
        except Exception as e:
            print(f"[palmas] não consegui acordar: {e}", flush=True)
    if not estado and not subir_servidor():
        print("[palmas] o servidor não subiu; veja jarvis.log", flush=True)
        return
    abrir_tela()
    print("[palmas] tela aberta.", flush=True)


class Detector:
    """Reconhece DUAS palmas: sons agudos e secos, de início brusco, depois de silêncio, de força parecida,
    sem uma terceira em seguida. Música, voz, teclado, batida em mesa e aplauso ficam de fora."""

    def __init__(self):
        self.fundo = 0.004          # ruído de fundo (média móvel lenta)
        self.em_pico = False
        self.pico_em = 0.0
        self.pico_max = 0.0
        self.pico_agudo = 0.0
        self.silencio_antes = 0.0
        self.ultimo_alto = 0.0      # última vez que houve som acima da metade do limite
        self.anterior = 0.0         # rms do bloco anterior (para medir o início brusco)
        self.bruto = True
        self.palmas: list[tuple[float, float]] = []   # (instante, força) das palmas válidas recentes
        self.confirmar_em = 0.0
        self.bloqueado_ate = 0.0

    def bloco(self, rms: float, agora: float, agudo: float = 1.0):
        limite = max(PICO_MINIMO / SENSIBILIDADE, self.fundo * SALTO)
        if CALIBRAR:
            print(f"rms={rms:.3f} agudo={agudo:.2f} fundo={self.fundo:.3f} limite={limite:.3f} {'#' * int(rms * 120)}", flush=True)

        if self.confirmar_em and agora >= self.confirmar_em:
            self.confirmar_em = 0.0
            if len(self.palmas) == 2:
                self.palmas.clear()
                self.bloqueado_ate = agora + RESFRIAMENTO
                print("[palmas] duas palmas confirmadas!", flush=True)
                disparar()

        if self.em_pico:
            if rms > self.pico_max:
                self.pico_max, self.pico_agudo = rms, agudo
        if rms > limite and not self.em_pico:
            self.em_pico = True
            self.pico_em = agora
            self.pico_max, self.pico_agudo = rms, agudo
            self.silencio_antes = agora - self.ultimo_alto
            self.bruto = self.anterior < 0.4 * rms          # início brusco: o bloco anterior era bem mais fraco
        elif self.em_pico and rms < limite * 0.6:
            self.em_pico = False
            self._fim_de_pico(agora, limite)
        elif self.em_pico and agora - self.pico_em > 0.7:
            self.em_pico = False
            print(f"[palmas] som longo ignorado (rms={self.pico_max:.3f})", flush=True)

        if rms > limite * 0.5:
            self.ultimo_alto = agora
        if not self.em_pico and rms < limite:
            self.fundo = 0.995 * self.fundo + 0.005 * min(rms, 0.1)
        self.anterior = rms

    def _fim_de_pico(self, agora: float, limite: float):
        duracao = agora - self.pico_em
        precisa_silencio = SILENCIO_ANTES_2A if self.palmas else SILENCIO_ANTES_1A
        motivo = None
        if duracao > DURACAO_MAX_PALMA:
            motivo = "longo demais"
        elif self.pico_agudo < AGUDO_MINIMO:
            motivo = "grave demais (não é palma)"
        elif not self.bruto:
            motivo = "início suave"
        elif self.silencio_antes < precisa_silencio:
            motivo = "veio no meio de barulho"
        print(f"[palmas] pico rms={self.pico_max:.3f} agudo={self.pico_agudo:.2f} dur={duracao*1000:.0f}ms "
              f"antes={self.silencio_antes:.2f}s -> {'palma' if motivo is None else 'ignorado: ' + motivo}", flush=True)
        if motivo is None:
            self._palma(self.pico_em, self.pico_max)

    def _palma(self, quando: float, forca: float):
        if quando < self.bloqueado_ate:
            return
        self.palmas = [(t, f) for t, f in self.palmas if quando - t <= 2.5] + [(quando, forca)]
        if len(self.palmas) >= 3:                       # aplauso ou ritmo
            print("[palmas] 3+ batidas seguidas: aplauso/ritmo, ignorado.", flush=True)
            self.palmas.clear()
            self.confirmar_em = 0.0
            self.bloqueado_ate = quando + 3.0
            return
        if len(self.palmas) == 2:
            (t1, f1), (t2, f2) = self.palmas
            intervalo = t2 - t1
            if INTERVALO_MIN <= intervalo <= INTERVALO_MAX and max(f1, f2) / min(f1, f2) <= RAZAO_MAX_ENTRE_PALMAS:
                self.confirmar_em = quando + CONFIRMACAO   # só dispara se não vier uma 3ª batida
            else:
                self.palmas = [self.palmas[-1]]


JANELA_FREQ = np.fft.rfftfreq(BLOCO, 1 / TAXA)


def principal():
    # Só um ouvinte por vez: a porta serve de trava.
    trava = socket.socket()
    try:
        trava.bind(("127.0.0.1", PORTA + 1))
    except OSError:
        print("[palmas] já existe um ouvinte rodando.", flush=True)
        return
    detector = Detector()

    def callback(dados, quadros, tempo, status):
        amostra = dados[:, 0]
        rms = float(np.sqrt(np.mean(amostra ** 2)))
        espectro = np.abs(np.fft.rfft(amostra * np.hanning(len(amostra)))) ** 2
        total = float(espectro[JANELA_FREQ > 80].sum()) + 1e-12
        agudo = float(espectro[JANELA_FREQ > 1500].sum()) / total
        detector.bloco(rms, time.monotonic(), agudo)

    print(f"[palmas] ouvindo (sensibilidade {SENSIBILIDADE}). Ctrl+C para sair.", flush=True)
    with sd.InputStream(samplerate=TAXA, blocksize=BLOCO, channels=1, dtype="float32", callback=callback):
        while True:
            time.sleep(1)


if __name__ == "__main__":
    principal()
