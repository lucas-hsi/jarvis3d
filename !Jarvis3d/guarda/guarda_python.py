"""
Guarda do Jarvis para scripts Python da Oficina (roda com o Python do usuário, não com o do Jarvis).

Instala um "audit hook" (PEP 578) ANTES de rodar o script. Esse gancho é do próprio interpretador e não pode ser removido
pelo script. Ele barra, com PermissionError e uma mensagem clara:
- gravar, apagar, renomear ou mudar permissões FORA da pasta do projeto (a Oficina) e da pasta temporária;
- ler pastas de segredos (.ssh, dados do Jarvis, senhas e cookies dos navegadores);
- abrir outros programas (subprocess, os.system, os.startfile, multiprocessing) e matar processos;
- acessar a internet (só o próprio computador, 127.0.0.1, é liberado), a menos que --rede tenha sido autorizado;
- carregar DLLs pelo ctypes e alterar o registro do Windows.

Uso: python -E -u guarda_python.py --raiz <pasta> --saida <arquivo.txt> [--rede] -- script.py [args...]
A saída do script vai para a tela E para --saida (o Jarvis lê de lá).
"""

import os
import sys
import tempfile

PREFIXO = "[GUARDA DO JARVIS]"


def _args():
    a = sys.argv[1:]
    if "--" not in a:
        print(f"{PREFIXO} uso: --raiz <pasta> --saida <arquivo> [--rede] -- script.py [args]")
        sys.exit(2)
    i = a.index("--")
    opcoes, resto = a[:i], a[i + 1:]
    raiz = saida = None
    rede = "--rede" in opcoes
    for k, v in zip(opcoes, opcoes[1:]):
        if k == "--raiz":
            raiz = v
        elif k == "--saida":
            saida = v
    if not raiz or not resto:
        print(f"{PREFIXO} faltou --raiz ou o script.")
        sys.exit(2)
    return os.path.realpath(raiz), saida, rede, resto


RAIZ, SAIDA, REDE, RESTO = _args()
TEMP = os.path.realpath(tempfile.gettempdir())
SCRIPT = os.path.realpath(RESTO[0])
LIBERADAS = [RAIZ, TEMP]
SEGREDOS = ("\\.ssh", "\\appdata\\roaming\\jarvis", "\\jarvis\\config.json", "\\jarvis\\segredos", "\\jarvis\\ajustes.json",
            "\\login data", "\\cookies", "\\web data", "\\local state", "\\.aws", "\\.git-credentials", "\\microsoft\\credentials",
            "\\microsoft\\protect", "\\.env")
LOCAL = {"127.0.0.1", "localhost", "::1", "0.0.0.0", ""}


# ------------------------------------------------------------------ saída em dobro (tela + arquivo que o Jarvis lê)
class _Tee:
    def __init__(self, tela, arquivo):
        self.tela, self.arquivo = tela, arquivo

    def write(self, s):
        try:
            self.tela.write(s)
            self.tela.flush()
        except Exception:
            pass
        try:
            self.arquivo.write(s)
            self.arquivo.flush()
        except Exception:
            pass
        return len(s)

    def flush(self):
        for f in (self.tela, self.arquivo):
            try:
                f.flush()
            except Exception:
                pass

    def isatty(self):
        return False

    def __getattr__(self, nome):
        return getattr(self.tela, nome)


if SAIDA:
    _arq = open(SAIDA, "w", encoding="utf-8", buffering=1)      # aberto ANTES da guarda (fica fora da Oficina, em .jarvis)
    sys.stdout = _Tee(sys.__stdout__, _arq)
    sys.stderr = _Tee(sys.__stderr__, _arq)
sys.dont_write_bytecode = True                                  # nada de .pyc em pastas do sistema


# ------------------------------------------------------------------ regras
def _caminho(p):
    if isinstance(p, int) or p is None:
        return None
    try:
        p = os.fsdecode(p)
    except TypeError:
        return None
    try:
        return os.path.realpath(os.path.abspath(p))
    except (OSError, ValueError):
        return p


def _liberado(c):
    if c is None:
        return True
    cl = os.path.normcase(c)
    return any(cl == os.path.normcase(b) or cl.startswith(os.path.normcase(b) + os.sep) for b in LIBERADAS)


def _segredo(c):
    return c is not None and any(s in os.path.normcase(c) for s in SEGREDOS)


