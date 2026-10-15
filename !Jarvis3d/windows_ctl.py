"""
Controle do Windows: volume, mídia, janelas, mouse e teclado.
Só ctypes (nada para instalar). As decisões de segurança (confirmar, limitar) ficam em ferramentas.py.
"""

import ctypes
import re
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
try:  # coordenadas em pixels reais, iguais às do print da tela
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

ULONG_PTR = ctypes.c_size_t

# tamanho do último print (real x enviado ao modelo), para converter coordenadas de clique
TELA = {"orig": (0, 0), "env": (0, 0)}


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _UNIAO(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _UNIAO)]


KEYUP, UNICODE, EXTENDED = 0x2, 0x4, 0x1

TECLAS = {
    "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "space": 0x20, "espaco": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "windows": 0x5B,
    "printscreen": 0x2C,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
}
ESTENDIDAS = {0x2E, 0x24, 0x23, 0x21, 0x22, 0x26, 0x28, 0x25, 0x27, 0x5B}


def _vk(nome: str) -> int:
    n = nome.strip().lower()
    if n in TECLAS:
        return TECLAS[n]
    if len(n) == 1 and n.isalnum():
        return ord(n.upper())
    raise ValueError(f"Tecla desconhecida: '{nome}'.")


def _enviar(entradas: list[_INPUT]):
    arr = (_INPUT * len(entradas))(*entradas)
    user32.SendInput(len(entradas), arr, ctypes.sizeof(_INPUT))


def _tecla(vk: int, subir: bool) -> _INPUT:
    flags = (EXTENDED if vk in ESTENDIDAS else 0) | (KEYUP if subir else 0)
    return _INPUT(1, _UNIAO(ki=_KEYBDINPUT(vk, 0, flags, 0, 0)))


def combo_para_teclas(combo: str) -> list[int]:
    partes = [p for p in re.split(r"\s*\+\s*", combo.strip()) if p]
    if not partes:
        raise ValueError("Combinação vazia.")
    return [_vk(p) for p in partes]


def pressionar(combo: str):
    """'ctrl+c', 'enter', 'alt+tab'... Segura todas, solta na ordem inversa."""
    vks = combo_para_teclas(combo)
    _enviar([_tecla(v, False) for v in vks])
    time.sleep(0.05)
    _enviar([_tecla(v, True) for v in reversed(vks)])


def digitar(texto: str, atraso: float = 0.008):
    """Digita texto (inclui acentos e emojis). Quebra de linha vira Enter."""
    for ch in texto:
        if ch == "\n":
            pressionar("enter")
        else:
            dados = ch.encode("utf-16-le")
            for i in range(0, len(dados), 2):
                unidade = int.from_bytes(dados[i:i + 2], "little")
                _enviar([_INPUT(1, _UNIAO(ki=_KEYBDINPUT(0, unidade, UNICODE, 0, 0))),
                         _INPUT(1, _UNIAO(ki=_KEYBDINPUT(0, unidade, UNICODE | KEYUP, 0, 0)))])
        time.sleep(atraso)


# ------------------------------------------------------------------ mouse

def tamanho_da_tela() -> tuple[int, int]:
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def posicao_do_mouse() -> tuple[int, int]:
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


# marcado enquanto o próprio Jarvis aciona teclas/mouse, para o vigia não confundir com o usuário
EM_ACAO = {"v": False}


