"""Teste de integração com a API do Google Gemini (custo zero).
Testa: streaming, chamada de ferramenta, ciclo de ferramentas e aprendizado de memórias.
"""

import asyncio
import os
import sys
import pathlib

BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")

import server
import gemini_adaptador
import memoria
import cerebro

ok = True


def checar(condicao: bool, desc: str):
    global ok
    if condicao:
        print(f"  [OK] {desc}")
    else:
        print(f"  [FALHOU] {desc}")
        ok = False


async def principal():
    global ok
    print("=== TESTE GOOGLE GEMINI (CUSTO ZERO) ===")
    
    checar(server.PROVEDOR == "gemini", f"provedor ativo é 'gemini' (atual: {server.PROVEDOR})")
    checar(server.MODELO == "gemini-3.5-flash-lite", f"modelo padrão é 'gemini-3.5-flash-lite' (atual: {server.MODELO})")
    checar(isinstance(server.ai, gemini_adaptador.AsyncGeminiClient), "cliente ai é AsyncGeminiClient")
    checar(server.ai_reserva is not None, "reserva (DeepSeek/Anthropic) está configurada")

    print("\n1) Streaming e tempo de resposta")
    msgs = [{"role": "user", "content": "Diga apenas: 'Jarvis online com Gemini'."}]
    pedacos = []
    t0 = asyncio.get_event_loop().time()
    async with server.ai.messages.stream(model=server.MODELO, max_tokens=100, messages=msgs) as s:
        async for p in s.text_stream:
            pedacos.append(p)
        resp = await s.get_final_message()
    dt = round((asyncio.get_event_loop().time() - t0) * 1000)
    texto = "".join(pedacos).strip()
    checar("jarvis" in texto.lower() or "gemini" in texto.lower() or len(texto) > 0, f"respondeu em {dt} ms: '{texto[:60]}'")

    print("\n2) Chamada de ferramenta (tool use)")
    ferr = [{
        "name": "abrir_programa",
        "description": "Abre um programa no Windows",
        "input_schema": {"type": "object", "properties": {"programa": {"type": "string"}}, "required": ["programa"]}
    }]
    msgs = [{"role": "user", "content": "Abre a calculadora para mim"}]
    async with server.ai.messages.stream(model=server.MODELO, max_tokens=200, tools=ferr, messages=msgs) as s:
        async for _ in s.text_stream:
            pass
        resp = await s.get_final_message()

    usos = [b for b in resp.content if b.type == "tool_use"]
    checar(len(usos) > 0 and usos[0].name == "abrir_programa", f"disparou tool_use: {usos[0].name if usos else None}")
    if usos:
        checar("calc" in str(usos[0].input).lower(), f"argumento correto da ferramenta: {usos[0].input}")
        checar(bool(usos[0].thought_signature), "thought_signature preservada no bloco de ferramenta")

    print("\n3) Segundo turno com retorno da ferramenta")
    if usos:
        msgs_segundo = [
            {"role": "user", "content": "Abre a calculadora para mim"},
            {"role": "assistant", "content": resp.content},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": usos[0].id, "content": "calculadora aberta."}]}
        ]
        pedacos_2 = []
        async with server.ai.messages.stream(model=server.MODELO, max_tokens=150, tools=ferr, messages=msgs_segundo) as s:
            async for p in s.text_stream:
                pedacos_2.append(p)
            resp_2 = await s.get_final_message()
        texto_2 = "".join(pedacos_2).strip()
        checar(len(texto_2) > 0, f"concluiu turno após ferramenta: '{texto_2[:70]}'")

    print("\n4) Aprendizado de memória (cerebro.aprender)")
    mem_temp = memoria.Memoria()
    mudou = await cerebro.aprender(server.ai, server.MODELO, mem_temp, "Lucas", "Eu amo programar em Python no meu tempo livre.", "Que legal, Lucas! Vou me lembrar disso.")
    checar(isinstance(mudou, list), f"aprendizado assíncrono executou sem erros (resultado: {len(mudou)} memória(s))")

    if ok:
        print("\nRESULTADO: TODOS OS TESTES DO GEMINI PASSARAM COM SUCESSO!")
    else:
        print("\nRESULTADO: ALGUNS TESTES FALHARAM!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(principal())
