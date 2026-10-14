"""
Teste do roteador de ferramentas (sem rede, sem servidor): garante que o assunto liga os grupos certos, que a
saudação vai enxuta, que a ordem das ferramentas é estável (cache de prompt) e que nada some por engano.

Uso:  .venv\\Scripts\\python.exe scripts\\teste_roteador.py
"""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import camera  # noqa: E402
import briefing  # noqa: E402
import cerebro  # noqa: E402
import direcao  # noqa: E402
import ferramentas  # noqa: E402
import google_tools  # noqa: E402
import interface  # noqa: E402
import navegador  # noqa: E402
import roteador  # noqa: E402

ok = True


def checar(cond, texto):
    global ok
    ok &= bool(cond)
    print("  [%s] %s" % ("OK" if cond else "FALHOU", texto))


TODAS = (ferramentas.definicoes({"chrome": "chrome"}, True) + cerebro.definicoes(True) + [camera.definicao(), direcao.definicao()]
         + navegador.definicoes() + interface.definicoes() + google_tools.definicoes(True)
         + [{"name": "trilha_sonora"}, {"name": "encerrar_conversa"}, {"name": "dormir"}, briefing.DEFINICAO, roteador.FERRAMENTA_HABILITAR])
NOMES = {t["name"] for t in TODAS}


def grupos(texto, ativacao=False, mem=None, extras=None, **estado):
    return roteador.escolher(texto, ativacao, {} if mem is None else mem, set() if extras is None else extras, estado)


print("1) NENHUMA ferramenta fica órfã (todas têm grupo e as conhecidas estão no lugar certo)")
por_grupo = {}
for n in NOMES:
    por_grupo.setdefault(roteador.grupo_de(n), set()).add(n)
checar(set(por_grupo) <= set(roteador.GRUPOS_ORDEM), f"grupos usados: {sorted(por_grupo)}")
checar({"youtube_buscar", "video_controle", "navegador_ver"} <= por_grupo["navegador"], "YouTube e navegador no grupo navegador")
checar({"email_enviar", "agenda_criar", "drive_listar", "google_status"} <= por_grupo["google"], "Google no grupo google")
checar({"clicar", "iniciar_controle", "listar_janelas"} <= por_grupo["pc"], "controle do PC no grupo pc")
checar({"ui_tema", "ui_reator"} <= por_grupo["interface"], "visual no grupo interface")
checar({"ver_camera", "modo_gravacao"} == por_grupo["camera"], "câmera e gravação no grupo camera")
checar({"consultar_cofre", "lembrar", "pesquisar_web", "dormir", "habilitar_ferramentas"} <= por_grupo["nucleo"], "núcleo tem cofre, memória, web, dormir e o escape")
checar("briefing" in por_grupo["nucleo"], "briefing está no núcleo (sempre disponível)")

print("\n2) A SAUDAÇÃO das palmas vai só com o núcleo")
g = grupos("(palmas)", ativacao=True)
checar(g == {"nucleo"}, f"grupos: {g}")
n_saudacao = len(roteador.filtrar(TODAS, g))
checar(n_saudacao < 25, f"{n_saudacao} ferramentas de {len(TODAS)} (antes eram todas)")

print("\n3) O ASSUNTO liga o grupo certo")
casos = [
    ("toca Back in Black no YouTube", "navegador"),
    ("pula essa música", "navegador"),
    ("o que eu tenho na agenda amanhã?", "google"),
    ("manda um e-mail para a Ana", "google"),
    ("organiza a pasta de downloads", "arquivos"),
    ("minimiza a janela do Chrome", "pc"),
    ("clica no botão salvar", "pc"),
    ("o que você acha da minha roupa?", "camera"),
    ("vou gravar um vídeo", "camera"),
    ("muda o tema para vermelho", "interface"),
    ("abre o site do mercado livre", "navegador"),
]
for texto, esperado in casos:
    g = grupos(texto)
    checar(esperado in g, f"'{texto}' → {esperado}  (grupos: {sorted(g)})")
g = grupos("qual a capital da França?")
checar(g == {"nucleo"}, f"pergunta simples fica só no núcleo: {sorted(g)}")

print("\n4) PEGAJOSO: 'mais alto' logo depois de tocar música ainda acha as ferramentas")
mem = {}
grupos("toca uma música do Queen", mem=mem)
g2 = grupos("mais alto", mem=mem)
checar("navegador" in g2, f"segundo turno sem a palavra-chave: {sorted(g2)}")
for _ in range(roteador.TURNOS_PEGAJOSO + 1):
    g3 = grupos("e quanto é 2 mais 2?", mem=mem)
checar("navegador" not in g3, "depois de alguns turnos de outro assunto o grupo sai (não incha o prompt para sempre)")
checar("navegador" in grupos("pausa aí", midia=True), "com mídia tocando, o navegador entra mesmo sem palavra-chave")
checar("pc" in grupos("continua", controle=True) and "camera" in grupos("continua", gravando=True), "controle ativo e gravação ligada mantêm seus grupos")

print("\n5) ESCAPE: o modelo liga o que faltou")
extras = set()
msg = roteador.habilitar({"grupos": ["google"]}, extras, TODAS)
checar("google" in extras and "email_enviar" in msg, f"habilitar google → {msg[:90]}...")
checar("agenda_listar" in {t["name"] for t in roteador.filtrar(TODAS, grupos("oi", extras=extras))}, "o grupo ligado entra na rodada seguinte")
checar("Informe grupos" in roteador.habilitar({"grupos": ["nada"]}, set(), TODAS), "grupo inventado é recusado com mensagem útil")

print("\n6) ORDEM ESTÁVEL (o cache de prompt só acerta se o prefixo for idêntico)")
a = [t["name"] for t in roteador.filtrar(TODAS, {"nucleo", "navegador", "google"})]
b = [t["name"] for t in roteador.filtrar(list(reversed(TODAS)) and TODAS, {"google", "navegador", "nucleo"})]
checar(a == b, "mesmos grupos, mesma ordem")
ordem = [roteador.GRUPOS_ORDEM.index(roteador.grupo_de(n)) for n in a]
checar(ordem == sorted(ordem), "agrupadas pela ordem fixa dos grupos")
checar(len(a) == len(set(a)), "sem ferramenta repetida")

print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
sys.exit(0 if ok else 1)
