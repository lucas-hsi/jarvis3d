"""
Navegador do Jarvis: um Chrome dedicado (perfil próprio e persistente) que ele opera pelo CONTEÚDO da página
(botões, links e campos numerados), muito mais confiável do que clicar por coordenadas da tela.

- Perfil próprio em %LOCALAPPDATA%\\JarvisNavegador: entre uma vez no YouTube/Spotify ali e o login fica salvo
  (com YouTube Premium não há anúncios). É um Chrome comum, sem a faixa "controlado por software de teste".
- Vídeo/música: tocar no YouTube, pausar, pular faixa, pular anúncio, avançar, volume, velocidade...
- Pular anúncio só clica no botão "Pular" que o próprio YouTube oferece; anúncio sem botão não é pulado.
- Segurança: senhas nunca são digitadas; ações de compra/pagamento/exclusão/publicação e páginas de banco pedem
  confirmação do usuário (sessao.confirmar); limite de ações por pedido; só http/https.
"""

import asyncio
import os
import re
import socket
import subprocess
from pathlib import Path
from urllib.parse import quote_plus, urlparse

BASE = Path(__file__).parent
PORTA_CDP = int(os.environ.get("JARVIS_NAVEGADOR_PORTA", 9333))
PERFIL = Path(os.environ.get("JARVIS_NAVEGADOR_PERFIL", Path(os.environ.get("LOCALAPPDATA", str(BASE))) / "JarvisNavegador"))
ARGS_EXTRAS = os.environ.get("JARVIS_NAVEGADOR_ARGS", "").split()   # testes: --headless=new
LIMITE_ACOES = 40

_pw = None
_browser = None
_ctx = None
_ativa = None
_vigia = None
_trava = asyncio.Lock()
_midia_ativa = False
_restaurar_tarefa: asyncio.Task | None = None
ao_mudar_midia = None            # callback async(bool): o servidor avisa a tela
pular_anuncios_auto = True


# ================================================================== o Chrome

def _porta_aberta() -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", PORTA_CDP)) == 0


