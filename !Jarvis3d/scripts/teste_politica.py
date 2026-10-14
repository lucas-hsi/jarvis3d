"""Política de autorização 'esperta': o que é pedido e de baixo risco não pede clique; leitura de conteúdo de fora trava o controle automático."""
import os
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
os.environ["JARVIS_MEMORIA_DIR"] = tempfile.mkdtemp(prefix="jarvis_pol_")
os.environ["JARVIS_SEM_VOZ"] = "1"
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
import server  # noqa: E402

ok = True


def checar(c, t):
    global ok
    ok &= bool(c)
    print("  [%s] %s" % ("OK" if c else "FALHOU", t))


class WS:
    async def send_text(self, *_): pass
    async def send_json(self, *_): pass


s = server.Sessao(WS())
server.CFG["autorizacao"] = "esperta"
server.CFG.pop("confirmar_camera", None)
print("POLÍTICA ESPERTA")
checar(s.liberado("camera"), "câmera pedida pelo usuário: sem confirmação")
checar(s.liberado("controle"), "controle de janelas num pedido limpo: sem confirmação")
for ferr in ("pesquisar_web", "ler_pagina", "email_ler", "navegador_ver", "ver_tela", "agenda_listar", "youtube_buscar"):
    s.turno_externo = False
    import asyncio

    class B:  # bloco de ferramenta falso: só precisamos do efeito de marcar o turno
        name, input, id = ferr, {}, "x"
    server.SIMULAR = True
    asyncio.run(server.rodar_ferramenta(s, B()))
    checar(s.turno_externo and not s.liberado("controle"), f"depois de {ferr} o controle volta a pedir confirmação")
s.turno_externo = False
checar(s.liberado("controle"), "turno novo: libera de novo")
checar(not s.liberado("deletar_tudo"), "qualquer outra coisa nunca é liberada por aqui")
print("POLÍTICA ANTIGA (sempre_perguntar)")
server.CFG["autorizacao"] = "sempre_perguntar"
checar(not s.liberado("camera") and not s.liberado("controle"), "tudo volta a pedir confirmação")
server.CFG["autorizacao"] = "esperta"; server.CFG["confirmar_camera"] = True
checar(not s.liberado("camera"), "confirmar_camera=true exige confirmação só da câmera")
print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
sys.exit(0 if ok else 1)
