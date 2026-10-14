"""
Atalhos de intenção: pedidos CURTOS e INEQUÍVOCOS (abrir programa, mídia, volume, tema, layout, hora) são resolvidos na hora, sem o modelo.
Poupa ~3 s e centavos por pedido ("abre a calculadora" vira ~0,3 s). Qualquer dúvida (frase longa, duas ações, alvo desconhecido) devolve None
e o pedido segue para o modelo como sempre. Só executa o que o Jarvis já faria sem pedir confirmação (nada que envie, pague, apague ou controle o mouse).
"""

import re
import unicodedata

COR = {"vermelho", "ciano", "azul", "ambar", "amarelo", "verde", "roxo", "gelo", "rosa"}
COR_TEMA = {"azul": "ciano", "amarelo": "ambar"}
NUMEROS = {"zero": 0, "dez": 10, "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70, "oitenta": 80, "noventa": 90, "cem": 100}
ENFEITE = re.compile(r"\b(jarvis|por favor|pra mim|para mim|ai|agora|rapidinho|rapido|entao|pode|poderia|consegue|voce)\b")
ABRIR = re.compile(r"^(abre|abra|abrir|inicia|inicie|iniciar|executa|execute|roda|chama|liga|ligue)\s+(?:o |a |os |as |um |uma )?(.+)$")
NAO_E_PROGRAMA = re.compile(r"\b(site|pagina|link|youtube|google|gmail|email|e-mail|whatsapp web|pasta|arquivo|camera|webcam|gravacao|modo|musica|video|aba)\b|[./:]")


def normalizar(t: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s%.,:/-]", " ", t)
    t = ENFEITE.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip(" .,!?")


def _numero(txt: str) -> int | None:
    m = re.search(r"\b(\d{1,3})\b", txt)
    if m:
        return max(0, min(100, int(m.group(1))))
    for palavra, v in NUMEROS.items():
        if re.search(rf"\b{palavra}\b", txt):
            return v
    return None


def interpretar(texto: str, achar_programa) -> dict | None:
    """Devolve {'acao': ..., ...} ou None. `achar_programa(nome) -> nome_exibido | None` resolve nomes de programas instalados."""
    t = normalizar(texto)
    if not t or len(t.split()) > 7:
        return None
    if re.search(r"\b(e depois|e tambem|e entao|depois|alem disso)\b", t) or re.search(r"\be (abre|abra|toca|toque|pesquisa|manda|envia|escreve|digita|clica)\b", t):
        return None                                           # duas ações: deixa para o modelo

    # ---- mídia (teclas de mídia do Windows)
    if re.fullmatch(r"(pula|pule|pular|passa|passe|avanca|proxima)( essa| a| para a| pra)?( musica| faixa)?( seguinte)?|(vai |va )?(para |pra )?(a )?proxima( musica| faixa)?", t):
        return {"acao": "midia", "valor": "proxima", "fala": "Pulei."}
    if re.fullmatch(r"(volta|voltar|volte)( a| para a| pra)?( musica| faixa)?( anterior)?|(musica|faixa) anterior|anterior", t) and "anterior" in t or re.fullmatch(r"volta (a )?(musica|faixa)", t):
        return {"acao": "midia", "valor": "anterior", "fala": "Voltei."}
    if re.fullmatch(r"(pausa|pause|pausar)( a| essa)?( musica| faixa)?|(continua|continue|retoma|retome|da play|play|resume)( a| essa)?( musica| faixa)?|(para|pare) (a )?(musica|faixa)", t):
        return {"acao": "midia", "valor": "play_pause", "fala": "Feito."}

    # ---- volume
    if re.search(r"\bvolume\b|\bsom\b|\bmudo\b|\bmuta\b|\bmute\b", t):
        if re.fullmatch(r"(coloca|poe|ponha|deixa|deixe|bota)? ?(o )?(som |volume )?(no )?(mudo|mute)|muta( o)?( som| volume)?|(tira|tire|desliga|desligue) o som|silencia( o)?( som| volume)?", t):
            return {"acao": "volume", "valor": "mudo", "fala": "Som silenciado."}
        n = _numero(t)
        if n is not None and re.fullmatch(r"(coloca|poe|ponha|deixa|deixe|bota|muda|define|ajusta|ajuste|seta)? ?(o )?(volume|som)( em| para| pra| no| a)? ?\d{0,3}[a-z ]*%?|volume \d{1,3}%?", t):
            return {"acao": "volume", "valor": "definir", "n": n, "fala": f"Volume em {n}."}
        if re.fullmatch(r"(aumenta|aumente|sobe|suba|mais|levanta)( o)?( volume| som)?( um pouco| mais)?|(volume|som) (mais )?(alto|pra cima)|mais (volume|alto)", t):
            return {"acao": "volume", "valor": "subir", "fala": "Aumentei."}
        if re.fullmatch(r"(abaixa|abaixe|diminui|diminua|desce|desca|reduz|reduza|menos)( o)?( volume| som)?( um pouco| mais)?|(volume|som) (mais )?(baixo|pra baixo)|menos (volume|alto)", t):
            return {"acao": "volume", "valor": "descer", "fala": "Abaixei."}

    # ---- tela
    m = re.fullmatch(r"(muda|mude|troca|troque|coloca|ponha|poe|deixa|deixe)( o| a)?( tema| cor| visual)?( da tela| do jarvis)?( para| pra| em| de| no)?( o)? ?(\w+)", t)
    if m and m.group(7) in COR and ("tema" in t or "cor" in t or "visual" in t or "tela" in t):
        cor = COR_TEMA.get(m.group(7), m.group(7))
        return {"acao": "ui", "nome": "ui_tema", "entrada": {"tema": cor}, "fala": "Pronto."}
    if re.fullmatch(r"(modo|ativa o modo|ligar o modo|liga o modo|entra no modo|entrar no modo) foco|foco|esconde( os| as)? (paineis|painel|barras|laterais)( laterais)?|so o centro|oculta( os| as)? (paineis|barras)( laterais)?", t):
        return {"acao": "ui", "nome": "ui_layout", "entrada": {"acao": "preset", "nome": "foco"}, "fala": "Modo foco."}
    if re.fullmatch(r"(mostra|mostre|exibe|exiba|volta com|traz)( os| as| de volta)? ?(tudo|paineis|painel)( de volta)?", t):
        return {"acao": "ui", "nome": "ui_painel", "entrada": {"painel": "todos", "acao": "mostrar"}, "fala": "Tudo de volta."}
    if re.fullmatch(r"(mostra|mostre|exibe|exiba|volta com|traz)( as| de volta)? ?(barras|laterais|barras laterais)( de volta)?|modo moderno|layout moderno", t):
        return {"acao": "ui", "nome": "ui_layout", "entrada": {"acao": "preset", "nome": "moderno"}, "fala": "Pronto."}
    if re.fullmatch(r"modo completo|layout completo", t):
        return {"acao": "ui", "nome": "ui_layout", "entrada": {"acao": "preset", "nome": "completo"}, "fala": "Modo completo."}
    if re.fullmatch(r"(modo|ativa o modo|liga o modo|entra no modo) cinema|cinema", t):
        return {"acao": "ui", "nome": "ui_layout", "entrada": {"acao": "preset", "nome": "cinema"}, "fala": "Modo cinema."}

    # ---- hora
    if re.fullmatch(r"(que|qual a|qual e a|me diz a|me fala a|diz a|fala a)? ?(horas?)( sao| e| agora| tem| eh)?( agora)?|(que|qual)( horas?| e a hora| a hora)( sao| e)?( agora)?", t) or t in ("que horas sao", "que horas e", "horas", "que hora e"):
        return {"acao": "hora"}

    # ---- abrir programa (só se o nome existir entre os programas instalados)
    m = ABRIR.match(t)
    if m:
        alvo = m.group(2).strip()
        if alvo and not NAO_E_PROGRAMA.search(alvo) and len(alvo.split()) <= 4:
            achado = achar_programa(alvo)
            if achado:
                return {"acao": "abrir", "programa": achado, "fala": f"Abrindo {achado}."}
    return None