def _achar_chrome() -> str | None:
    for c in (os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
              os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
              os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
              os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe")):
        if os.path.exists(c):
            return c
    return None


async def contexto():
    global _pw, _browser, _ctx, _vigia
    if _ctx is not None and _browser is not None and _browser.is_connected():
        return _ctx
    from playwright.async_api import async_playwright
    if not _porta_aberta():
        chrome = _achar_chrome()
        if chrome is None:
            raise ValueError("Não encontrei o Chrome neste computador.")
        PERFIL.mkdir(parents=True, exist_ok=True)
        subprocess.Popen([chrome, f"--remote-debugging-port={PORTA_CDP}", "--remote-debugging-address=127.0.0.1",
                          f"--user-data-dir={PERFIL}", "--no-first-run", "--no-default-browser-check",
                          "--autoplay-policy=no-user-gesture-required", "--start-maximized", *ARGS_EXTRAS, "about:blank"],
                         creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        for _ in range(60):
            await asyncio.sleep(0.25)
            if _porta_aberta():
                break
        else:
            raise ValueError("O Chrome do Jarvis não abriu a tempo.")
    _pw = _pw or await async_playwright().start()
    _browser = await _pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORTA_CDP}")
    _ctx = _browser.contexts[0] if _browser.contexts else await _browser.new_context()
    if _vigia is None or _vigia.done():
        _vigia = asyncio.create_task(_vigiar())
    return _ctx


async def pagina(nova: bool = False, mostrar: bool = False):
    global _ativa
    ctx = await contexto()
    if nova or _ativa is None or _ativa.is_closed():
        abertas = [p for p in ctx.pages if not p.is_closed()]
        _ativa = abertas[-1] if abertas and not nova else await ctx.new_page()
    if mostrar:
        await mostrar_janela(True)
    return _ativa


async def mostrar_janela(mostrar: bool):
    """Traz o Chrome do Jarvis para a frente (ou o minimiza). Falha em silêncio se não der."""
    try:
        pg = await pagina()
        cdp = await _ctx.new_cdp_session(pg)
        janela = await cdp.send("Browser.getWindowForTarget")
        await cdp.send("Browser.setWindowBounds", {"windowId": janela["windowId"],
                                                   "bounds": {"windowState": "maximized" if mostrar else "minimized"}})
        if mostrar:
            await pg.bring_to_front()
        await cdp.detach()
    except Exception:
        pass


def ativo() -> bool:
    return _browser is not None and _browser.is_connected()


async def desconectar():
    """Solta o Playwright mas deixa o Chrome aberto (a música continua)."""
    global _pw, _browser, _ctx, _ativa, _vigia
    if _vigia and not _vigia.done():
        _vigia.cancel()
    _vigia = None
    try:
        if _pw:
            await _pw.stop()
    except Exception:
        pass
    _pw = _browser = _ctx = _ativa = None


# ================================================================== vigia: anúncios e "tem mídia tocando?"

SKIP_SELETORES = [".ytp-skip-ad-button", ".ytp-ad-skip-button-modern", ".ytp-ad-skip-button", ".ytp-ad-skip-button-container button",
                  "button.ytp-ad-skip-button-modern"]

JS_ESTADO_VIDEO = r"""
() => {
  const player = document.querySelector('#movie_player');
  const v = document.querySelector('video.html5-main-video') || document.querySelector('video');
  const txt = (s) => (document.querySelector(s) || {}).innerText || '';
  const pular = [%SKIPS%].some((s) => { const e = document.querySelector(s); return e && e.offsetParent !== null; });
  return {
    tem_video: !!v,
    tocando: !!v && !v.paused && !v.ended && v.readyState > 2,
    pausado: v ? v.paused : null,
    tempo: v ? Math.floor(v.currentTime) : null,
    duracao: v && isFinite(v.duration) ? Math.floor(v.duration) : null,
    titulo: (txt('h1.ytd-watch-metadata') || txt('ytd-watch-metadata h1') || document.title || '').trim(),
    canal: txt('ytd-channel-name a').trim(),
    anuncio: !!(player && player.classList.contains('ad-showing')),
    pode_pular: pular,
    volume: player && player.getVolume ? player.getVolume() : (v ? Math.round(v.volume * 100) : null),
    mudo: player && player.isMuted ? player.isMuted() : (v ? v.muted : null),
    url: location.href,
  };
}
""".replace("%SKIPS%", ", ".join(f"'{s}'" for s in SKIP_SELETORES))


async def _estado_pagina(pg) -> dict | None:
    try:
        return await pg.evaluate(JS_ESTADO_VIDEO)
    except Exception:
        return None


async def _clicar_pular(pg) -> bool:
    for sel in SKIP_SELETORES:
        try:
            loc = pg.locator(sel).first
            if await loc.count() and await loc.is_visible():
                await loc.click(timeout=1500)
                return True
        except Exception:
            continue
    return False


async def _vigiar():
    """A cada segundo: pula anúncio quando o YouTube oferece o botão e avisa a tela quando começa/para a mídia."""
    global _midia_ativa
    while True:
        await asyncio.sleep(1.0)
        try:
            if _ctx is None:
                return
            tocando = False
            for pg in list(_ctx.pages):
                if pg.is_closed():
                    continue
                est = await _estado_pagina(pg)
                if not est or not est["tem_video"]:
                    continue
                if pular_anuncios_auto and est["anuncio"] and est["pode_pular"]:
                    await _clicar_pular(pg)
                if est["tocando"]:
                    tocando = True
            if tocando != _midia_ativa:
                _midia_ativa = tocando
                if ao_mudar_midia:
                    await ao_mudar_midia(tocando)
        except asyncio.CancelledError:
            raise
        except Exception:
            continue


# ================================================================== volume: abaixa quando o Jarvis fala

JS_VOLUME = r"""
(fator) => {
  const player = document.querySelector('#movie_player');
  const v = document.querySelector('video.html5-main-video') || document.querySelector('video');
  if (!v) return null;
  if (window.__jv_orig === undefined) window.__jv_orig = player && player.getVolume ? player.getVolume() : Math.round(v.volume * 100);
  const alvo = Math.max(0, Math.min(100, Math.round(window.__jv_orig * fator)));
  if (player && player.setVolume) player.setVolume(alvo); else v.volume = alvo / 100;
  if (fator >= 1) window.__jv_orig = undefined;
  return alvo;
}
"""


async def duck(fator: float, restaurar_em: float | None = None):
    """Abaixa (fator<1) ou restaura (1) o volume de todo vídeo tocando. Não faz nada se o navegador não está em uso."""
    global _restaurar_tarefa
    if not ativo():
        return
    if _restaurar_tarefa and not _restaurar_tarefa.done():
        _restaurar_tarefa.cancel()
    for pg in list(_ctx.pages):
        if pg.is_closed():
            continue
        try:
            await pg.evaluate(JS_VOLUME, fator)
        except Exception:
            pass
    if restaurar_em is not None and fator < 1:
        _restaurar_tarefa = asyncio.create_task(_restaurar_depois(restaurar_em))


async def _restaurar_depois(s: float):
    await asyncio.sleep(s)
    await duck(1.0)


# ================================================================== elementos da página (por número)

JS_ELEMENTOS = r"""
(deslocamento) => {
  // Numera os elementos acionáveis da página. Atravessa shadow DOM aberto; os iframes são percorridos pelo Python
  // (um quadro por vez, somando `deslocamento` para os números nunca se repetirem entre quadros).
  const raizes = [document];
  const coletar = (no) => { for (const el of no.querySelectorAll('*')) { if (el.shadowRoot) { raizes.push(el.shadowRoot); coletar(el.shadowRoot); } } };
  try { coletar(document); } catch (e) {}
  for (const r of raizes) r.querySelectorAll('[data-jarvis-id]').forEach((e) => e.removeAttribute('data-jarvis-id'));

  const sel = 'a[href], button, input:not([type=hidden]), textarea, select, summary, [onclick], ' +
    '[role=button], [role=link], [role=tab], [role=menuitem], [role=menuitemcheckbox], [role=menuitemradio], [role=checkbox], [role=radio], ' +
    '[role=option], [role=switch], [role=treeitem], [role=textbox], [role=searchbox], [role=combobox], [role=slider], ' +
    '[contenteditable=""], [contenteditable="true"], [contenteditable="plaintext-only"], [tabindex]:not([tabindex="-1"])';
  const vistos = new Set(), itens = [];
  const vh = window.innerHeight, vw = window.innerWidth;

  const texto = (el) => (el ? (el.innerText || el.textContent || '') : '').replace(/\s+/g, ' ').trim();
  const rotuloDe = (el) => {
    let r = el.getAttribute('aria-label') || '';
    if (!r) { const ids = (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
              r = ids.map((i) => texto(el.getRootNode().getElementById ? el.getRootNode().getElementById(i) : document.getElementById(i))).join(' ').trim(); }
    if (!r) r = el.innerText || '';
    if (!r) r = el.value || el.placeholder || el.title || el.alt || '';
    if (!r) r = el.getAttribute('name') || el.getAttribute('data-placeholder') || el.getAttribute('aria-placeholder') || '';
    if (!r) { const img = el.querySelector('img[alt]'); if (img) r = img.alt; }
    if (!r) { const sv = el.querySelector('svg title, svg desc'); if (sv) r = sv.textContent; }
    if (!r) r = el.getAttribute('data-testid') || el.getAttribute('data-test') || el.getAttribute('data-tooltip') || '';
    return r.replace(/\s+/g, ' ').trim().slice(0, 90);
  };
  const tipoDe = (el) => {
    const tag = el.tagName, role = (el.getAttribute('role') || '').toLowerCase();
    if (tag === 'A' || role === 'link') return 'link';
    if (tag === 'INPUT') return el.type === 'password' ? 'senha' : (el.type === 'checkbox' || el.type === 'radio' ? 'caixa' : (el.type === 'submit' || el.type === 'button' ? 'botão' : 'campo'));
    if (tag === 'TEXTAREA' || el.isContentEditable || role === 'textbox' || role === 'searchbox' || role === 'combobox') return 'campo';
    if (tag === 'SELECT') return 'lista';
    if (role === 'checkbox' || role === 'switch' || role === 'radio' || role === 'menuitemcheckbox' || role === 'menuitemradio') return 'caixa';
    return 'botão';
  };
  const visivel = (el, r) => {
    if (r.width < 4 || r.height < 4) return false;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') return false;
    if (r.bottom < 0 || r.top > vh * 1.6 || r.right < 0 || r.left > vw) return false;
    return true;
  };
  const adicionar = (el, forcarRotulo) => {
    if (itens.length >= 70) return false;
    const r = el.getBoundingClientRect();
    if (!visivel(el, r)) return false;
    const tipo = tipoDe(el);
    let rotulo = rotuloDe(el);
    if (!rotulo && tipo === 'campo') rotulo = '(campo de texto)';
    if (!rotulo) return false;
    const chave = tipo + '|' + rotulo + '|' + Math.round(r.top / 24) + '|' + Math.round(r.left / 40);
    if (vistos.has(chave)) return false;
    vistos.add(chave);
    const id = deslocamento + itens.length + 1;
    el.setAttribute('data-jarvis-id', String(id));
    let destino = '';
    try { if (el.href) { const u = new URL(el.href); destino = u.host.replace(/^www\./, '') + u.pathname.slice(0, 30); } } catch (e) {}
    let estado = '';
    if (el.checked === true || el.getAttribute('aria-checked') === 'true' || el.getAttribute('aria-pressed') === 'true') estado = 'marcado';
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') estado = (estado ? estado + ', ' : '') + 'desativado';
    if (tipo === 'campo' && !el.isContentEditable && el.value) estado = (estado ? estado + ', ' : '') + 'tem texto';
    itens.push({ id, tipo, rotulo, destino, estado, emTela: r.top >= 0 && r.bottom <= vh });
    return true;
  };

  for (const raiz of raizes) {
    for (const el of raiz.querySelectorAll(sel)) { if (itens.length >= 70) break; adicionar(el); }
  }
  // Sites com botões feitos de <div>/<span> clicáveis (sem papel nem onclick): só se a lista estiver magra.
  if (itens.length < 25) {
    for (const raiz of raizes) {
      for (const el of raiz.querySelectorAll('div, span, li, td, img, i')) {
        if (itens.length >= 45) break;
        if (el.closest && el.closest(sel)) continue;
        const r = el.getBoundingClientRect();
        if (r.width < 8 || r.height < 8 || r.width > vw * 0.9 || r.bottom < 0 || r.top > vh * 1.2) continue;
        if (getComputedStyle(el).cursor === 'pointer') adicionar(el);
      }
    }
  }
  return { itens, texto: (document.body ? document.body.innerText : '').replace(/\s+\n/g, '\n').slice(0, 1400) };
}
"""

RISCO_ACAO = re.compile(r"\b(comprar|compre|finalizar|pagar|pagamento|confirmar (pedido|compra|pagamento)|transferir|enviar dinheiro|"
                        r"assinar|contratar|excluir|apagar|deletar|remover|cancelar (assinatura|conta|pedido)|sair da conta|logout|"
                        r"publicar|postar|enviar mensagem|buy now|place order|pay|delete|remove|unsubscribe|checkout)\b", re.IGNORECASE)
PAGINA_SENSIVEL = re.compile(r"banco|bank|nubank|itau|itaú|bradesco|santander|caixa\.gov|bb\.com\.br|paypal|pagamento|checkout|"
                             r"pagar|cartao|cartão|carteira|wallet|binance|\bpix\b|gov\.br|senha|password|signin|login", re.IGNORECASE)


def _url_valida(url: str) -> str:
    url = url.strip()
    if re.match(r"^(javascript|data|file|chrome|about|blob|vbscript|view-source|mailto|tel|ftp):", url, re.IGNORECASE):
        raise ValueError("Só abro endereços http ou https.")
    if "://" not in url:
        url = "https://" + url
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise ValueError("Só abro endereços http ou https.")
    return url


async def _resumo(pg) -> str:
    try:
        titulo = await pg.title()
    except Exception:
        titulo = ""
    return f"{titulo} ({pg.url[:120]})"


JS_ASSENTAR = r"""
([quieto_ms, max_ms]) => new Promise((resolve) => {
  // Espera o DOM parar de ganhar/perder nós por `quieto_ms` (ou `max_ms` no máximo). Só childList: players e barras
  // de progresso mudam atributos o tempo todo e nunca "assentariam".
  let t = null; const inicio = performance.now();
  const fim = () => { obs.disconnect(); resolve(Math.round(performance.now() - inicio)); };
  const obs = new MutationObserver(() => { clearTimeout(t); t = setTimeout(fim, quieto_ms); });
  obs.observe(document.documentElement, { childList: true, subtree: true });
  t = setTimeout(fim, quieto_ms);
  setTimeout(fim, max_ms);
})
"""


async def _esperar_pagina(pg, ms=900):
    """Espera a página 'assentar': carregou o HTML e o DOM parou de mudar (SPAs), em vez de um tempo fixo às cegas."""
    try:
        await pg.wait_for_load_state("domcontentloaded", timeout=4000)
    except Exception:
        pass
    try:
        await pg.evaluate(JS_ASSENTAR, [450, max(1000, ms * 2)])
    except Exception:
        await asyncio.sleep(min(ms, 600) / 1000)        # página trocou no meio da espera: um respiro curto


# ------------------------------------------------------------------ elementos numerados (todos os quadros)

_ULTIMO: dict[int, tuple[str, str]] = {}        # número -> (tipo, rótulo) do último snapshot, para reencontrar após mudança

JS_LIMPAR = "() => document.querySelectorAll('[data-jarvis-id]').forEach((e) => e.removeAttribute('data-jarvis-id'))"


async def _snapshot(pg, max_itens: int = 80) -> dict:
    """Elementos acionáveis da página inteira: quadro principal + iframes (até 11), numerados sem repetição."""
    itens, texto = [], ""
    quadros = [pg.main_frame] + [f for f in pg.frames if f is not pg.main_frame][:11]
    for i, fr in enumerate(quadros):
        if len(itens) >= max_itens:                  # cheio: só limpa ids velhos nos quadros restantes (não colidir depois)
            try:
                await fr.evaluate(JS_LIMPAR)
            except Exception:
                pass
            continue
        try:
            d = await fr.evaluate(JS_ELEMENTOS, len(itens))
        except Exception:
            continue                                  # quadro sumiu ou navegou no meio: ignora
        if i == 0:
            texto = d["texto"]
        for it in d["itens"]:
            it["quadro"] = i
            itens.append(it)
    itens = itens[:max_itens]
    _ULTIMO.clear()
    _ULTIMO.update({it["id"]: (it["tipo"], it["rotulo"]) for it in itens})
    return {"itens": itens, "texto": texto}


def _linhas_elementos(itens: list[dict]) -> list[str]:
    return [f"[{i['id']}] {i['tipo']}: {i['rotulo']}" + (f"  → {i['destino']}" if i["destino"] else "")
            + (f"  ({i['estado']})" if i.get("estado") else "") + ("" if i["emTela"] else "  (abaixo/acima na página)")
            + ("  [em outro quadro]" if i.get("quadro") else "") for i in itens]


async def _ver_texto(pg, max_itens: int = 80, max_texto: int = 1400, limite: int = 9000) -> str:
    dados = await _snapshot(pg, max_itens)
    return (f"Página: {await _resumo(pg)}\n\nTexto:\n{dados['texto'][:max_texto]}\n\nElementos:\n"
            + "\n".join(_linhas_elementos(dados["itens"])))[:limite]


async def _localizar(pg, numero: int):
    """Locator do elemento numerado, em qualquer quadro; None se não existe mais."""
    for fr in [pg.main_frame] + [f for f in pg.frames if f is not pg.main_frame]:
        try:
            loc = fr.locator(f'[data-jarvis-id="{int(numero)}"]').first
            if await loc.count():
                return loc
        except Exception:
            continue
    return None


async def _resolver_numero(pg, numero: int):
    """Acha o elemento pelo número; se a página mudou e o número sumiu, relê a página e reencontra o MESMO tipo+rótulo."""
    loc = await _localizar(pg, numero)
    if loc is not None:
        return loc
    antes = _ULTIMO.get(int(numero))
    if antes:
        novo = await _snapshot(pg)
        for it in novo["itens"]:
            if (it["tipo"], it["rotulo"]) == antes:
                achado = await _localizar(pg, it["id"])
                if achado is not None:
                    return achado
    raise ValueError("Esse número não existe mais e não reencontrei o elemento. Chame navegador_ver de novo.")


async def _clicar_robusto(loc, pg):
    """Clique normal; se algo cobrir o elemento, força; por último dispara o clique pelo próprio elemento (JS)."""
    try:
        await loc.scroll_into_view_if_needed(timeout=3000)
    except Exception:
        pass
    try:
        await loc.click(timeout=5000)
        return
    except Exception as e1:
        primeiro = str(e1).splitlines()[0][:140]
    try:
        await loc.click(timeout=3000, force=True)
        return
    except Exception:
        pass
    try:
        await loc.evaluate("e => e.click()")
        return
    except Exception:
        raise ValueError(f"Não consegui clicar: {primeiro}")


async def _seguir_nova_aba(antes: int):
    """Se o clique abriu uma aba nova, passa a operar nela."""
    global _ativa
    abertas = [p for p in _ctx.pages if not p.is_closed()]
    if len(abertas) > antes:
        _ativa = abertas[-1]
        try:
            await _ativa.wait_for_load_state("domcontentloaded", timeout=4000)
        except Exception:
            pass


async def _cuidado(sessao, pg, descricao: str, rotulo: str = "") -> bool:
    """Confirmação extra em página sensível ou em ação de risco. False = o usuário negou."""
    if sessao is None:
        return True
    try:
        titulo = await pg.title()
    except Exception:
        titulo = ""
    motivos = []
    if PAGINA_SENSIVEL.search(f"{pg.url} {titulo}"):
        motivos.append(f"Página sensível: {titulo or pg.url[:60]}")
    if rotulo and RISCO_ACAO.search(rotulo):
        motivos.append(f"Ação de risco: \"{rotulo}\"")
    if not motivos:
        return True
    return await sessao.confirmar(f"Navegador: {descricao}", motivos + ["Pode envolver dinheiro, conta ou algo difícil de desfazer."])


# ================================================================== ferramentas

def _def(nome, descricao, props, req):
    return {"name": nome, "description": descricao, "input_schema": {"type": "object", "properties": props, "required": req}}


def definicoes() -> list[dict]:
    return [
        _def("youtube_buscar", "Busca no YouTube e TOCA (ou só lista) vídeos ou músicas. Já pula anúncios sozinho quando o YouTube oferece o botão Pular. Para música, busque o nome da música e do artista. Devolve o que está tocando e as outras opções.",
             {"consulta": {"type": "string"}, "posicao": {"type": "integer", "description": "Qual resultado tocar (1 = primeiro, padrão)."},
              "tipo": {"type": "string", "enum": ["video", "playlist"], "description": "'playlist' para tocar uma lista inteira (padrão: video)."},
              "somente_listar": {"type": "boolean", "description": "True para só listar os resultados sem tocar."},
              "mostrar": {"type": "boolean", "description": "True se o usuário quer ASSISTIR (traz o navegador para a frente). Para só ouvir música, deixe falso."}},
             ["consulta"]),
        _def("video_controle", "Controla o vídeo/música que está tocando no navegador do Jarvis. Ações: pausar, continuar, proximo (próxima faixa/vídeo), anterior, avancar e voltar (use 'valor' em segundos, padrão 10), ir_para (valor = segundo), volume (valor 0-100), mudo, velocidade (valor 0.25 a 2), tela_cheia, legendas, pular_anuncio, estado (o que está tocando agora).",
             {"acao": {"type": "string", "enum": ["pausar", "continuar", "proximo", "anterior", "avancar", "voltar", "ir_para", "volume", "mudo", "velocidade", "tela_cheia", "legendas", "pular_anuncio", "estado"]},
              "valor": {"type": "number"}}, ["acao"]),
        _def("navegador_abrir", "Abre um endereço no navegador do Jarvis (Chrome dedicado, com login salvo) e mostra a janela.",
             {"url": {"type": "string"}}, ["url"]),
        _def("navegador_ver", "Lista o que há na página atual do navegador do Jarvis: texto principal e os elementos clicáveis NUMERADOS (links, botões, campos). Use antes de navegador_clicar ou navegador_digitar; os números mudam a cada chamada.", {}, []),
        _def("navegador_clicar", "Clica num elemento da página: pelo número de navegador_ver (preferido) ou pelo texto visível.",
             {"numero": {"type": "integer"}, "texto": {"type": "string", "description": "Texto visível do botão/link, se não souber o número."}}, []),
        _def("navegador_digitar", "Escreve num campo da página (número de navegador_ver ou rótulo do campo). Nunca digita senhas.",
             {"numero": {"type": "integer"}, "campo": {"type": "string", "description": "Rótulo ou placeholder do campo."},
              "texto": {"type": "string"}, "enter": {"type": "boolean", "description": "Apertar Enter depois."}}, ["texto"]),
        _def("navegador_tecla", "Aperta uma tecla ou atalho na página atual (ex.: Enter, Escape, Space, ArrowRight, Control+F).", {"tecla": {"type": "string"}}, ["tecla"]),
        _def("navegador_rolar", "Rola a página. Positivo desce, negativo sobe (1 = uma tela).", {"telas": {"type": "number"}}, ["telas"]),
        _def("navegador_voltar", "Volta uma página no histórico do navegador do Jarvis.", {}, []),
        _def("navegador_abas", "Lista as abas abertas, ou troca para uma pelo trecho do título.", {"trocar_para": {"type": "string"}}, []),
        _def("navegador_janela", "Traz o navegador do Jarvis para a frente ou o minimiza (a música continua).",
             {"acao": {"type": "string", "enum": ["mostrar", "minimizar"]}}, ["acao"]),
    ]


ROTULOS = {"youtube_buscar": "YOUTUBE", "video_controle": "MÍDIA", **{n: "NAVEGADOR" for n in (
    "navegador_abrir", "navegador_ver", "navegador_clicar", "navegador_digitar", "navegador_tecla", "navegador_rolar",
    "navegador_voltar", "navegador_abas", "navegador_janela")}}
NOMES = set(ROTULOS)
PEDEM_CONFIRMACAO = {"navegador_clicar", "navegador_digitar", "navegador_tecla"}


def _texto(entrada: dict, campo: str) -> str:
    v = entrada.get(campo)
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"Faltou o campo '{campo}'.")
    return v.strip()


