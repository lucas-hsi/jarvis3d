"""
Escolhe quais ferramentas entram em CADA chamada ao modelo.

Por quê: eram 74 ferramentas (~10 mil tokens) em toda fala, até na saudação das palmas. Menos tokens de entrada
= primeiro token mais cedo e menos custo. As ferramentas ficam em grupos; o NÚCLEO vai sempre, o resto só quando
o assunto pede (palavras da fala, o que está em uso na sessão, ou o próprio modelo pedindo via `habilitar_ferramentas`).

Princípio de segurança do roteamento: errar para MAIS é barato (só tokens), errar para MENOS é caro (o modelo
diria que não consegue). Por isso os gatilhos são largos e há a ferramenta de escape `habilitar_ferramentas`.
A ORDEM das ferramentas é estável (necessária para o cache de prompt acertar o prefixo).
"""

import re
import unicodedata

GRUPOS_ORDEM = ("nucleo", "pesquisa", "cofre", "rotinas", "arquivos", "pc", "navegador", "google", "camera", "interface", "mcp")

# NÚCLEO enxuto (2026-10-26): só o que uma conversa comum precisa. Eram 29 ferramentas (~4,4 mil tokens) em TODA chamada.
NUCLEO = {
    "abrir_programa", "controlar_volume", "controlar_midia", "lembrar", "buscar_memoria", "esquecer_memoria",
    "encerrar_conversa", "dormir", "habilitar_ferramentas", "briefing",
}
PESQUISA = {"pesquisar_web", "ler_pagina", "abrir_site", "noticias", "pesquisa_profunda", "pensar_fundo", "modo_especialista"}
COFRE = {"consultar_cofre", "ler_nota", "anotar_no_cofre", "acrescentar_no_cofre"}
ROTINAS = {"lembrete_voz", "vigiar_cotacao", "rotina_salvar", "rotina_executar", "proativo_gerenciar", "mostrar_clima", "trilha_sonora"}
ARQUIVOS = {"listar_pasta", "organizar_pasta", "mover_itens", "renomear_item", "criar_pasta", "mover_para_lixo",
            "desfazer_organizacao", "abrir_pasta", "ler_documento", "criar_documento", "buscar_documentos"}
PC = {"listar_janelas", "gerenciar_janela", "mostrar_area_de_trabalho", "bloquear_tela", "iniciar_controle", "clicar",
      "digitar", "pressionar_teclas", "rolar", "janela_ver", "janela_acao", "terminal_executar", "ver_tela",
      "oficina_escrever", "oficina_rodar", "oficina_ler", "oficina_listar", "oficina_abrir"}
CAMERA = {"ver_camera", "modo_gravacao"}
NAVEGADOR_EXTRA = {"youtube_buscar", "video_controle"}

DESCRICAO_GRUPOS = {
    "pesquisa": "pesquisar na web, ler páginas, notícias, pesquisa profunda, abrir um site, pensar a fundo (modelo maior) e modos especialistas",
    "cofre": "ler, buscar e anotar no cofre do Obsidian (notas, ideias, projetos)",
    "rotinas": "lembretes por voz, alertas de cotação, rotinas, clima, trilha sonora e o que o Jarvis faz sozinho",
    "arquivos": "listar, organizar, mover, renomear e mandar para o lixo arquivos e pastas (Downloads, Documentos, Área de Trabalho)",
    "pc": "ver a tela, janelas do Windows, clicar/digitar em programas (janela_ver/janela_acao), mouse, teclado, bloquear a tela, terminal PowerShell visível e a OFICINA (criar/rodar arquivos, scripts e pequenos programas)",
    "navegador": "YouTube e música, controle de vídeo, abrir e operar sites no navegador do Jarvis",
    "google": "Google Agenda, Gmail e Drive",
    "camera": "webcam (olhar roupa/objetos) e modo gravação de vídeo",
    "interface": "visual da tela do Jarvis (tema, painéis, layout, reator, efeitos)",
    "mcp": "ferramentas externas do usuário (servidores MCP: Notion, GitHub, arquivos, bancos, casa inteligente...)",
}


