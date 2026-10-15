"""
Modo gravação (direção de vídeo) do Jarvis: ele vira o seu assistente de direção enquanto você grava.

Como funciona:
- A janela do Jarvis liga a webcam (a luz da câmera e a prévia ao vivo ficam visíveis) e, a cada `intervalo` segundos, manda um
  quadro reduzido + medidas locais (brilho, contraste, movimento, rosto, nível do microfone) para cá.
- A IA olha o quadro como um diretor e só escreve uma dica curta se houver algo a corrigir (enquadramento, luz, fundo, postura,
  olhar, som). Se está tudo bem, ela não diz nada.
- Durante a gravação o Jarvis fica em SILÊNCIO: sem voz e sem efeitos sonoros (para não entrar no seu vídeo). As dicas aparecem só
  em texto na tela. Ele só responde se você chamar pelo nome (e a resposta também vem em texto).
- Ao parar, ele resume o que apareceu.

Privacidade e custo (impostos aqui, não pelo modelo):
- Pede confirmação ao ligar (fica claro que os quadros vão à IA). Nada é gravado em disco; cada quadro é descartado depois da análise.
- Intervalo mínimo de 10 s, no máximo 1 análise em andamento, no máximo 300 análises e 2 horas por ativação.
"""

import time

import provedor

NOME = "modo_gravacao"
ROTULO = "DIREÇÃO"
INTERVALO_MIN, INTERVALO_PADRAO, INTERVALO_MAX = 10, 25, 120
MAX_ANALISES, MAX_SEGUNDOS = 300, 2 * 3600
REPETIR_APOS = 90          # mesma categoria de dica só volta depois disso (a não ser que fique grave)

CATEGORIAS = ["enquadramento", "luz", "fundo", "postura", "olhar", "som", "geral"]


def definicao() -> dict:
    return {
        "name": NOME,
        "description": ("Liga ou desliga o MODO GRAVAÇÃO: você vira o assistente de direção de vídeo. A webcam fica ao vivo e, a cada poucos segundos, "
                        "você recebe uma análise do quadro e mostra DICAS EM TEXTO na tela (enquadramento, luz, fundo, postura, olhar na câmera, som). "
                        "Use 'iniciar' quando o usuário disser que vai gravar um vídeo ou pedir ajuda para gravar. Enquanto ligado você fica em SILÊNCIO "
                        "(sem voz nem sons, para não entrar no vídeo) e só responde, em texto, se ele te chamar pelo nome. Use 'parar' quando ele disser que acabou, "
                        "mandar cortar ou parar de gravar; aí você volta a falar e resume as dicas. 'status' mostra o que já foi apontado."),
        "input_schema": {"type": "object", "properties": {
            "acao": {"type": "string", "enum": ["iniciar", "parar", "status"]},
            "objetivo": {"type": "string", "description": "O que ele vai gravar e para onde (ex.: 'vídeo de vendas para o Instagram, em pé, fundo da loja'). Ajuda a direção."},
            "intervalo_s": {"type": "integer", "description": f"Segundos entre as análises ({INTERVALO_MIN} a {INTERVALO_MAX}, padrão {INTERVALO_PADRAO})."}},
            "required": ["acao"]},
    }


FERRAMENTA_DICA = {
    "name": "dica_de_direcao",
    "description": "Registra a dica de direção para este quadro. Se não há nada relevante a corrigir, devolva nota vazia e gravidade 0.",
    "input_schema": {"type": "object", "properties": {
        "nota": {"type": "string", "description": "UMA frase curta e acionável em português do Brasil (máx. 110 caracteres), ou vazio se está tudo bem."},
        "gravidade": {"type": "integer", "description": "0 = tudo bem, 1 = melhoraria o vídeo, 2 = vai estragar a gravação (corrigir já)."},
        "categoria": {"type": "string", "enum": CATEGORIAS}},
        "required": ["nota", "gravidade", "categoria"]},
}

PROMPT = """Você é o diretor de vídeo do {nome}, que está gravando agora. Você recebe um quadro da webcam dele (a imagem NÃO é espelhada: esquerda e direita são as reais) e medidas locais.
Aponte só o que ele pode corrigir AGORA e que melhora de verdade o vídeo:
- enquadramento (cabeça cortada, muito alto/baixo, fora do centro, muito longe ou perto), luz (escuro, estourado, contraluz, sombra forte no rosto), fundo (bagunça, objeto estranho atrás da cabeça, pessoa passando), postura (curvado, inclinado, mãos cobrindo o rosto), olhar (não está olhando para a lente), som (use o nível do microfone das medidas: muito baixo, estourando ou ruído).
Regras: uma frase curta e direta, sem rodeios. Não elogie. Se está tudo bem, devolva nota vazia e gravidade 0 (isso é o normal na maioria dos quadros). Não repita o que já foi dito recentemente, a menos que continue errado e grave. Não identifique pessoas pelo rosto nem comente o corpo dele; fale só de técnica de vídeo. Português do Brasil."""