def _hms(s) -> str:
    if s is None:
        return "?"
    s = int(s)
    return f"{s // 60}:{s % 60:02d}"


async def executar(nome: str, entrada: dict, sessao, config: dict | None = None) -> str:
    if sessao is not None:
        n = getattr(sessao, "navegador_acoes", 0)
        if n >= LIMITE_ACOES:
            raise ValueError("Limite de ações no navegador neste pedido. Peça de novo se precisar continuar.")
        sessao.navegador_acoes = n + 1

    if nome == "youtube_buscar":
        return await _youtube_buscar(entrada)
    if nome == "video_controle":
        return await _video_controle(entrada)
    if nome == "navegador_janela":
        await mostrar_janela(_texto(entrada, "acao") == "mostrar")
        return "Janela do navegador " + ("à frente." if entrada["acao"] == "mostrar" else "minimizada (a música continua).")
    if nome == "navegador_abrir":
        pg = await pagina(mostrar=True)
        await pg.goto(_url_valida(_texto(entrada, "url")), wait_until="domcontentloaded", timeout=20000)
        await _esperar_pagina(pg, 600)
        # já devolve os elementos: poupa o navegador_ver (uma ida e volta ao modelo) logo depois de abrir
        return f"Aberto.\n\n{await _ver_texto(pg, 45, 600, 6000)}"
    if nome == "navegador_ver":
        pg = await pagina()
        await _esperar_pagina(pg, 300)
        return await _ver_texto(pg)
    if nome == "navegador_clicar":
        return await _clicar(entrada, sessao)
    if nome == "navegador_digitar":
        return await _digitar(entrada, sessao)
    if nome == "navegador_tecla":
        pg = await pagina()
        tecla = _texto(entrada, "tecla")
        if not await _cuidado(sessao, pg, f"apertar {tecla}"):
            return "O usuário negou esta ação."
        aliases = {"espaço": "Space", "espaco": "Space", "esc": "Escape", "enter": "Enter", "baixo": "ArrowDown", "cima": "ArrowUp",
                   "direita": "ArrowRight", "esquerda": "ArrowLeft"}
        await pg.keyboard.press(aliases.get(tecla.lower(), tecla))
        await asyncio.sleep(0.4)
        return f"Tecla {tecla} apertada."
    if nome == "navegador_rolar":
        pg = await pagina()
        telas = max(-10, min(10, float(entrada.get("telas") or 1)))
        await pg.evaluate("(t) => window.scrollBy({top: window.innerHeight * 0.85 * t, behavior: 'instant'})", telas)
        await asyncio.sleep(0.3)
        return "Rolado."
    if nome == "navegador_voltar":
        pg = await pagina()
        antes = pg.url
        await pg.evaluate("() => history.back()")      # go_back() trava quando o Chrome restaura a página do cache
        for _ in range(24):
            await asyncio.sleep(0.25)
            if pg.url != antes:
                break
        await _esperar_pagina(pg, 400)
        return (f"Voltei: {await _resumo(pg)}" if pg.url != antes else "Não há página anterior no histórico.")
    if nome == "navegador_abas":
        global _ativa
        ctx = await contexto()
        abertas = [p for p in ctx.pages if not p.is_closed()]
        trocar = (entrada.get("trocar_para") or "").strip().lower()
        if trocar:
            for p in abertas:
                if trocar in (await p.title()).lower() or trocar in p.url.lower():
                    _ativa = p
                    await p.bring_to_front()
                    return f"Agora na aba: {await _resumo(p)}"
            raise ValueError(f"Nenhuma aba com '{trocar}'.")
        linhas = []
        for i, p in enumerate(abertas):
            linhas.append(f"{i + 1}. {await _resumo(p)}" + ("  ← atual" if p is _ativa else ""))
        return "\n".join(linhas) or "Nenhuma aba."
    raise ValueError(f"Ferramenta desconhecida: {nome}")