def grupo_de(nome: str) -> str:
    if nome in NUCLEO:
        return "nucleo"
    for grupo, nomes in (("pesquisa", PESQUISA), ("cofre", COFRE), ("rotinas", ROTINAS), ("arquivos", ARQUIVOS), ("pc", PC), ("camera", CAMERA)):
        if nome in nomes:
            return grupo
    if nome in NAVEGADOR_EXTRA or nome.startswith("navegador_"):
        return "navegador"
    if nome.startswith(("agenda_", "email_", "drive_", "google_")):
        return "google"
    if nome.startswith("ui_"):
        return "interface"
    if nome.startswith("mcp__"):
        return "mcp"
    return "nucleo"          # ferramenta nova sem grupo: vai sempre (seguro)


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


# Gatilhos (sobre o texto sem acento e em minúsculas). Apertados em 2026-10-26: palavras comuns como "abre", "tela", "programa", "sistema",
# "criar", "lembra", "google", "contrato" ligavam grupos inteiros à toa. Se faltar algo, o modelo chama `habilitar_ferramentas`.
GATILHOS = {
    "pesquisa": re.compile(r"pesquis|notici|manchete|internet|\bweb\b|\bsite\b|pagina|\blink\b|http|\.com|\bbusca|procura|cotacao|\bpreco|quanto custa|"
                           r"ultim[ao]s?\b|atualmente|analis|compar[ae]|vale a pena|estrateg|plano de|pros e contras|aprofund|especialista|"
                           r"modo (financas|saude|codigo|redacao|estudo|negocios|juridico)|pensa (bem|fundo)|raciocin"),
    "cofre": re.compile(r"\bcofre\b|obsidian|(?<!bloco de )\bnotas?\b|anot|pendenc|o que (eu )?(salvei|decidi|escrevi)|\bvault\b|diario|\bideias?\b|aprendizado|registr[ae]|guarda isso|salva isso|"
                        r"meus? projetos?|\bprojeto\b|decisao|decisoes"),
    "rotinas": re.compile(r"\bme lembr|\blembretes?\b|daqui a|em \d+ (min|hora)|\bavis[ae]|dolar|bitcoin|cotacao|\brotina|modo trabalho|"
                          r"resumo do dia|clima|previsao|temperatura|chover|\bchuva|trilha|musica de acao|adrenalina|proativ"),
    "arquivos": re.compile(r"\bpastas?\b|arquivos?\b|download|organiz|renome|lixeira|\bmov[ae]\b|\bmova\b|desfaz.*organiz|\bpdf|planilha|\bexcel\b|"
                           r"\bdocx?\b|\bxlsx\b|\bword\b|documentos?\b|area de trabalho|onde (esta|ficou) (o|a|meu|minha)"),
    "pc": re.compile(r"janela|minimiz|maximiz|\bfech(a|ar|e) (a|o|essa|esse)|\bclic|digit(a|e|ar)\b|\btecla|atalho|mouse|\brol(e|ar)\b|"
                     r"area de trabalho|bloque(ia|ar)|trav(a|ar) a tela|\bbotao|terminal|comando|powershell|power ?xel|\bcmd\b|\bpip\b|\bnpm\b|\bgit\b|"
                     r"executa|roda (o|a|esse|esse)|instal(a|e|ar)\b|script|escript|python|paiton|codigo|programinha|oficina|automatiz|desenvolv|"
                     r"\bcri(a|e|ar) (um|uma|o|a) (script|programa|app|aplicativo|site|bot|codigo|arquivo|pagina|ferramenta|calculadora)|"
                     r"\.py\b|html|\btela\b|\bprint\b|\bve (a|o|isso)\b|olha (a|o|isso|minha)|le (a|o) (tela|que)|na minha tela|painel de controle"),
    "navegador": re.compile(r"youtube|music|\bsom\b|toc[ae]\b|toque|video|\bpul[ae]|proxim|anterior|pausa|continu|anunci|"
                            r"navegador|\baba\b|\blogin\b|entra no|preench|playlist|letra d|\bclip|mercado livre|olx|amazon|instagram|facebook|"
                            r"linkedin|compr(a|ar|e) |\bsite\b|\bwww|http|\.com"),
    "google": re.compile(r"agenda|e-?mail|gmail|\bdrive\b|compromisso|reuniao|calendario|rascunho|caixa de entrada|convite|marcar (uma |a )?(reuniao|consulta|compromisso)|"
                         r"\bevento|nao lid|remetente|anexo"),
    "camera": re.compile(r"camera|webcam|\bfoto\b|me ve\b|olha pra mim|olhe pra mim|roupa|grav(a|ar|acao)|film(a|ar)|vestid|outfit|enquadr|iluminac"),
    "interface": re.compile(r"\btema\b|\bpainel\b|paineis|\blayout\b|reator|\bcores?\b|efeito|interface|esfera|modo foco|brilho|animac|"
                            r"(muda|troca|coloca|deixa|pinta).*(vermelh|azul|verde|ambar|roxo|laranja)|esconde (o|os) |mostra (o|os) (painel|paineis)"),
}