def _barrar(motivo):
    msg = f"{PREFIXO} bloqueado: {motivo}"
    try:
        sys.stderr.write("\n" + msg + "\n")
    except Exception:
        pass
    raise PermissionError(msg)


ESCRITA = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
PROCESSOS = {"subprocess.Popen", "os.system", "os.exec", "os.spawn", "os.posix_spawn", "os.startfile", "os.startfile/2", "os.kill",
             "os.killpg", "_winapi.CreateProcess", "_winapi.OpenProcess", "_winapi.TerminateProcess", "_winapi.CreateJunction",
             "pty.spawn", "webbrowser.open"}
MEXE_EM_CAMINHO = {"os.remove": (0,), "os.rmdir": (0,), "os.rename": (0, 1), "os.replace": (0, 1), "os.mkdir": (0,), "os.chmod": (0,),
                   "os.chown": (0,), "os.link": (0, 1), "os.symlink": (0, 1), "os.truncate": (0,), "os.utime": (0,), "os.chflags": (0,),
                   "shutil.rmtree": (0,), "shutil.move": (0, 1), "shutil.copyfile": (1,), "shutil.copytree": (1,), "shutil.copymode": (1,),
                   "shutil.copystat": (1,), "shutil.chown": (0,), "shutil.unpack_archive": (1,), "shutil.make_archive": (0,)}
REGISTRO_ESCRITA = {"winreg.CreateKey", "winreg.DeleteKey", "winreg.DeleteValue", "winreg.SetValue", "winreg.SaveKey", "winreg.LoadKey",
                    "winreg.ConnectRegistry", "winreg.DisableReflectionKey", "winreg.EnableReflectionKey"}


def _host(endereco):
    if isinstance(endereco, tuple) and endereco:
        return str(endereco[0])
    return str(endereco or "")


def gancho(evento, args):
    if evento == "open":
        c = _caminho(args[0])
        modo = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else 0
        escreve = (isinstance(modo, str) and any(x in modo for x in "wax+")) or bool((flags or 0) & ESCRITA)
        if _segredo(c):
            _barrar(f"o script tentou abrir um arquivo de segredos ({c})")
        if escreve and not _liberado(c):
            _barrar(f"o script tentou gravar fora da Oficina ({c}). Só dá para gravar em {RAIZ}")
    elif evento in MEXE_EM_CAMINHO:
        for i in MEXE_EM_CAMINHO[evento]:
            if i < len(args):
                c = _caminho(args[i])
                if not _liberado(c):
                    _barrar(f"o script tentou mexer em '{c}' ({evento}) fora da Oficina")
    elif evento in PROCESSOS:
        _barrar(f"o script tentou abrir/fechar outro programa ({evento}). Scripts da Oficina não podem fazer isso")
    elif evento in ("ctypes.dlopen", "ctypes.dlsym", "ctypes.dlsym/handle"):
        _barrar("o script tentou carregar DLLs do Windows pelo ctypes")
    elif evento in REGISTRO_ESCRITA:
        _barrar(f"o script tentou alterar o registro do Windows ({evento})")
    elif evento in ("socket.connect", "socket.connect_ex", "socket.sendto", "socket.sendmsg"):
        if not REDE and _host(args[1] if len(args) > 1 else "") not in LOCAL:
            _barrar("o script tentou acessar a internet sem autorização (peça ao Jarvis para rodar com rede)")
    elif evento == "socket.getaddrinfo":
        if not REDE and str(args[0] if args else "") not in LOCAL:
            _barrar(f"o script tentou acessar '{args[0]}' na internet sem autorização")
    elif evento == "socket.bind":
        if _host(args[1] if len(args) > 1 else "") not in LOCAL and not REDE:
            _barrar("o script tentou abrir uma porta para a rede (só 127.0.0.1 é liberado)")


# ------------------------------------------------------------------ partida
def principal():
    import runpy
    if not _liberado(SCRIPT):
        print(f"{PREFIXO} o script precisa estar dentro da Oficina ({RAIZ}).")
        sys.exit(2)
    sys.argv = [SCRIPT] + RESTO[1:]
    sys.path[0] = os.path.dirname(SCRIPT)                      # imports do próprio projeto funcionam; a pasta do Jarvis sai do caminho
    os.chdir(os.path.dirname(SCRIPT))
    sys.addaudithook(gancho)
    runpy.run_path(SCRIPT, run_name="__main__")


if __name__ == "__main__":
    principal()