async def _clicar(entrada: dict, sessao) -> str:
    pg = await pagina()
    ctx = await contexto()
    antes = len([p for p in ctx.pages if not p.is_closed()])
    numero, texto = entrada.get("numero"), (entrada.get("texto") or "").strip()
    url_antes = pg.url
    if numero:
        loc = await _resolver_numero(pg, numero)
    elif texto:
        padrao = re.compile(re.escape(texto), re.IGNORECASE)
        loc = None
        for candidato in (pg.get_by_role("button", name=padrao), pg.get_by_role("link", name=padrao), pg.get_by_text(padrao)):
            for i in range(min(await candidato.count(), 6)):
                if await candidato.nth(i).is_visible():
                    loc = candidato.nth(i)
                    break
            if loc is not None:
                break
        if loc is None:
            raise ValueError(f"Não achei nada clicável com '{texto}'. Use navegador_ver para ver as opções.")
    else:
        raise ValueError("Informe o número (de navegador_ver) ou o texto do elemento.")
    rotulo = (await loc.evaluate("e => (e.getAttribute('aria-label') || e.innerText || e.value || e.title || '').replace(/\\s+/g,' ').trim().slice(0,90)")) or ""
    if not await _cuidado(sessao, pg, f"clicar em \"{rotulo or texto}\"", rotulo):
        return "O usuário negou este clique."
    await _clicar_robusto(loc, pg)
    await _esperar_pagina(pg)
    await _seguir_nova_aba(antes)
    destino = _ativa or pg
    # devolve a página já relida (o próximo passo quase sempre é olhar o resultado): poupa uma ida e volta ao modelo
    try:
        ver = await _ver_texto(destino, 40, 500, 5000)
    except Exception:
        ver = f"Agora: {await _resumo(destino)}"
    return f"Cliquei em \"{rotulo or texto}\".\n\n{ver}"


