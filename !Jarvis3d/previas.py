"""
Miniaturas de páginas para o visual Aurora: depois de uma pesquisa, as páginas aparecem num canto da tela do Jarvis
(foto pequena + título). Clicando, o Chrome do Jarvis abre naquela página. Antes a pesquisa trazia o Chrome maximizado
para a frente e roubava a tela.

As fotos saem de um Chrome SEPARADO e INVISÍVEL (headless, perfil temporário, sem som), que fecha sozinho depois de
2 minutos parado. Nada é salvo em disco. Só abre de verdade (visível) uma URL que a própria tela recebeu de nós.
"""

import asyncio
import base64
import io
import time

from PIL import Image

import navegador

LARGURA = 480                 # px da miniatura enviada à tela
OCIOSO_S = 120

_pw = None
_browser = None
_trava = asyncio.Lock()
_ultimo_uso = 0.0
_vigia: asyncio.Task | None = None


async def _abrir():
    global _pw, _browser, _vigia
    if _browser is not None and _browser.is_connected():
        return _browser
    from playwright.async_api import async_playwright
    chrome = navegador._achar_chrome()
    if chrome is None:
        raise ValueError("sem Chrome")
    _pw = _pw or await async_playwright().start()
    _browser = await _pw.chromium.launch(executable_path=chrome, headless=True, args=["--mute-audio", "--no-first-run", "--disable-extensions"])
    if _vigia is None or _vigia.done():
        _vigia = asyncio.create_task(_fechar_quando_ocioso())
    return _browser


async def _fechar_quando_ocioso():
    global _browser
    while True:
        await asyncio.sleep(30)
        if _browser is not None and time.monotonic() - _ultimo_uso > OCIOSO_S and not _trava.locked():
            try:
                await _browser.close()
            except Exception:
                pass
            _browser = None
            return


async def miniatura(url: str, espera_ms: int = 1200) -> str | None:
    """JPEG em base64 (LARGURA px) da parte de cima da página, ou None se não deu (site lento, bloqueio, sem Chrome)."""
    global _ultimo_uso
    if not url.startswith(("http://", "https://")):
        return None
    async with _trava:
        _ultimo_uso = time.monotonic()
        ctx = None
        try:
            b = await _abrir()
            ctx = await b.new_context(viewport={"width": 1280, "height": 800}, locale="pt-BR", java_script_enabled=True)
            pg = await ctx.new_page()
            await pg.goto(url, wait_until="domcontentloaded", timeout=12000)
            await pg.wait_for_timeout(espera_ms)
            png = await pg.screenshot(type="jpeg", quality=70, timeout=6000)
        except Exception:
            return None
        finally:
            if ctx is not None:
                try:
                    await ctx.close()
                except Exception:
                    pass
            _ultimo_uso = time.monotonic()
    im = Image.open(io.BytesIO(png)).convert("RGB")
    im.thumbnail((LARGURA, LARGURA))
    saida = io.BytesIO()
    im.save(saida, "JPEG", quality=72)
    return base64.standard_b64encode(saida.getvalue()).decode()


async def enviar_previas(sessao, paginas: list[dict], maximo: int = 3):
    """Manda à tela um cartão por página, já com a miniatura (as fotos saem uma por vez, sem travar a resposta)."""
    for p in paginas[:maximo]:
        url = str(p.get("url") or "")
        if not url.startswith(("http://", "https://")):
            continue
        sessao.urls_previas.add(url)
        try:
            img = await miniatura(url)
            await sessao.enviar({"tipo": "cartao", "cartao": "pagina", "url": url, "titulo": str(p.get("titulo") or "")[:90],
                                 "site": str(p.get("site") or ""), "imagem": img})
        except Exception:
            return                                  # janela fechou ou Chrome indisponível: as miniaturas são só enfeite


async def abrir_visivel(url: str):
    """O usuário clicou na miniatura: abre a página no Chrome do Jarvis, na frente."""
    pg = await navegador.pagina(nova=True)
    await pg.goto(url, timeout=20000, wait_until="domcontentloaded")
    await navegador.mostrar_janela(True)
