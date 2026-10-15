"""Fim de fala pelo TEXTO: frase completa é entregue mais cedo; frase cortada no meio (ou só "Jarvis") espera a continuação e junta; sem continuação, entrega depois."""
import asyncio
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
import stt  # noqa: E402

ok = True
rng = np.random.default_rng(3)


def checar(c, t):
    global ok
    ok &= bool(c)
    print("  [%s] %s" % ("OK" if c else "FALHOU", t))


def ruido(s):
    return (rng.standard_normal(int(s * 16000)) * 10 ** (-66 / 20)).astype(np.float32)


def voz(s, f0=120.0):                                   # harmônicos + modulação silábica: parece voz para o detector (não é ruído plano)
    t = np.arange(int(s * 16000)) / 16000
    x = sum(np.sin(2 * np.pi * f0 * h * t + h) / h for h in range(1, 22))
    x = x * (0.55 + 0.45 * np.sin(2 * np.pi * 4.0 * t)) ** 2
    return (x / np.sqrt(np.mean(x ** 2)) * 10 ** (-24 / 20)).astype(np.float32)


class Falso:
    """Transcritor de mentira: o texto depende da DURAÇÃO do áudio (roteiro por faixas)."""
    pronto = True

    def __init__(self, roteiro):
        self.roteiro = roteiro                           # [(duração máxima em s, texto)]

    def transcrever(self, x):
        d = len(x) / 16000
        for limite, texto in self.roteiro:
            if d <= limite:
                return texto, 0.9, ""
        return self.roteiro[-1][1], 0.9, ""


async def rodar(roteiro, trechos, continuacao=0.4):
    """trechos: lista de áudios (voz e pausas) alimentados em tempo simulado; devolve (textos entregues, quadros até a 1ª entrega depois do fim da voz)."""
    msgs = []

    async def emitir(m):
        msgs.append(m)
    s = stt.SessaoSTT(Falso(roteiro), emitir)
    s.continuacao_s = continuacao
    s.ligar(True)
    x = np.concatenate([ruido(1.0)] + trechos + [ruido(2.5)])
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    fim_voz = None
    t_voz = len(np.concatenate([ruido(1.0)] + trechos)) // 320                # quadro em que a última voz/pausa termina
    entrega = None
    for i in range(0, len(pcm), 640):
        await s.alimentar(pcm[i:i + 640])
        await asyncio.sleep(0)
        if entrega is None and any(m["tipo"] == "transcricao" for m in msgs):
            entrega = i // 640
        if i // 640 > t_voz and continuacao > 0 and False:
            pass
        await asyncio.sleep(0.004)                       # dá chance às tarefas de fundo (a transcrição falsa é imediata)
    await asyncio.sleep(continuacao + 0.5)
    textos = [m["texto"] for m in msgs if m["tipo"] == "transcricao"]
    return textos, entrega, t_voz


async def principal():
    print("1) frase COMPLETA: entrega antes de esperar todo o silêncio")
    textos, entrega, t_voz = await rodar([(9, "Jarvis, abre o Chrome.")], [voz(1.6)])
    fim_voz_quadro = (16000 + int(1.6 * 16000)) // 320
    atraso = (entrega - fim_voz_quadro) * 20 if entrega is not None else None
    checar(textos == ["Jarvis, abre o Chrome."], f"entregou uma vez: {textos}")
    checar(atraso is not None and atraso < 420, f"entregue {atraso} ms depois do fim da voz (o normal seria ~480 ms + transcrição)")

    print("2) frase CORTADA no meio + continuação: junta")
    textos, *_ = await rodar([(2.3, "Jarvis, abre o"), (9, "Jarvis, abre o Chrome.")], [voz(1.4), ruido(0.7), voz(1.2)], continuacao=1.1)
    checar(textos == ["Jarvis, abre o Chrome."], f"uma só fala, juntada: {textos}")

    print("3) só 'Jarvis.' e a ordem vem depois de uma pausa: junta")
    textos, *_ = await rodar([(1.8, "Jarvis."), (9, "Jarvis, que horas são?")], [voz(0.8), ruido(0.8), voz(1.4)], continuacao=1.3)
    checar(textos == ["Jarvis, que horas são?"], f"{textos}")

    print("4) cortada no meio e NINGUÉM continua: entrega depois da espera")
    textos, *_ = await rodar([(9, "Jarvis, abre o")], [voz(1.4)], continuacao=0.5)
    checar(textos == ["Jarvis, abre o"], f"entregou o que tinha: {textos}")

    print("5) pergunta completa com '?' também sai cedo; vírgula no fim espera")
    checar(stt.texto_completo("Que horas são?") and not stt.texto_incompleto("Que horas são?"), "'Que horas são?' é completa")
    checar(stt.texto_incompleto("Jarvis, abre o chrome e") and stt.texto_incompleto("Então,") and stt.texto_incompleto("Jarvis."), "'... e', 'Então,' e só 'Jarvis.' são incompletas")
    checar(not stt.texto_incompleto("Abre a calculadora.") and not stt.texto_incompleto("Toca Back in Black"), "frases normais não são incompletas")


asyncio.run(principal())
print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
sys.exit(0 if ok else 1)