async def _digitar(entrada: dict, sessao) -> str:
    pg = await pagina()
    texto = entrada.get("texto")
    if not isinstance(texto, str) or not texto:
        raise ValueError("Faltou o campo 'texto'.")
    numero, campo = entrada.get("numero"), (entrada.get("campo") or "").strip()
    if numero:
        loc = await _resolver_numero(pg, numero)
    elif campo:
        padrao = re.compile(re.escape(campo), re.IGNORECASE)
        loc = pg.get_by_placeholder(padrao).first
        if not await loc.count():
            loc = pg.get_by_label(padrao).first
        if not await loc.count():
            loc = pg.get_by_role("textbox", name=padrao).first
    else:
        loc = pg.locator("input:focus, textarea:focus").first
    if not await loc.count():
        raise ValueError("Não achei esse campo. Use navegador_ver para ver os campos numerados.")
    tipo = await loc.evaluate("e => ((e.type || '') + '|' + (e.autocomplete || '') + '|' + (e.name || '')).toLowerCase()")
    if "password" in tipo or "senha" in tipo:
        raise ValueError("Não digito senhas. Peça para o usuário preencher esse campo.")
    if not await _cuidado(sessao, pg, f"digitar \"{texto[:40]}\""):
        return "O usuário negou esta digitação."
    try:
        await loc.fill(texto[:2000], timeout=5000)
    except Exception:
        # editor feito de <div> sem contenteditable "de verdade" (alguns chats): clica e insere o texto
        try:
            await loc.click(timeout=3000)
            if len(texto) <= 300:
                await pg.keyboard.type(texto, delay=4)      # eventos de tecla reais: editores de chat reagem a eles
            else:
                await pg.keyboard.insert_text(texto[:2000])
        except Exception as e:
            raise ValueError(f"Não consegui escrever nesse campo: {str(e).splitlines()[0][:140]}")
    if entrada.get("enter"):
        await loc.press("Enter")
        await _esperar_pagina(pg)
        try:
            return f"Digitei e apertei Enter.\n\n{await _ver_texto(_ativa or pg, 40, 500, 5000)}"
        except Exception:
            return f"Digitei e apertei Enter. Agora: {await _resumo(pg)}"
    return f"Digitei no campo. Agora: {await _resumo(pg)}"