class Direcao:
    def __init__(self):
        self.ativa = False
        self.objetivo = ""
        self.intervalo = INTERVALO_PADRAO
        self.inicio = 0.0
        self.analises = 0
        self.em_andamento = False
        self.notas: list[dict] = []          # {t, categoria, gravidade, texto}
        self.ultima_por_categoria: dict[str, float] = {}

    def iniciar(self, objetivo: str, intervalo: int | None):
        self.ativa = True
        self.objetivo = (objetivo or "").strip()[:300]
        try:
            self.intervalo = max(INTERVALO_MIN, min(INTERVALO_MAX, int(intervalo or INTERVALO_PADRAO)))
        except (TypeError, ValueError):
            self.intervalo = INTERVALO_PADRAO
        self.inicio, self.analises, self.em_andamento = time.time(), 0, False
        self.notas.clear()
        self.ultima_por_categoria.clear()

    def parar(self):
        self.ativa = False
        self.em_andamento = False

    def estourou(self) -> str | None:
        if self.analises >= MAX_ANALISES:
            return "limite de análises"
        if time.time() - self.inicio > MAX_SEGUNDOS:
            return "limite de tempo"
        return None

    def registrar(self, nota: str, gravidade: int, categoria: str) -> dict | None:
        """Devolve a dica a mostrar, ou None se está tudo bem / repetida."""
        nota = (nota or "").strip()
        if not nota or gravidade <= 0:
            return None
        categoria = categoria if categoria in CATEGORIAS else "geral"
        agora = time.time()
        ultima = self.ultima_por_categoria.get(categoria, 0)
        if agora - ultima < (20 if gravidade >= 2 else REPETIR_APOS):
            return None
        self.ultima_por_categoria[categoria] = agora
        item = {"t": round(agora - self.inicio), "categoria": categoria, "gravidade": min(2, int(gravidade)), "texto": nota[:140]}
        self.notas.append(item)
        return item

    def resumo(self) -> str:
        dur = round((time.time() - self.inicio) / 60, 1) if self.inicio else 0
        if not self.notas:
            return f"Modo gravação encerrado após {dur} min ({self.analises} análises). A direção não apontou nenhum problema."
        linhas = [f"[{n['t'] // 60}:{n['t'] % 60:02d}] ({n['categoria']}{', GRAVE' if n['gravidade'] >= 2 else ''}) {n['texto']}" for n in self.notas[-25:]]
        return f"Modo gravação encerrado após {dur} min ({self.analises} análises). Dicas dadas:\n" + "\n".join(linhas)


def _medidas(m: dict) -> str:
    if not isinstance(m, dict):
        return "(sem medidas)"
    def num(k, nd=2):
        v = m.get(k)
        return f"{v:.{nd}f}" if isinstance(v, (int, float)) else "?"
    rosto = m.get("rosto")
    if isinstance(rosto, dict):
        try:
            r = (f"rosto detectado: centro x={float(rosto.get('cx', 0)):.2f}, y={float(rosto.get('cy', 0)):.2f}, "
                 f"largura={float(rosto.get('w', 0)):.2f} (0 a 1 da imagem)")
        except (TypeError, ValueError):
            r = "rosto detectado"
    elif rosto is False:
        r = "nenhum rosto detectado pelo navegador"
    else:
        r = "detecção de rosto indisponível"
    return (f"brilho médio {num('brilho', 0)}/255, contraste {num('contraste', 0)}, pixels estourados {num('estourado', 3)}, "
            f"movimento {num('movimento', 1)}, microfone médio {num('mic_medio', 2)} pico {num('mic_pico', 2)} (0 a 1); {r}")


async def analisar(ai, modelo: str, nome: str, jpeg: bytes, metricas: dict, objetivo: str, recentes: list[dict]) -> dict:
    """Pede ao modelo a dica deste quadro. Devolve {nota, gravidade, categoria} (nota vazia = tudo bem). Nunca levanta erro."""
    import base64
    ja_ditas = "; ".join(f"{n['categoria']}: {n['texto']}" for n in recentes[-4:]) or "(nada ainda)"
    texto = (f"Objetivo do vídeo: {objetivo or '(não informado)'}\nMedidas locais: {_medidas(metricas)}\nDicas já dadas: {ja_ditas}\nQuadro atual:")
    try:
        r = await ai.messages.create(
            model=modelo, max_tokens=300, system=PROMPT.replace("{nome}", nome),
            messages=[{"role": "user", "content": [
                {"type": "text", "text": texto},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.standard_b64encode(jpeg).decode()}}]}],
            tools=[FERRAMENTA_DICA], tool_choice={"type": "tool", "name": "dica_de_direcao"}, **provedor.extras(ai))
    except Exception as e:
        print(f"[jarvis] direção: {type(e).__name__}: {e}", flush=True)
        return {"nota": "", "gravidade": 0, "categoria": "geral", "erro": type(e).__name__}
    bloco = next((b for b in r.content if b.type == "tool_use"), None)
    d = (bloco.input if bloco else None) or {}
    try:
        return {"nota": str(d.get("nota") or ""), "gravidade": int(d.get("gravidade") or 0), "categoria": str(d.get("categoria") or "geral")}
    except (TypeError, ValueError):
        return {"nota": "", "gravidade": 0, "categoria": "geral"}
