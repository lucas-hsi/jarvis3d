"""Modos especialista: um conjunto de regras que entra no contexto do Jarvis até o usuário mudar. O modelo liga sozinho pelo assunto (ferramenta modo_especialista)."""

import re

BASE = ("Trabalhe como especialista: mostre as premissas e os números, diga o que NÃO sabe ou não conseguiu verificar, separe fato de opinião, "
        "cite as fontes quando houver, e termine com uma recomendação objetiva. Respostas faladas continuam curtas: detalhe só se pedirem.")

MODOS = {
    "geral": ("Assistente geral", ""),
    "financas": ("Finanças pessoais", "Ajude com orçamento, dívidas, fluxo de caixa, impostos e conceitos de investimento em nível EDUCATIVO. Faça as contas passo a passo e confira os números. "
               "Não dê recomendação personalizada de comprar ou vender ativos; compare opções e riscos e lembre que decisões de investimento são do usuário."),
    "saude": ("Saúde (informativo)", "Explique de forma clara e cuidadosa, em nível informativo. Aponte sinais de alerta que exigem atendimento médico, evite diagnóstico e nunca sugira trocar ou parar remédio sem médico."),
    "codigo": ("Programação", "Entregue código correto e enxuto, explique a ideia em uma frase, aponte casos de borda e riscos. Para algo difícil, use pensar_fundo. Rode comandos só com terminal_executar (com confirmação)."),
    "redacao": ("Redação e comunicação", "Escreva com clareza e no tom pedido (formal, direto, persuasivo). Dê uma versão pronta para usar e, se útil, uma alternativa mais curta."),
    "estudo": ("Estudo e aprendizado", "Ensine em passos curtos, com exemplos e uma pergunta de checagem no fim. Adapte ao nível do usuário e proponha um plano de revisão quando fizer sentido."),
    "negocios": ("Negócios e estratégia", "Pense como consultor: objetivo, dados, alternativas, riscos, próximo passo mensurável. Use as notas do Obsidian do usuário para contexto dos projetos dele."),
    "juridico": ("Jurídico (informativo)", "Explique conceitos e caminhos possíveis em nível INFORMATIVO, deixando claro que não substitui advogado. Aponte prazos e documentos a juntar. Assunto jurídico pessoal só vai ao Obsidian com confirmação."),
    "pesquisa": ("Pesquisa e análise", "Para qualquer tema que exija dados atuais ou comparação, use pesquisa_profunda e informe as fontes e o grau de certeza."),
}

FERRAMENTA = {
    "name": "modo_especialista",
    "description": ("Liga um modo especialista que melhora a resposta no assunto: " + ", ".join(f"{k} ({v[0]})" for k, v in MODOS.items() if k != "geral") +
                    ". Ligue quando o assunto da conversa mudar para uma dessas áreas (e 'geral' para voltar ao normal). Não precisa avisar o usuário em voz alta."),
    "input_schema": {"type": "object", "properties": {"modo": {"type": "string", "enum": list(MODOS)}}, "required": ["modo"]},
}


def aplicar(sessao, modo: str) -> str:
    modo = (modo or "geral").lower()
    if modo not in MODOS:
        raise ValueError("Modo desconhecido: " + modo)
    sessao.modo = modo
    return f"Modo '{MODOS[modo][0]}' ligado." if modo != "geral" else "Voltou ao modo geral."


def bloco(sessao) -> str:
    modo = getattr(sessao, "modo", "geral")
    if modo == "geral" or modo not in MODOS:
        return ""
    return f"\n=== MODO ESPECIALISTA: {MODOS[modo][0]} ===\n{BASE}\n{MODOS[modo][1]}"


# palavras que sugerem uma pergunta DIFÍCIL (o roteador usa o modelo maior, se o orçamento do dia permitir)
DIFICIL = re.compile(r"\b(analis[ae]|compar[ae]|estrateg\w*|planej\w*|arquitet\w*|otimiz\w*|calcul\w*|demonstr\w*|prós e contras|pros e contras|vale a pena|"
                     r"melhor op[cç][aã]o|diagn[oó]stic\w*|debug\w*|refator\w*|revis[ae]|contrato|detalhad\w*|a fundo|com calma|passo a passo|por que .{12,})", re.IGNORECASE)


def parece_dificil(texto: str) -> bool:
    return len(texto.split()) >= 8 and bool(DIFICIL.search(texto))