# ------------------------------------------------------------------ YouTube e vídeo

JS_RESULTADOS = r"""
() => [...document.querySelectorAll('ytd-video-renderer')].slice(0, 8).map((r) => {
  const t = r.querySelector('a#video-title');
  return {
    titulo: (t && (t.getAttribute('title') || t.innerText) || '').trim(),
    href: t ? t.href : '',
    canal: ((r.querySelector('ytd-channel-name a') || {}).innerText || '').trim(),
    duracao: ((r.querySelector('ytd-thumbnail-overlay-time-status-renderer') || {}).innerText || '').replace(/\s+/g, ' ').trim(),
  };
}).filter((x) => x.href)
"""

JS_PLAYLISTS = r"""
() => [...document.querySelectorAll('yt-lockup-view-model, ytd-playlist-renderer')].slice(0, 6).map((r) => {
  const a = r.querySelector('a[href*="list="]');
  return { titulo: ((r.querySelector('h3, #video-title, a#video-title') || a || {}).innerText || '').replace(/\s+/g, ' ').trim().slice(0, 100),
           href: a ? a.href : '', canal: '', duracao: '' };
}).filter((x) => x.href)
"""


async def _consentimento(pg):
    """Se aparecer o aviso de cookies do Google, escolhe 'Rejeitar tudo' (mais privado)."""
    try:
        if "consent." in pg.url:
            for nome in ("Rejeitar tudo", "Reject all"):
                b = pg.get_by_role("button", name=re.compile(nome, re.I)).first
                if await b.count():
                    await b.click(timeout=3000)
                    await _esperar_pagina(pg, 800)
                    return
    except Exception:
        pass


