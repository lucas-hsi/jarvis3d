"""Oficina do Jarvis: criar arquivo (com versão anterior guardada), caminhos fora da Oficina recusados, e a GUARDA do Python
barrando de verdade (gravar fora, abrir programa, internet, DLL, segredos) enquanto deixa o script trabalhar dentro da Oficina.
Janela OCULTA (JARVIS_TERMINAL_OCULTO=1); usa o Python do sistema."""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
os.environ["JARVIS_HOME"] = tempfile.mkdtemp(prefix="jarvis_of_")
os.environ["JARVIS_OFICINA"] = tempfile.mkdtemp(prefix="jarvis_oficina_")
os.environ["JARVIS_TERMINAL_OCULTO"] = "1"
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
import oficina  # noqa: E402

OF = Path(os.environ["JARVIS_OFICINA"])
FORA = Path(tempfile.mkdtemp(prefix="jarvis_fora_", dir=str(Path.home())))      # fora da Oficina e fora do temp
ok = True


def checar(c, t):
    global ok
    ok &= bool(c)
    print("  [%s] %s" % ("OK" if c else "FALHOU", t))


class S:
    def __init__(self, resp=True):
        self.resp, self.pedidos, self.msgs, self.turno_externo = resp, [], [], False

    async def confirmar(self, titulo, detalhes, nivel="medio"):
        self.pedidos.append((titulo, detalhes, nivel))
        return self.resp

    async def enviar(self, obj):
        self.msgs.append(obj)

    def liberado(self, o_que):
        return True


async def rodar_py(codigo, nome, s=None, **extra):
    s = s or S()
    await oficina.executar("oficina_escrever", {"caminho": f"testes/{nome}.py", "conteudo": codigo, "abrir": False}, s)
    return await oficina.executar("oficina_rodar", {"arquivo": f"testes/{nome}.py", **extra}, s), s


async def principal():
    s = S()
    r = await oficina.executar("oficina_escrever", {"caminho": "calc/app.py", "conteudo": "print('versão 1')\n", "abrir": False}, s)
    checar("Criado" in r and (OF / "calc" / "app.py").exists(), "cria arquivo numa subpasta da Oficina")
    checar(any(m.get("tipo") == "oficina" and m.get("evento") == "arquivo" for m in s.msgs), "a tela recebe o cartão do arquivo")
    r = await oficina.executar("oficina_escrever", {"caminho": "calc/app.py", "conteudo": "print('versão 2')\n", "abrir": False}, s)
    versoes = list((oficina.INTERNO / "versoes" / "calc").glob("app.py.*"))
    checar("versão anterior" in r and versoes and "versão 1" in versoes[0].read_text(encoding="utf-8"), "sobrescrever guarda a versão anterior")
    for ruim in ("../fora.txt", str(FORA / "x.txt"), "C:\\Windows\\x.txt", "calc/con.txt", "x.exe", ".env"):
        try:
            await oficina.executar("oficina_escrever", {"caminho": ruim, "conteudo": "x", "abrir": False}, s)
            checar(False, f"deveria recusar '{ruim}'")
        except ValueError:
            checar(True, f"recusa '{ruim}'")
    checar("app.py" in oficina.listar(), "lista a Oficina")

    if not oficina.python_exe():
        print("  [AVISO] sem Python do sistema: pulando a guarda")
        return
    r, _ = await rodar_py("open('saida.txt', 'w').write('ok')\nprint('gravou', open('saida.txt').read())\n", "dentro")
    checar("gravou ok" in r and "Código de saída 0" in r, "script grava DENTRO da Oficina normalmente")
    alvo = FORA / "invasao.txt"
    r, _ = await rodar_py(f"open(r'{alvo}', 'w').write('x')\n", "fora")
    checar("GUARDA DO JARVIS" in r and not alvo.exists(), "gravar FORA da Oficina é barrado")
    r, _ = await rodar_py("import subprocess\nsubprocess.run(['notepad.exe'])\n", "processo")
    checar("GUARDA DO JARVIS" in r and "outro programa" in r, "abrir outro programa é barrado")
    r, _ = await rodar_py("import os\nos.system('echo oi')\n", "system")
    checar("GUARDA DO JARVIS" in r, "os.system é barrado")
    r, _ = await rodar_py("import urllib.request\nurllib.request.urlopen('http://example.com', timeout=3)\n", "rede")
    checar("GUARDA DO JARVIS" in r and "internet" in r, "internet sem autorização é barrada")
    r, _ = await rodar_py("import ctypes\nctypes.windll.user32.MessageBoxW(0, 'x', 'x', 0)\n", "dll")
    checar("GUARDA DO JARVIS" in r and "DLL" in r, "ctypes/DLL é barrado")
    r, _ = await rodar_py("import os, shutil\nshutil.rmtree(os.path.expanduser('~/Documents'))\n", "rmtree")
    checar("GUARDA DO JARVIS" in r, "apagar pasta fora da Oficina é barrado")
    r, _ = await rodar_py("print(open(r'%s').read())\n" % (Path.home() / ".ssh" / "id_rsa"), "segredo")
    checar("GUARDA DO JARVIS" in r and "segredos" in r, "ler pasta de segredos é barrado")
    r, _ = await rodar_py("import socket\ns = socket.socket(); s.bind(('127.0.0.1', 0)); print('porta local ok')\n", "local")
    checar("porta local ok" in r, "servidor local (127.0.0.1) é liberado para pequenos sistemas")
    n = S(False)
    r, n = await rodar_py("print('x')\n", "comrede", n, rede=True)
    checar("NÃO autorizou" in r and n.pedidos and n.pedidos[0][2] == "alto", "pedir internet exige confirmação forte")
    r, _ = await rodar_py("import sys\nprint('args', sys.argv[1:])\nraise SystemExit(4)\n", "args", argumentos=["a", "b c"])
    checar("args ['a', 'b c']" in r and "Código de saída 4" in r, "argumentos e código de saída chegam certos")
    await oficina.executar("oficina_escrever", {"caminho": "testes/apaga.ps1", "conteudo": "Remove-Item C:\\Windows -Recurse\n", "abrir": False}, s)
    r = await oficina.executar("oficina_rodar", {"arquivo": "testes/apaga.ps1"}, S())
    checar("BLOQUEADO" in r, "script .ps1 destrutivo é bloqueado")
    await oficina.executar("oficina_escrever", {"caminho": "testes/ola.ps1", "conteudo": "Write-Output 'olá do ps1'\n", "abrir": False}, s)
    r = await oficina.executar("oficina_rodar", {"arquivo": "testes/ola.ps1"}, S())
    checar("olá do ps1" in r, "script .ps1 seguro roda")


asyncio.run(principal())
try:
    FORA.rmdir()
except OSError:
    pass
print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
sys.exit(0 if ok else 1)
