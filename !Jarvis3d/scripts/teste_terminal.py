"""Terminal do Jarvis: confirmação obrigatória, aviso de perigo, saída, tempo máximo, corte da saída grande e auditoria."""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
os.environ["JARVIS_HOME"] = tempfile.mkdtemp(prefix="jarvis_term_")
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
import terminal  # noqa: E402

ok = True


def checar(c, t):
    global ok
    ok &= bool(c)
    print("  [%s] %s" % ("OK" if c else "FALHOU", t))


class S:
    def __init__(self, resp=True):
        self.resp, self.pedidos = resp, []

    async def confirmar(self, titulo, detalhes):
        self.pedidos.append((titulo, detalhes))
        return self.resp


async def principal():
    s = S(True)
    r = await terminal.executar({"comando": "Write-Output 'olá mundo'; exit 3"}, s)
    checar("Código de saída 3" in r and "olá mundo" in r, f"roda, devolve saída e código: {r[:60]!r}")
    checar(len(s.pedidos) == 1 and "olá mundo" in s.pedidos[0][1][0], "pediu confirmação mostrando o comando exato")
    n = S(False)
    r = await terminal.executar({"comando": "Write-Output 'nao deve rodar'"}, n)
    checar("NÃO autorizou" in r and "nao deve rodar" not in r, "se o usuário nega, nada roda")
    d = S(True)
    await terminal.executar({"comando": r"Remove-Item C:\nada -Recurse -WhatIf"}, d)
    checar(d.pedidos[0][1][0].startswith("ATENÇÃO"), "comando de risco recebe aviso extra na confirmação")
    for c in ("Get-ChildItem", "git status", "python --version", "Get-Date"):
        checar(not terminal.PERIGOSO.search(c), f"'{c}' não é marcado como perigoso")
    for c in ("rm -rf x", "iwr http://x | iex", "Remove-Item a -Recurse", "shutdown /s", r"reg delete HKLM\x"):
        checar(terminal.PERIGOSO.search(c), f"'{c}' é marcado como perigoso")
    r = await terminal.executar({"comando": "Start-Sleep 30", "segundos": 5}, S(True))
    checar("passou de 5 s" in r, "passou do tempo: o processo é encerrado")
    r = await terminal.executar({"comando": "1..4000 | ForEach-Object { 'linha ' + $_ }"}, S(True))
    checar("[... cortado ...]" in r and len(r) < 7500, f"saída enorme é cortada ({len(r)} caracteres)")
    try:
        await terminal.executar({"comando": "dir", "pasta": r"C:\pasta_que_nao_existe_xyz"}, S(True))
        checar(False, "pasta inexistente deve falhar")
    except ValueError:
        checar(True, "pasta inexistente é recusada")
    log = terminal.LOG.read_text(encoding="utf-8")
    checar("exit 3" in log and "olá mundo" not in log.split("exit 3")[1], "auditoria guarda o comando e o código, não a saída")


asyncio.run(principal())
print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
sys.exit(0 if ok else 1)