async def _youtube_buscar(entrada: dict) -> str:
    consulta = _texto(entrada, "consulta")
    tipo = entrada.get("tipo") or "video"
    posicao = max(1, int(entrada.get("posicao") or 1))
    pg = await pagina(mostrar=bool(entrada.get("mostrar")))
    filtro = "EgIQAw%3D%3D" if tipo == "playlist" else "EgIQAQ%3D%3D"
    await pg.goto(f"https://www.youtube.com/results?search_query={quote_plus(consulta)}&sp={filtro}", wait_until="domcontentloaded", timeout=25000)
    await _consentimento(pg)
    seletor = "yt-lockup-view-model, ytd-playlist-renderer" if tipo == "playlist" else "ytd-video-renderer"
    try:
        await pg.wait_for_selector(seletor, timeout=12000)
    except Exception:
        raise ValueError("O YouTube não mostrou resultados (sem internet ou a página mudou).")
    resultados = await pg.evaluate(JS_PLAYLISTS if tipo == "playlist" else JS_RESULTADOS)
    if not resultados:
        raise ValueError("Não achei resultados para essa busca.")
    lista = "\n".join(f"{i + 1}. {r['titulo']}" + (f" — {r['canal']}" if r["canal"] else "") + (f" ({r['duracao']})" if r["duracao"] else "")
                      for i, r in enumerate(resultados))
    if entrada.get("somente_listar"):
        return f"Resultados para '{consulta}':\n{lista}"
    if posicao > len(resultados):
        raise ValueError(f"Só há {len(resultados)} resultados.")
    escolhido = resultados[posicao - 1]
    await pg.goto(escolhido["href"], wait_until="domcontentloaded", timeout=25000)
    if tipo == "playlist":
        for rotulo in ("Reproduzir tudo", "Play all", "Reproduzir"):
            b = pg.get_by_role("button", name=re.compile(rotulo, re.I)).first
            if await b.count():
                try:
                    await b.click(timeout=3000)
                    break
                except Exception:
                    pass
    try:
        await pg.wait_for_selector("video", timeout=12000)
    except Exception:
        raise ValueError("A página abriu mas o player não apareceu.")
    await asyncio.sleep(1.5)
    await pg.evaluate("() => { const v = document.querySelector('video'); if (v && v.paused) v.play().catch(() => {}); }")
    await asyncio.sleep(0.8)
    if pular_anuncios_auto:
        await _clicar_pular(pg)
    est = await _estado_pagina(pg) or {}
    resto = "\n".join(l for l in lista.split("\n") if not l.startswith(f"{posicao}."))
    if est.get("tocando") and not est.get("anuncio"):
        abertura = "Tocando"
    elif est.get("anuncio"):
        abertura = "Começando (passa um anúncio antes; pulo assim que o YouTube liberar o botão Pular)"
    else:
        abertura = "Carregando"
    return (f"{abertura}: {escolhido['titulo']}" + (f" — {escolhido['canal']}" if escolhido["canal"] else "")
            + (f" ({escolhido['duracao']})" if escolhido["duracao"] else "") + f"\nOutras opções:\n{resto}")


