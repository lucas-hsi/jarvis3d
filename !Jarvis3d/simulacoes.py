"""
Modo de TESTE (JARVIS_SIMULAR_FERRAMENTAS=1): as ferramentas não fazem nada de verdade e devolvem respostas plausíveis.
Serve para avaliar, com o modelo REAL, se ele escolhe a ferramenta certa (scripts/cenarios_reais.py) sem abrir
programa, tocar música, mexer em arquivo, enviar e-mail ou tocar na agenda. Nunca ligado no uso normal.
"""

import json

PADRAO = "[simulado] ferramenta executada com sucesso."

RESPOSTAS = {
    "youtube_buscar": "Tocando: Back in Black — AC/DC (4:15)\nOutras opções:\n2. Highway to Hell — AC/DC (3:28)",
    "video_controle": "Agora: Highway to Hell — AC/DC.",
    "agenda_listar": "1. Reunião com cliente da loja — amanhã 10:00 (id ev1)\n2. Almoço com a Ana — amanhã 12:30 (id ev2)",
    "email_listar": "1. [id m1] Fatura do cartão — Banco X — vence dia 10\n2. [id m2] Orçamento do pneu — Oficina do Zé",
    "pesquisar_web": "Resultados: dólar comercial fecha a R$ 5,12 (fonte: exemplo.com).",
    "noticias": "Manchetes: 1) Inflação desacelera em setembro. 2) Dólar em queda.",
    "abrir_programa": "Aberto: calculadora.",
    "consultar_cofre": "[Projeto/Projeto - Riscos e pendências.md]\n1. Rever o fluxo de anúncios.",
    "ler_nota": "Nota: conteúdo de exemplo da nota.",
    "listar_pasta": "Downloads: 4 arquivos (2 imagens, 1 PDF, 1 documento).",
    "organizar_pasta": "O usuário cancelou. Nada foi alterado.",
    "listar_janelas": "Google Chrome\nBloco de Notas\nCalculadora",
    "gerenciar_janela": "minimizar: Google Chrome",
    "iniciar_controle": "Controle autorizado. Comece com janela_ver.",
    "janela_ver": "Janela: Bloco de Notas (notepad.exe)\nControles:\n[1] campo: Editor de texto (vazio)\n[2] botão: Salvar\n[3] menu: Arquivo",
    "janela_acao": "Acionei 'Salvar'. (1/20 ações)",
    "ver_tela": "[simulado] imagem da tela.",
    "ver_camera": "[simulado] foto da câmera: camisa azul, ambiente bem iluminado.",
    "lembrar": "Memória guardada.",
    "buscar_memoria": "Nenhuma memória relacionada.",
    "anotar_no_cofre": "Nota criada em Ideias/ e linkada no índice.",
    "acrescentar_no_cofre": "Texto acrescentado à nota.",
    "agenda_lembrete": "Lembrete criado.",
    "email_rascunho": "Rascunho criado.",
    "email_enviar": "O usuário cancelou. Nada foi enviado.",
    "controlar_volume": "Volume ajustado.",
    "controlar_midia": "Feito.",
    "briefing": "Agora: terça, 14 de outubro, 09:00.\n=== COMPROMISSOS ===\n1. Reunião com cliente — 10:00\n=== E-MAILS ===\n1. Fatura vence dia 10",
}


def resposta(nome: str, entrada) -> str:
    if nome.startswith("ui_"):
        return "Interface atualizada."
    return RESPOSTAS.get(nome) or f"{PADRAO} ({nome} {json.dumps(entrada, ensure_ascii=False)[:120]})"
