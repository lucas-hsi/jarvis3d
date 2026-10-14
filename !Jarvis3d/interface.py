"""
Controle da tela por voz: tema, painéis, layouts, estilo do reator e efeitos.
As ferramentas só mandam um comando à janela do Jarvis; quem aplica e guarda (localStorage) é o navegador,
então o visual escolhido continua depois de fechar e abrir de novo. Nada aqui toca em arquivos ou no sistema.
"""

TEMAS = ["ciano", "vermelho", "ambar", "verde", "roxo", "gelo", "rosa"]
PAINEIS = ["clima", "atalhos", "sistema", "rede", "processos", "nucleo", "fluxo", "memoria", "agenda", "atividade", "manchetes", "osciloscopio"]
PRESETS = ["completo", "moderno", "foco", "minimo", "cinema"]
ESTILOS_REATOR = ["classico", "esfera", "minimo"]
EFEITOS = ["glitch", "pulso", "varredura", "flash", "chuva_de_dados"]

ROTULOS = {n: "INTERFACE" for n in ("ui_tema", "ui_painel", "ui_layout", "ui_reator", "ui_efeito")}
NOMES = set(ROTULOS)


def _def(nome, descricao, props, req):
    return {"name": nome, "description": descricao, "input_schema": {"type": "object", "properties": props, "required": req}}


def definicoes() -> list[dict]:
    return [
        _def("ui_tema", "Muda a cor de toda a tela do Jarvis.", {"tema": {"type": "string", "enum": TEMAS}}, ["tema"]),
        _def("ui_painel", "Mostra, esconde ou alterna um painel da tela. 'todos' vale para todos os painéis.",
             {"painel": {"type": "string", "enum": PAINEIS + ["todos"]}, "acao": {"type": "string", "enum": ["mostrar", "esconder", "alternar"]}},
             ["painel", "acao"]),
        _def("ui_layout", "Layouts da tela. preset: completo (tudo), foco (só o reator e a legenda), minimo (sistema e memória), cinema (só o reator). "
                          "salvar/carregar guardam e restauram o arranjo atual com um nome ('modo trabalho').",
             {"acao": {"type": "string", "enum": ["preset", "salvar", "carregar"]},
              "nome": {"type": "string", "description": "Nome do preset (completo, foco, minimo, cinema) ou nome do layout salvo."}},
             ["acao", "nome"]),
        _def("ui_reator", "Muda o estilo e o brilho do reator central. Estilos: classico, esfera (esfera de partículas girando), minimo.",
             {"estilo": {"type": "string", "enum": ESTILOS_REATOR}, "brilho": {"type": "number", "description": "0.5 (suave) a 1.5 (intenso). Padrão 1."}}, []),
        _def("ui_efeito", "Dispara um efeito visual rápido na tela (só visual).", {"nome": {"type": "string", "enum": EFEITOS}}, ["nome"]),
    ]


def _escolha(entrada: dict, campo: str, validos: list[str]) -> str:
    v = str(entrada.get(campo) or "").strip().lower()
    if v not in validos:
        raise ValueError(f"'{campo}' deve ser um destes: {', '.join(validos)}.")
    return v


async def executar(nome: str, entrada: dict, sessao) -> str:
    if nome == "ui_tema":
        comando = {"tema": _escolha(entrada, "tema", TEMAS)}
    elif nome == "ui_painel":
        comando = {"painel": _escolha(entrada, "painel", PAINEIS + ["todos"]), "acao": _escolha(entrada, "acao", ["mostrar", "esconder", "alternar"])}
    elif nome == "ui_layout":
        acao = _escolha(entrada, "acao", ["preset", "salvar", "carregar"])
        nome_layout = str(entrada.get("nome") or "").strip().lower()[:40]
        if not nome_layout:
            raise ValueError("Faltou o nome do layout.")
        if acao == "preset" and nome_layout not in PRESETS:
            raise ValueError(f"Preset deve ser um destes: {', '.join(PRESETS)}.")
        comando = {"acao": acao, "nome": nome_layout}
    elif nome == "ui_reator":
        comando = {}
        if entrada.get("estilo"):
            comando["estilo"] = _escolha(entrada, "estilo", ESTILOS_REATOR)
        if entrada.get("brilho") is not None:
            try:
                comando["brilho"] = max(0.5, min(1.5, float(entrada["brilho"])))
            except (TypeError, ValueError):
                raise ValueError("'brilho' deve ser um número entre 0,5 e 1,5.")
        if not comando:
            raise ValueError("Informe o estilo ou o brilho.")
    elif nome == "ui_efeito":
        comando = {"nome": _escolha(entrada, "nome", EFEITOS)}
    else:
        raise ValueError(f"Ferramenta desconhecida: {nome}")
    await sessao.enviar({"tipo": "ui", "comando": nome, **comando})
    return "Feito."