async def _video_controle(entrada: dict) -> str:
    acao = _texto(entrada, "acao")
    valor = entrada.get("valor")
    pg = await pagina()
    est = await _estado_pagina(pg)
    if not est or not est["tem_video"]:
        raise ValueError("Não há vídeo nem música tocando no navegador do Jarvis.")

    async def js(codigo, arg=None):
        return await pg.evaluate(codigo, arg)

    if acao == "estado":
        quem = est["titulo"] + (f" — {est['canal']}" if est["canal"] else "")
        return (f"{quem}. {'Tocando' if est['tocando'] else 'Pausado'}, {_hms(est['tempo'])} de {_hms(est['duracao'])}, "
                f"volume {est['volume']}%{' (mudo)' if est['mudo'] else ''}." + (" Está passando um anúncio." if est["anuncio"] else ""))
    if acao == "pular_anuncio":
        if not est["anuncio"]:
            return "Não há anúncio passando agora."
        if await _clicar_pular(pg):
            return "Anúncio pulado."
        faltam = (est["duracao"] or 0) - (est["tempo"] or 0)
        return f"O anúncio ainda não tem o botão Pular (ou não é pulável). Faltam cerca de {max(0, faltam)} segundos; a minha tentativa automática pula assim que o botão aparecer."
    if acao == "pausar":
        await js("() => document.querySelector('video').pause()")
        return "Pausado."
    if acao == "continuar":
        await js("() => document.querySelector('video').play()")
        return "Tocando."
    if acao in ("avancar", "voltar"):
        s = float(valor or 10) * (1 if acao == "avancar" else -1)
        await js("(s) => { const v = document.querySelector('video'); v.currentTime = Math.max(0, v.currentTime + s); }", s)
        return f"{'Avancei' if s > 0 else 'Voltei'} {abs(int(s))} segundos."
    if acao == "ir_para":
        await js("(s) => { document.querySelector('video').currentTime = s; }", float(valor or 0))
        return f"No segundo {int(valor or 0)}."
    if acao == "volume":
        v = max(0, min(100, int(valor if valor is not None else 50)))
        await js("""(v) => { const p = document.querySelector('#movie_player'); const el = document.querySelector('video');
                    if (p && p.setVolume) { p.unMute && p.unMute(); p.setVolume(v); } else { el.muted = false; el.volume = v / 100; }
                    window.__jv_orig = undefined; }""", v)
        return f"Volume em {v}%."
    if acao == "mudo":
        await js("() => { const p = document.querySelector('#movie_player'); const v = document.querySelector('video'); "
                 "if (p && p.isMuted) { p.isMuted() ? p.unMute() : p.mute(); } else { v.muted = !v.muted; } }")
        return "Alternei o mudo."
    if acao == "velocidade":
        r = max(0.25, min(2.0, float(valor or 1)))
        await js("(r) => { document.querySelector('video').playbackRate = r; }", r)
        return f"Velocidade {r}x."
    if acao == "tela_cheia":
        await pg.keyboard.press("f")
        return "Alternei a tela cheia."
    if acao == "legendas":
        await pg.keyboard.press("c")
        return "Alternei as legendas."
    if acao in ("proximo", "anterior"):
        if acao == "proximo":
            btn = pg.locator(".ytp-next-button").first
            if await btn.count() and await btn.is_visible():
                await btn.click(timeout=3000)
            else:
                await pg.keyboard.press("Shift+N")
        else:
            btn = pg.locator(".ytp-prev-button").first
            if await btn.count() and await btn.is_visible():
                await btn.click(timeout=3000)
            else:
                await pg.keyboard.press("Shift+P")
        await asyncio.sleep(2.0)
        novo = await _estado_pagina(pg) or {}
        mudou = novo.get("titulo") and novo.get("titulo") != est["titulo"]
        return (f"Agora: {novo.get('titulo')}" if mudou else
                "Mandei o comando, mas o título não mudou: talvez não haja próximo/anterior nesta reprodução. "
                "Posso buscar outra música no YouTube.")
    raise ValueError("Ação de vídeo desconhecida.")
