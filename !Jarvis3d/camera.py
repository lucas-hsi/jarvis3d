"""
Visão de webcam (sob demanda).

O navegador (a janela do Jarvis) liga a câmera só no instante da foto, mostra uma prévia com contagem regressiva,
tira UM quadro, desliga a câmera e manda o quadro para cá. Nada é gravado em disco. O quadro vai ao modelo como
imagem dentro desta fala e não fica no histórico.

Privacidade (imposta aqui, não pelo modelo):
- A primeira foto de cada sessão pede a confirmação do usuário (painel + voz).
- Uma foto por chamada; sem vídeo contínuo; a prévia e a luz da câmera ficam visíveis durante a captura.
"""

import asyncio
import base64
import io
import uuid

from PIL import Image

NOME = "ver_camera"
ROTULO = "CÂMERA"
LIMITE_BASE64 = 4_000_000


def definicao() -> dict:
    return {
        "name": NOME,
        "description": ("Tira uma foto com a webcam do notebook agora e devolve a imagem para você analisar. Use quando o usuário "
                        "pedir para você olhar para ele ou para algo que ele mostra (roupa que veste, objeto, documento, ambiente, "
                        "um produto, um prato...). A câmera mostra uma contagem regressiva para ele se posicionar. "
                        "Descreva o que vê com objetividade e dê dicas úteis. Não identifique pessoas pelo rosto."),
        "input_schema": {"type": "object", "properties": {
            "segundos": {"type": "number", "description": "Contagem regressiva antes da foto, de 1 a 8 (padrão 3). Use mais tempo se ele precisar pegar um objeto."}},
            "required": []},
    }


async def executar(entrada: dict, sessao, ver_imagem_bloco) -> list | str:
    if not sessao.camera_ok and getattr(sessao, "liberado", lambda _o: False)("camera"):
        sessao.camera_ok = True                     # ele pediu para olhar: a tela já mostra a contagem, o flash e a foto
    if not sessao.camera_ok:
        ok = await sessao.confirmar(
            "Usar a câmera do notebook",
            ["Vou tirar UMA foto agora e enviá-la à IA para analisar.",
             "A câmera só liga no instante da foto e a imagem não é salva no disco.",
             "Vale para esta sessão; avisarei na tela a cada foto."])
        if not ok:
            return "O usuário NÃO autorizou a câmera. Não insista; diga que respeita a decisão."
        sessao.camera_ok = True
    try:
        segundos = max(1.0, min(8.0, float(entrada.get("segundos") or 3)))
    except (TypeError, ValueError):
        segundos = 3.0
    jpeg = await sessao.capturar_camera(segundos)
    return ver_imagem_bloco(jpeg)


def validar_jpeg(b64: str) -> bytes:
    """Confere que o que o navegador mandou é mesmo uma imagem razoável e a recodifica (tira metadados)."""
    if not isinstance(b64, str) or not b64 or len(b64) > LIMITE_BASE64:
        raise ValueError("Imagem ausente ou grande demais.")
    try:
        im = Image.open(io.BytesIO(base64.b64decode(b64, validate=True)))
        im.load()
    except Exception:
        raise ValueError("A imagem recebida da câmera é inválida.")
    if max(im.size) > 4096 or min(im.size) < 64:
        raise ValueError("Tamanho de imagem inesperado.")
    im = im.convert("RGB")
    im.thumbnail((1024, 1024))
    saida = io.BytesIO()
    im.save(saida, "JPEG", quality=82)
    return saida.getvalue()


def bloco_de_imagem(jpeg: bytes) -> list:
    return [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                     "data": base64.standard_b64encode(jpeg).decode()}},
        {"type": "text", "text": "Foto da webcam tirada agora (a imagem não é espelhada: esquerda e direita são as reais)."},
    ]


def novo_id() -> str:
    return uuid.uuid4().hex[:8]