TURNOS_PEGAJOSO = 3        # um grupo usado/ativado continua disponível nos turnos seguintes ("pula essa", "mais alto")


def escolher(texto: str, ativacao: bool, memoria_sessao: dict, extras: set, estado: dict) -> set:
    """Grupos para este turno. `memoria_sessao` = {grupo: turnos restantes} (mutado); `extras` = habilitados pelo modelo."""
    ativos = set()                           # grupos que ESTE turno pede de verdade (só estes renovam o "pegajoso")
    if not ativacao:
        t = _norm(texto)
        for g, rx in GATILHOS.items():
            if rx.search(t):
                ativos.add(g)
        if estado.get("midia"):
            ativos.add("navegador")          # tem som tocando: "pausa", "mais baixo", "próxima" sem dizer nada específico
        if estado.get("controle"):
            ativos.add("pc")
        if estado.get("gravando"):
            ativos.add("camera")
    grupos = {"nucleo"} | ativos
    for g in list(memoria_sessao):           # envelhece o que ficou de turnos anteriores
        memoria_sessao[g] -= 1
        if memoria_sessao[g] <= 0:
            del memoria_sessao[g]
        else:
            grupos.add(g)
    for g in ativos:
        memoria_sessao[g] = TURNOS_PEGAJOSO
    return grupos | set(extras)


def filtrar(definicoes: list[dict], grupos: set) -> list[dict]:
    """Ferramentas dos grupos pedidos, em ordem estável (grupo, depois ordem original) para o cache acertar."""
    saida = [d for d in definicoes if grupo_de(d["name"]) in grupos]
    saida.sort(key=lambda d: GRUPOS_ORDEM.index(grupo_de(d["name"])))     # sort é estável: mantém a ordem dentro do grupo
    return saida


FERRAMENTA_HABILITAR = {
    "name": "habilitar_ferramentas",
    "description": ("Liga grupos de ferramentas que não estão disponíveis agora. Use SÓ quando precisar de algo que não "
                    "está na sua lista: " + "; ".join(f"{g} = {d}" for g, d in DESCRICAO_GRUPOS.items()) +
                    ". Depois de ligar, use as novas ferramentas no mesmo pedido, sem avisar o usuário."),
    "input_schema": {"type": "object",
                     "properties": {"grupos": {"type": "array", "items": {"type": "string", "enum": list(DESCRICAO_GRUPOS)}}},
                     "required": ["grupos"]},
}


def habilitar(entrada: dict, extras: set, definicoes: list[dict]) -> str:
    pedidos = entrada.get("grupos") if isinstance(entrada, dict) else None
    validos = [g for g in (pedidos or []) if g in DESCRICAO_GRUPOS]
    if not validos:
        return "Informe grupos válidos: " + ", ".join(DESCRICAO_GRUPOS)
    extras.update(validos)
    nomes = [d["name"] for d in definicoes if grupo_de(d["name"]) in validos]
    return f"Grupos ligados: {', '.join(validos)}. Ferramentas agora disponíveis: {', '.join(nomes) or '(nenhuma neste momento)'}."
