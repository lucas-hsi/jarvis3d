"""Atalhos de intenção: frases curtas viram ação direta; qualquer coisa ambígua ou composta NÃO pode virar atalho (vai para o modelo)."""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
import intencoes  # noqa: E402

APPS = {"calculadora": "Calculadora", "bloco de notas": "Bloco de Notas", "chrome": "chrome", "spotify": "spotify", "paint": "Paint", "excel": "Excel", "configuracoes": "Configurações"}
achar = lambda n: APPS.get(intencoes.normalizar(n))  # noqa: E731
ok = True


def esperar(frase, acao=None, valor=None):
    global ok
    r = intencoes.interpretar(frase, achar)
    bom = (r is None) if acao is None else (r is not None and r["acao"] == acao and (valor is None or valor in (r.get("valor"), r.get("programa"), r.get("n"), (r.get("entrada") or {}).get("tema"), (r.get("entrada") or {}).get("nome"), (r.get("entrada") or {}).get("painel"))))
    ok &= bool(bom)
    print("  [%s] %-52s -> %s" % ("OK" if bom else "FALHOU", frase, None if r is None else {k: v for k, v in r.items() if k != "fala"}))


print("ATALHOS (devem ser resolvidos na hora)")
for f, a, v in [
    ("Abre a calculadora", "abrir", "Calculadora"), ("Jarvis, abre o bloco de notas por favor", "abrir", "Bloco de Notas"), ("abrir o chrome", "abrir", "chrome"),
    ("abre o paint", "abrir", "Paint"), ("abre as configurações", "abrir", "Configurações"),
    ("pula essa música", "midia", "proxima"), ("próxima música", "midia", "proxima"), ("pula", "midia", "proxima"), ("volta a música", "midia", "anterior"),
    ("música anterior", "midia", "anterior"), ("pausa a música", "midia", "play_pause"), ("continua a música", "midia", "play_pause"), ("pausa", "midia", "play_pause"),
    ("volume 40", "volume", 40), ("coloca o volume em 70%", "volume", 70), ("aumenta o volume", "volume", "subir"), ("abaixa o som", "volume", "descer"),
    ("coloca no mudo", "volume", "mudo"), ("muta o som", "volume", "mudo"), ("diminui o volume", "volume", "descer"),
    ("muda o tema para vermelho", "ui", "vermelho"), ("coloca o tema roxo", "ui", "roxo"), ("modo foco", "ui", "foco"), ("esconde os painéis", "ui", "foco"),
    ("mostra tudo", "ui", "todos"), ("mostra as barras laterais", "ui", "moderno"), ("modo completo", "ui", "completo"), ("modo cinema", "ui", "cinema"), ("que horas são?", "hora", None), ("que horas são agora", "hora", None),
]:
    esperar(f, a, v)

print("NÃO podem virar atalho (vão para o modelo)")
for f in [
    "abre a calculadora e soma 2 mais 2", "abre o youtube", "abre o site do google", "abre a pasta downloads", "abre o programa que eu uso para editar vídeo",
    "abre o xyzprograma", "toca Back in Black", "pausa o jogo que está rodando na tela", "qual é a capital da França", "muda o tema da tela para uma cor mais bonita",
    "abre a calculadora depois pesquisa o dólar", "me explica como funciona o volume de um som", "abre a câmera", "abre a webcam", "manda um e-mail para a Ana",
    "pula essa parte da explicação e me diz o resumo do projeto inteiro", "coloca o volume da reunião no máximo e abre o chrome", "tchau",
]:
    esperar(f)

print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
sys.exit(0 if ok else 1)
