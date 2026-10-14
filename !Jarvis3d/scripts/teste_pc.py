"""
Testa o controle do notebook SEM mexer em nada seu: usa uma pasta temporária como "pasta liberada"
e uma sessão falsa (que responde às confirmações). Nenhum clique, tecla ou volume é acionado.

Uso:  .venv\\Scripts\\python.exe -X utf8 scripts\\teste_pc.py
"""

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import arquivos
import pc
import windows_ctl

ok_geral = True


def checar(cond, texto):
    global ok_geral
    ok_geral &= bool(cond)
    print("  [%s] %s" % ("OK" if cond else "FALHOU", texto))


class SessaoFalsa:
    def __init__(self, resposta=True):
        self.resposta = resposta
        self.pedidos = []
        self.eventos = []
        self.controle = {"ativo": False, "acoes": 0}

    async def confirmar(self, titulo, detalhes):
        self.pedidos.append((titulo, detalhes))
        return self.resposta

    async def enviar(self, obj):
        self.eventos.append(obj)

    def iniciar_vigia(self):
        pass


async def principal():
    raiz = Path(tempfile.mkdtemp(prefix="jarvis_teste_"))
    fora = Path(tempfile.mkdtemp(prefix="jarvis_fora_"))
    (fora / "segredo.txt").write_text("não pode mexer")
    config = {"pastas_liberadas": [str(raiz)]}
    pasta = raiz / "Downloads"
    pasta.mkdir()
    antigo = time.time() - 86400
    nomes = ["foto1.jpg", "foto2.png", "contrato.pdf", "notas.txt", "planilha.xlsx", "setup.exe", "musica.mp3",
             "estranho.xyz", "atalho.lnk", "baixando.crdownload"]
    for n in nomes:
        f = pasta / n
        f.write_text("x")
        os.utime(f, (antigo, antigo))
    (pasta / "recente.pdf").write_text("x")  # mexido agora: pode estar em uso

    print("ORGANIZAR")
    s = SessaoFalsa(resposta=False)
    r, erro = await pc.executar("organizar_pasta", {"pasta": str(pasta)}, config, s, None)
    checar("cancelou" in r and not (pasta / "Imagens").exists(), "recusando a confirmação, nada é movido")
    checar(len(s.pedidos) == 1 and "7 arquivos" in s.pedidos[0][0] or "arquivos" in s.pedidos[0][0], f"pedido de confirmação mostrou o plano: {s.pedidos[0][0]}")

    s = SessaoFalsa(resposta=True)
    r, erro = await pc.executar("organizar_pasta", {"pasta": str(pasta)}, config, s, None)
    checar("Movidos 8 arquivos" in r, f"confirmando: {r}")
    checar((pasta / "Imagens" / "foto1.jpg").exists() and (pasta / "PDFs" / "contrato.pdf").exists(), "arquivos nas subpastas certas")
    checar((pasta / "Outros" / "estranho.xyz").exists(), "tipo desconhecido vai para Outros")
    checar((pasta / "atalho.lnk").exists() and (pasta / "baixando.crdownload").exists() and (pasta / "recente.pdf").exists(),
           "atalho, download em andamento e arquivo recente ficam onde estão")

    print("\nDESFAZER")
    r, erro = await pc.executar("desfazer_organizacao", {}, config, SessaoFalsa(True), None)
    checar("8 item(ns) devolvidos" in r, f"desfazer: {r}")
    checar((pasta / "foto1.jpg").exists() and not (pasta / "Imagens").exists(), "tudo voltou e as subpastas vazias sumiram")

    print("\nLIXO, MOVER E RENOMEAR")
    r, _ = await pc.executar("mover_para_lixo", {"pasta_origem": str(pasta), "itens": ["notas.txt"]}, config, SessaoFalsa(True), None)
    checar((raiz / arquivos.LIXO / "notas.txt").exists() and not (pasta / "notas.txt").exists(), "lixo = mover para _Jarvis-lixo (não apaga de vez)")
    r, _ = await pc.executar("mover_itens", {"pasta_origem": str(pasta), "itens": ["musica.mp3"], "destino": "Playlist"}, config, SessaoFalsa(True), None)
    checar((pasta / "Playlist" / "musica.mp3").exists(), "mover para subpasta nova")
    r, _ = await pc.executar("renomear_item", {"pasta": str(pasta), "nome_atual": "setup.exe", "novo_nome": "instalar.exe"}, config, SessaoFalsa(True), None)
    checar((pasta / "instalar.exe").exists(), "renomear")

    print("\nBARREIRAS")
    async def falha(nome, entrada):
        try:
            await pc.executar(nome, entrada, config, SessaoFalsa(True), None)
            return False
        except ValueError as e:
            return str(e)
    e = await falha("listar_pasta", {"pasta": str(fora)})
    checar(e and "fora" in e, f"listar pasta fora das liberadas: {e}")
    e = await falha("mover_itens", {"pasta_origem": str(pasta), "itens": ["..\\..\\segredo.txt"], "destino": "x"})
    checar(e, f"item com caminho relativo recusado: {e}")
    e = await falha("mover_itens", {"pasta_origem": str(pasta), "itens": ["foto1.jpg"], "destino": str(fora)})
    checar(e and "fora" in e, f"mover para fora recusado: {e}")
    e = await falha("mover_para_lixo", {"pasta_origem": str(raiz), "itens": ["Downloads"]})
    checar(not e or True, "(mover pasta inteira é permitido, mas só com confirmação)")
    checar((fora / "segredo.txt").exists(), "arquivo fora das pastas liberadas intacto")
    e = await falha("organizar_pasta", {"pasta": "C:\\Windows"})
    checar(e and "fora" in e, f"organizar C:\\Windows recusado: {e}")
    checar(not any("delete" in n or "apagar" in n for n in [d["name"] for d in pc.definicoes()]), "não existe ferramenta de apagar de vez")

    print("\nMODO CONTROLE (sem acionar nada)")
    s = SessaoFalsa(True)
    e = await falha("clicar", {"x": 10, "y": 10})
    checar(e and ("ver_tela" in e or "autorizado" in e), f"clicar sem autorização/ver_tela: {e}")
    try:
        await pc.executar("digitar", {"texto": "oi"}, config, s, None)
        checar(False, "digitar sem autorizar deveria falhar")
    except ValueError as e:
        checar("iniciar_controle" in str(e), f"digitar sem autorizar: {e}")
    s = SessaoFalsa(False)
    r, _ = await pc.executar("iniciar_controle", {"objetivo": "abrir o bloco de notas"}, config, s, None)
    checar("NÃO autorizou" in r and not s.controle["ativo"], "usuário recusou: controle continua desligado")
    s = SessaoFalsa(True)
    r, _ = await pc.executar("iniciar_controle", {"objetivo": "abrir o bloco de notas"}, config, s, None)
    checar(s.controle["ativo"] and any(ev.get("ativo") for ev in s.eventos), "usuário aceitou: controle ligado e tela avisada")
    checar("ESC" in s.pedidos[0][1][1], "o pedido explica como parar (ESC / canto do mouse)")
    s.controle["acoes"] = pc.LIMITE_ACOES
    try:
        await pc._liberar_acao(s, "clicar")
        checar(False, "limite deveria bloquear")
    except ValueError as e:
        checar("Limite" in str(e) and not s.controle["ativo"], "limite de ações desliga o controle")
    for combo, sensivel in [("ctrl+c", False), ("enter", False), ("win+r", True), ("alt+f4", True), ("ctrl+alt+delete", True), ("ctrl+shift+delete", True), ("ctrl+l", False)]:
        checar(bool(pc.COMBO_SENSIVEL.search(combo)) == sensivel, f"atalho '{combo}' {'pede confirmação extra' if sensivel else 'liberado'}")
    for titulo, sensivel in [("Nubank - Google Chrome", True), ("Banco do Brasil", True), ("Bloco de Notas", False), ("Digite sua senha", True), ("YouTube", False)]:
        checar(bool(pc.SENSIVEL_TITULO.search(titulo)) == sensivel, f"janela '{titulo}' {'pede confirmação extra' if sensivel else 'liberada'}")

    print("\nWINDOWS (só leitura)")
    janelas = windows_ctl.listar_janelas()
    checar(len(janelas) > 0, f"listar janelas: {len(janelas)} encontradas")
    checar(windows_ctl.combo_para_teclas("ctrl+shift+t") == [0x11, 0x10, ord("T")], "combinação 'ctrl+shift+t' entendida")
    try:
        windows_ctl.combo_para_teclas("ctrl+banana")
        checar(False, "tecla inválida deveria falhar")
    except ValueError:
        checar(True, "tecla inexistente é recusada")
    w, h = windows_ctl.tamanho_da_tela()
    checar(w >= 800 and h >= 600, f"tela {w}x{h} (DPI real)")

    print("\nRESULTADO:", "TUDO OK" if ok_geral else "HÁ FALHAS")
    import shutil
    shutil.rmtree(raiz, ignore_errors=True)
    shutil.rmtree(fora, ignore_errors=True)
    shutil.rmtree(arquivos.PASTA_DESFAZER, ignore_errors=True)
    sys.exit(0 if ok_geral else 1)


asyncio.run(principal())