def tecla_pressionada(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def mouse_no_canto() -> bool:
    """Freio de emergência: mouse jogado no canto superior esquerdo."""
    x, y = posicao_do_mouse()
    return x <= 2 and y <= 2


def clicar(x: int, y: int, botao: str = "esquerdo", duplo: bool = False):
    w, h = tamanho_da_tela()
    x, y = max(3, min(w - 1, int(x))), max(3, min(h - 1, int(y)))  # nunca clica no canto de emergência
    user32.SetCursorPos(x, y)
    time.sleep(0.08)
    descer, subir = {"esquerdo": (0x2, 0x4), "direito": (0x8, 0x10), "meio": (0x20, 0x40)}[botao]
    for _ in range(2 if duplo else 1):
        user32.mouse_event(descer, 0, 0, 0, 0)
        user32.mouse_event(subir, 0, 0, 0, 0)
        time.sleep(0.06)


def mover_mouse(x: int, y: int):
    w, h = tamanho_da_tela()
    user32.SetCursorPos(max(3, min(w - 1, int(x))), max(3, min(h - 1, int(y))))


def mouse_botao(baixo: bool, botao: str = "esquerdo"):
    """Aperta ou solta um botão do mouse (para ARRASTAR: aperta, move, solta)."""
    descer, subir = {"esquerdo": (0x2, 0x4), "direito": (0x8, 0x10), "meio": (0x20, 0x40)}[botao]
    user32.mouse_event(descer if baixo else subir, 0, 0, 0, 0)


def zoom(passos: int):
    """Ctrl + roda do mouse: zoom em navegadores, Office, mapas, visualizadores. Positivo = aproxima."""
    user32.keybd_event(0x11, 0, 0, 0)
    try:
        user32.mouse_event(0x0800, 0, 0, ctypes.c_ulong(int(passos * 120) & 0xFFFFFFFF).value, 0)
    finally:
        user32.keybd_event(0x11, 0, KEYUP, 0)


def rolar(passos: int):
    """Positivo = para cima, negativo = para baixo (1 passo ≈ 3 linhas)."""
    user32.mouse_event(0x0800, 0, 0, ctypes.c_ulong(int(passos * 120) & 0xFFFFFFFF).value, 0)


# ------------------------------------------------------------------ volume e mídia

def _tecla_de_midia(vk: int):
    user32.keybd_event(vk, 0, EXTENDED, 0)
    user32.keybd_event(vk, 0, EXTENDED | KEYUP, 0)


def volume(acao: str, valor: int = 0):
    if acao == "mudo":
        _tecla_de_midia(0xAD)
    elif acao in ("subir", "descer"):
        for _ in range(max(1, min(25, round((valor or 10) / 2)))):
            _tecla_de_midia(0xAF if acao == "subir" else 0xAE)
            time.sleep(0.01)
    elif acao == "definir":
        alvo = max(0, min(100, int(valor)))
        for _ in range(50):
            _tecla_de_midia(0xAE)
        for _ in range(round(alvo / 2)):
            _tecla_de_midia(0xAF)
            time.sleep(0.01)
    else:
        raise ValueError("Ação de volume desconhecida.")


def midia(acao: str):
    vk = {"play_pause": 0xB3, "proxima": 0xB0, "anterior": 0xB1, "parar": 0xB2}.get(acao)
    if vk is None:
        raise ValueError("Ação de mídia desconhecida.")
    _tecla_de_midia(vk)


# ------------------------------------------------------------------ janelas

_ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _titulo(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def listar_janelas() -> list[tuple[int, str]]:
    achadas: list[tuple[int, str]] = []

    def cada(hwnd, _):
        if user32.IsWindowVisible(hwnd) and not (user32.GetWindowLongW(hwnd, -20) & 0x80):  # sem janelas-ferramenta
            t = _titulo(hwnd)
            if t and t not in ("Program Manager",):
                achadas.append((int(hwnd), t))
        return True

    user32.EnumWindows(_ENUM(cada), 0)
    return achadas


def janela_em_foco() -> str:
    return _titulo(user32.GetForegroundWindow())


def acao_na_janela(trecho: str, acao: str) -> str:
    alvo = next(((h, t) for h, t in listar_janelas() if trecho.lower() in t.lower()), None)
    if alvo is None:
        raise ValueError(f"Nenhuma janela aberta com '{trecho}' no título.")
    hwnd, titulo = alvo
    if acao == "focar":
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
        user32.keybd_event(0x12, 0, 0, 0)          # Alt libera o pedido de foco
        user32.keybd_event(0x12, 0, KEYUP, 0)
        user32.SetForegroundWindow(hwnd)
    elif acao == "minimizar":
        user32.ShowWindow(hwnd, 6)
    elif acao == "maximizar":
        user32.ShowWindow(hwnd, 3)
    elif acao == "restaurar":
        user32.ShowWindow(hwnd, 9)
    elif acao == "fechar":
        user32.PostMessageW(hwnd, 0x10, 0, 0)       # WM_CLOSE: fecha com educação, o programa pode perguntar se salva
    else:
        raise ValueError("Ação de janela desconhecida.")
    return titulo


def mostrar_area_de_trabalho():
    pressionar("win+d")


def bloquear_tela():
    user32.LockWorkStation()
