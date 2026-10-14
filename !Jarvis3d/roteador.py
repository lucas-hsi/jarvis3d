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

GRUPOS_ORDEM = ("nucleo", "arquivos", "pc", "navegador", "google", "camera", "interface")

NUCLEO = {
    "pesquisar_web", "ler_pagina", "abrir_site", "ver_tela", "noticias", "abrir_programa", "consultar_cofre", "ler_nota",
    "controlar_volume", "controlar_midia", "lembrar", "buscar_memoria", "esquecer_memoria", "anotar_no_cofre",
    "acrescentar_no_cofre", "trilha_sonora", "encerrar_conversa", "dormir", "habilitar_ferramentas", "briefing",
}
ARQUIVOS = {"listar_pasta", "organizar_pasta", "mover_itens", "renomear_item", "criar_pasta", "mover_para_lixo",
            "desfazer_organizacao", "abrir_pasta"}
PC = {"listar_janelas", "gerenciar_janela", "mostrar_area_de_trabalho", "bloquear_tela", "iniciar_controle", "clicar",
      "digitar", "pressionar_teclas", "rolar", "janela_ver", "janela_acao"}
CAMERA = {"ver_camera", "modo_gravacao"}
NAVEGADOR_EXTRA = {"youtube_buscar", "video_controle"}

DESCRICAO_GRUPOS = {
    "arquivos": "listar, organizar, mover, renomear e mandar para o lixo arquivos e pastas (Downloads, Documentos, Área de Trabalho)",
    "pc": "janelas do Windows, clicar/digitar em programas (janela_ver/janela_acao), mouse, teclado, bloquear a tela",
    "navegador": "YouTube e música, controle de vídeo, abrir e operar sites no navegador do Jarvis",
    "google": "Google Agenda, Gmail e Drive",
    "camera": "webcam (olhar roupa/objetos) e modo gravação de vídeo",
    "interface": "visual da tela do Jarvis (tema, painéis, layout, reator, efeitos)",
}


def grupo_de(nome: str) -> str:
    if nome in NUCLEO:
        return "nucleo"
    if nome in ARQUIVOS:
        return "arquivos"
    if nome in PC:
        return "pc"
    if nome in CAMERA:
        return "camera"
    if nome in NAVEGADOR_EXTRA or nome.startswith("navegador_"):
        return "navegador"
    if nome.startswith(("agenda_", "email_", "drive_", "google_")):
        return "google"
    if nome.startswith("ui_"):
        return "interface"
    return "nucleo"          # ferramenta nova sem grupo: vai sempre (seguro)


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


GATILHOS = {
    "arquivos": re.compile(r"pasta|arquivo|download|documento|organiz|renome|lixeira|lixo|desfaz|\bmov[ae]|imagens|\bpdf|baixad"),
    "pc": re.compile(r"janela|minimiz|maximiz|\bfech|clic|digit|escrev|\btecla|atalho|mouse|\brol(e|ar)|desktop|area de trabalho|"
                     r"bloque|\btela|programa|aplicativ|\bapp\b|botao|\bmenu|instal|configurac|painel de controle|abr[ae]|"
                     r"word|excel|bloco de notas|explorador|calculadora|whatsapp|discord|spotify|obs\b|vscode|terminal"),
    "navegador": re.compile(r"youtube|music|\bsom\b|toc[ae]|toque|video|\bpul[ae]|proxim|anterior|pausa|continu|anunci|\bsite|pagina|"
                            r"navegador|\baba|pesquis|google|\blink|login|entra |compr|playlist|letra|\bclip|\bbusca|procura|"
                            r"mercado livre|olx|amazon|instagram|facebook|linkedin|\bweb\b|internet|\bhttp|\.com"),
    "google": re.compile(r"agenda|e-?mail|gmail|drive|lembret|lembra|compromisso|reuniao|calendario|google|rascunho|evento|"
                         r"caixa de entrada|convite|marcar|nao lid|remetente|anexo"),
    "camera": re.compile(r"camera|webcam|\bfoto|me ve|olha pra|olhe|roupa|grav|film|vestid|outfit|enquadr|iluminac"),
    "interface": re.compile(r"\btema|painel|paineis|layout|reator|\bcor\b|\bcores\b|efeito|interface|visual|esfera|minimo|"
                            r"modo foco|esconde|mostra os|brilho|animac|fundo|vermelho|azul|verde|ambar"),
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
