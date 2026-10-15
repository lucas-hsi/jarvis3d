"""
Testa o DeepSeek de VERDADE (centavos) pelo endpoint compatível com a Anthropic: texto em streaming, ferramenta, imagem, imagem dentro de tool_result,
esforço, modelo maior (pensar_fundo) e o 1º texto. Uso:  .venv\\Scripts\\python.exe -X utf8 scripts\\teste_deepseek.py
"""

import asyncio
import base64
import io
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
os.environ["JARVIS_MEMORIA_DIR"] = tempfile.mkdtemp(prefix="jarvis_ds_")
os.environ["JARVIS_SEM_VOZ"] = "1"
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
import server  # noqa: E402

ok = True


def checar(c, t):
    global ok
    ok &= bool(c)
    print("  [%s] %s" % ("OK" if c else "FALHOU", t))


FERR = [{"name": "abrir_programa", "description": "Abre um programa do computador.", "input_schema": {"type": "object", "properties": {"programa": {"type": "string"}}, "required": ["programa"]}}]


def imagem_teste() -> dict:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (480, 200), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, 460, 180], outline="blue", width=4)
    d.text((60, 80), "FATURA 4821 - TOTAL R$ 350,00", fill="black")
    b = io.BytesIO(); im.save(b, "JPEG")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(b.getvalue()).decode()}}


async def principal():
    print(f"provedor {server.PROVEDOR} | modelo {server.MODELO} | profundo {server.MODELO_PROFUNDO} | reserva {'sim' if server.ai_reserva else 'não'}")
    if server.PROVEDOR != "deepseek":
        sys.exit("O provedor não é o DeepSeek (falta DEEPSEEK_API_KEY ou provedor no config).")
    ai, M = server.ai, server.MODELO

    print("1) texto em streaming + esforço")
    t0 = time.perf_counter(); primeiro = None; texto = ""
    async with ai.messages.stream(model=M, max_tokens=200, system="Responda em português, curto.", messages=[{"role": "user", "content": "Qual a capital da França?"}], output_config={"effort": "low"}) as s:
        async for p in s.text_stream:
            if primeiro is None: primeiro = (time.perf_counter() - t0) * 1000
            texto += p
        fim = await s.get_final_message()
    checar("paris" in texto.lower(), f"respondeu '{texto.strip()[:60]}' (1º texto {primeiro:.0f} ms)")

    print("2) ferramenta (tool_use)")
    r = await ai.messages.create(model=M, max_tokens=300, tools=FERR, messages=[{"role": "user", "content": "Abre a calculadora"}])
    usos = [b for b in r.content if b.type == "tool_use"]
    checar(usos and usos[0].name == "abrir_programa" and "calc" in str(usos[0].input).lower(), f"chamou {usos[0].name if usos else None} {usos[0].input if usos else ''}")
    msgs = [{"role": "user", "content": "Abre a calculadora"}, {"role": "assistant", "content": r.content},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": usos[0].id, "content": "calculadora aberto (janela 'Calculadora')."}]}]
    r2 = await ai.messages.create(model=M, max_tokens=200, tools=FERR, messages=msgs)
    checar(any(b.type == "text" and b.text.strip() for b in r2.content), f"depois do resultado fala: '{''.join(b.text for b in r2.content if b.type == 'text')[:70]}'")

    print("3) imagem")
    r = await ai.messages.create(model=M, max_tokens=200, messages=[{"role": "user", "content": [imagem_teste(), {"type": "text", "text": "Qual o total da fatura na imagem? Responda só o valor."}]}])
    t = "".join(b.text for b in r.content if b.type == "text")
    checar("350" in t, f"leu a imagem: '{t.strip()[:60]}'")

    print("4) imagem DENTRO de tool_result (como o ver_tela devolve)")
    msgs = [{"role": "user", "content": "Olha a tela e me diz o total."}, {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_1", "name": "ver_tela", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": [imagem_teste(), {"type": "text", "text": "Print da tela."}]}]}]
    try:
        r = await ai.messages.create(model=M, max_tokens=200, tools=[{"name": "ver_tela", "description": "print da tela", "input_schema": {"type": "object", "properties": {}}}], messages=msgs)
        t = "".join(b.text for b in r.content if b.type == "text")
        checar("350" in t, f"leu a imagem no tool_result: '{t.strip()[:60]}'")
    except Exception as e:
        checar(False, f"imagem em tool_result falhou: {type(e).__name__}: {str(e)[:120]}")

    print("5) modelo maior (pensar_fundo)")
    t0 = time.perf_counter()
    try:
        t = await server.pensar_fundo({"pergunta": "Um sistema tem 3 serviços com 99,9% de disponibilidade cada, em série. Qual a disponibilidade total e o que fazer para melhorar?"})
        checar("99,7" in t or "99.7" in t or "99,70" in t, f"{(time.perf_counter() - t0):.1f} s: '{t.strip()[:90]}'")
    except Exception as e:
        checar(False, f"pensar_fundo falhou: {e}")

    print("6) 1º texto (5 chamadas)")
    ms = []
    for _ in range(5):
        t0 = time.perf_counter()
        async with ai.messages.stream(model=M, max_tokens=60, system=server.REGRAS[:6000], tools=FERR, messages=[{"role": "user", "content": "Que horas são?"}]) as s:
            async for p in s.text_stream:
                ms.append((time.perf_counter() - t0) * 1000); break
            await s.get_final_message()
    print(f"     1º texto: mediana {statistics.median(ms):.0f} ms, máx {max(ms):.0f} ms")
    print("\nRESULTADO:", "TUDO OK" if ok else "HÁ FALHAS")
    sys.exit(0 if ok else 1)


asyncio.run(principal())
