// Animações das AÇÕES do Jarvis (câmera, abrir/fechar programas, controle do PC, arquivos, pesquisas) e dinâmica dos painéis laterais
// (foco contextual, parallax com mola, arrastar com inércia). Só desenha por cima; não decide nada nem mexe no servidor.
(function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    const camada = document.createElement('div');
    camada.id = 'acoes';
    const chips = document.createElement('div');
    chips.id = 'ac-chips';
    camada.appendChild(chips);
    const montar = () => { if (!camada.isConnected) document.body.appendChild(camada); };
    if (document.body) montar(); else document.addEventListener('DOMContentLoaded', montar);

    const reduzido = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const sumir = (el, ms) => setTimeout(() => el.remove(), ms);

    function centroReator() {
        const el = document.querySelector('.reator-caixa');
        const r = el ? el.getBoundingClientRect() : { left: innerWidth / 2 - 100, top: innerHeight / 2 - 100, width: 200, height: 200 };
        return { x: r.left + r.width / 2, y: r.top + r.height / 2, r: Math.min(r.width, r.height) / 2 };
    }

    // ---------------------------------------------------------------- onda do reator (3D se houver, senão um anel CSS)
    function onda(forca = 1) {
        if (window.Cena3D && window.Cena3D.pulso) { window.Cena3D.pulso(forca); return; }       // com a cena 3D, a onda é desenhada nela
        const c = centroReator();
        const a = document.createElement('div');
        a.className = 'ac-anel';
        a.style.cssText = `left:${c.x}px;top:${c.y}px;width:${c.r * 2}px;height:${c.r * 2}px`;
        camada.appendChild(a);
        sumir(a, 1500);
    }

    // ---------------------------------------------------------------- cartão de programa: abre (cresce do reator) / fecha (some nele)
    function cartao(tipo, nome) {
        const c = centroReator();
        const w = Math.min(innerWidth * 0.3, 400), h = w * 0.62;
        const el = document.createElement('div');
        el.className = 'ac-cartao ' + tipo;
        el.style.cssText = `left:${c.x}px;top:${c.y}px;width:${w}px;height:${h}px`;
        const rot = tipo === 'abrir' ? 'ABRINDO' : tipo === 'fechar' ? 'ENCERRANDO' : 'JANELA';
        el.innerHTML = `<div class="ac-barra"><i></i><i></i><i></i><span></span></div><div class="ac-corpo"><b>${rot}</b><span class="ac-nome"></span><div class="ac-prog"><u></u></div></div><em class="tl"></em><em class="tr"></em><em class="bl"></em><em class="br"></em>`;
        el.querySelector('.ac-barra span').textContent = nome || 'programa';
        el.querySelector('.ac-nome').textContent = (nome || '').toUpperCase().slice(0, 40);
        camada.appendChild(el);
        onda(tipo === 'fechar' ? 0.6 : 1);
        sumir(el, 2400);
        return el;
    }

    // ---------------------------------------------------------------- mira de controle (mouse/teclado/cliques): linhas varrem até o alvo
    function mira(texto) {
        const c = centroReator();
        const el = document.createElement('div');
        el.className = 'ac-mira';
        el.style.cssText = `left:${c.x}px;top:${c.y}px`;
        el.innerHTML = '<i class="h"></i><i class="v"></i><b></b><span></span>';
        el.querySelector('span').textContent = (texto || 'ALVO TRAVADO').toUpperCase().slice(0, 36);
        camada.appendChild(el);
        sumir(el, 1500);
    }

    // ---------------------------------------------------------------- etiquetas de ação (uma por ferramenta em andamento)
    const GLIFOS = { 'CÂMERA': '◉', PROGRAMA: '▣', WINDOWS: '▤', CONTROLE: '✛', ARQUIVOS: '▦', PESQUISA: '⌕', LEITURA: '≣', ABRINDO: '↗', NAVEGADOR: '◈',
        YOUTUBE: '▶', GESTO: '✋', 'MÍDIA': '♫', AGENDA: '◷', 'E-MAIL': '✉', GOOGLE: '◷', COFRE: '❖', OBSIDIAN: '❖', 'MEMÓRIA': '❖', 'VISÃO': '◎', 'NOTÍCIAS': '≡', INTERFACE: '◇' };
    const vivas = new Map();
    function etiqueta(msg) {
        if (msg.estado === 'inicio') {
            const el = document.createElement('div');
            el.className = 'ac-chip';
            el.innerHTML = '<s></s><b></b><span></span><u></u>';
            el.querySelector('s').textContent = GLIFOS[msg.rotulo] || '◆';
            el.querySelector('b').textContent = msg.rotulo || 'AÇÃO';
            el.querySelector('span').textContent = (msg.detalhe || '').slice(0, 56);
            chips.appendChild(el);
            while (chips.children.length > 3) chips.firstChild.remove();
            vivas.set(msg.id, el);
            setTimeout(() => { if (vivas.get(msg.id) === el) { vivas.delete(msg.id); el.classList.add('sai'); sumir(el, 600); } }, 25000);     // ferramenta que nunca avisou o fim
        } else {
            const el = vivas.get(msg.id);
            if (!el) return;
            el.classList.add(msg.estado === 'erro' ? 'erro' : 'ok');
            vivas.delete(msg.id);
            setTimeout(() => el.classList.add('sai'), 1100);
            sumir(el, 1700);
        }
    }

    // ---------------------------------------------------------------- roteia o evento da ferramenta para a animação certa
    function evento(msg) {
        if (reduzido || !msg) return;
        montar();
        etiqueta(msg);
        if (msg.estado !== 'inicio') { if (msg.estado === 'erro') onda(0.4); return; }
        const rot = msg.rotulo || '', det = (msg.detalhe || '');
        if (rot === 'PROGRAMA') cartao('abrir', det);
        else if (rot === 'WINDOWS' && /fech/i.test(det)) cartao('fechar', det.replace(/fechar/i, '').trim() || 'janela');
        else if (rot === 'WINDOWS' && /minimiz|maximiz|restaur|focar/i.test(det)) { cartao('janela', det); }
        else if (rot === 'CONTROLE') { mira(det); onda(0.5); }
        else if (rot === 'CÂMERA') { /* a câmera tem a própria animação (mira da câmera) */ }
        else onda(0.7);
        const alvo = { ARQUIVOS: 'sistema', PESQUISA: 'rede', LEITURA: 'rede', ABRINDO: 'rede', NAVEGADOR: 'rede', YOUTUBE: 'rede' }[rot];
        if (alvo) foco([alvo], 3.5);
    }

    // ---------------------------------------------------------------- câmera: mira em cima da prévia, disparo e a foto voando para o painel de atividade
    let miraCam = null;
    function cameraAbrir() {
        const pip = $('camera-pip');
        if (!pip || reduzido) return;
        cameraFechar();
        onda(0.9);
        pip.classList.add('ac-entrando');
        setTimeout(() => pip.classList.remove('ac-entrando'), 900);
        const r = { left: pip.offsetLeft, top: pip.offsetTop, width: pip.offsetWidth, height: pip.offsetHeight };      // o layout, sem a animação de entrada
        miraCam = document.createElement('div');
        miraCam.className = 'ac-miracam';
        miraCam.style.cssText = `left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px`;
        miraCam.innerHTML = '<em class="tl"></em><em class="tr"></em><em class="bl"></em><em class="br"></em><i class="scan"></i><b class="cruz"></b><span>ANALISANDO ENQUADRAMENTO</span>';
        montar();
        camada.appendChild(miraCam);
    }
    function cameraDisparo(tela) {
        if (reduzido) return;
        if (miraCam) { miraCam.classList.add('trava'); miraCam.querySelector('span').textContent = 'IMAGEM CAPTURADA'; }
        onda(1.3);
        try {
            const pe = $('camera-pip');
            const pip = { left: pe.offsetLeft, top: pe.offsetTop, width: pe.offsetWidth, height: pe.offsetHeight };
            const alvo = ($('p-atividade') || $('p-nucleo') || document.body).getBoundingClientRect();
            const img = document.createElement('img');
            img.className = 'ac-foto';
            img.src = tela.toDataURL('image/jpeg', 0.5);
            img.style.cssText = `left:${pip.left}px;top:${pip.top}px;width:${pip.width}px;height:${pip.height}px;--dx:${alvo.left + alvo.width / 2 - (pip.left + pip.width / 2)}px;--dy:${alvo.top + alvo.height / 2 - (pip.top + pip.height / 2)}px`;
            camada.appendChild(img);
            sumir(img, 1600);
            foco(['atividade'], 3);
        } catch (_) { /* a animação é enfeite: nunca atrapalha a foto */ }
    }
    function cameraFechar() { if (miraCam) { const m = miraCam; miraCam = null; m.classList.add('sai'); sumir(m, 500); } }
    new MutationObserver(() => { const p = $('camera-pip'); if (p && p.hidden) cameraFechar(); })
        .observe(document.documentElement, { attributes: true, subtree: true, attributeFilter: ['hidden'] });

    // ---------------------------------------------------------------- painéis: foco contextual
    function foco(ids, seg) {
        const col = document.querySelectorAll('.coluna');
        const alvos = [];
        for (const id of ids) document.querySelectorAll(`.painel[data-painel="${id}"]`).forEach((p) => alvos.push(p));
        if (!alvos.length) return;
        col.forEach((c) => c.classList.add('tem-foco'));
        alvos.forEach((p) => { p.classList.add('em-foco'); clearTimeout(p._focoT); p._focoT = setTimeout(() => {
            p.classList.remove('em-foco');
            if (!document.querySelector('.painel.em-foco')) col.forEach((c) => c.classList.remove('tem-foco'));
        }, seg * 1000); });
    }

    // ---------------------------------------------------------------- painéis: parallax com mola (cada um com sua "massa") e arrastar com inércia
    const POS = (() => { try { return JSON.parse(localStorage.getItem('jarvis_painel_pos') || '{}'); } catch (_) { return {}; } })();
    const salvar = () => { try { localStorage.setItem('jarvis_painel_pos', JSON.stringify(POS)); } catch (_) {} };
    const painel = new Map();                               // el -> estado físico
    let mx = 0, my = 0, rodandoFisica = false;
    addEventListener('pointermove', (e) => { mx = e.clientX / innerWidth - 0.5; my = e.clientY / innerHeight - 0.5; acordar(); }, { passive: true });

    function registrar(el) {
        const id = el.id || el.dataset.painel;
        const p = painel.get(el) || { el, id, px: 0, py: 0, dx: (POS[id] || [0, 0])[0], dy: (POS[id] || [0, 0])[1], vx: 0, vy: 0, arrasta: false,
            massa: 0.7 + (parseFloat(getComputedStyle(el).getPropertyValue('--i')) || 0) * 0.12 };
        painel.set(el, p);
        return p;
    }
    function acordar() { if (!rodandoFisica) { rodandoFisica = true; requestAnimationFrame(fisica); } }

    function fisica() {
        let ativo = false;
        for (const p of painel.values()) {
            if (!p.arrasta) {                               // inércia depois de soltar
                if (Math.abs(p.vx) > 0.05 || Math.abs(p.vy) > 0.05) {
                    p.dx += p.vx; p.dy += p.vy; p.vx *= 0.9; p.vy *= 0.9; ativo = true;
                    limitar(p);
                    if (Math.abs(p.vx) <= 0.05 && Math.abs(p.vy) <= 0.05) { POS[p.id] = [Math.round(p.dx), Math.round(p.dy)]; salvar(); }
                }
            }
            const alvoX = mx * 16 / p.massa, alvoY = my * 10 / p.massa;     // painéis mais "leves" andam mais: sensação de profundidade
            p.px += (alvoX - p.px) * 0.09; p.py += (alvoY - p.py) * 0.09;
            if (Math.abs(alvoX - p.px) > 0.05 || Math.abs(alvoY - p.py) > 0.05) ativo = true;
            p.el.style.setProperty('--px', p.px.toFixed(2)); p.el.style.setProperty('--py', p.py.toFixed(2));
            p.el.style.setProperty('--dx', p.dx.toFixed(1)); p.el.style.setProperty('--dy', p.dy.toFixed(1));
            if (p.arrasta) ativo = true;
        }
        if (ativo) requestAnimationFrame(fisica); else rodandoFisica = false;
    }

    function limitar(p) {                                   // não deixa o painel sair da tela
        const r = p.el.getBoundingClientRect();
        const folgaX = (r.left < 8 ? 8 - r.left : r.right > innerWidth - 8 ? innerWidth - 8 - r.right : 0);
        const folgaY = (r.top < 8 ? 8 - r.top : r.bottom > innerHeight - 8 ? innerHeight - 8 - r.bottom : 0);
        if (folgaX) { p.dx += folgaX; p.vx = 0; }
        if (folgaY) { p.dy += folgaY; p.vy = 0; }
    }

    // Arrastar pelo cabeçalho. O alvo do evento num painel 3D inclinado nem sempre é o <h2> (o navegador acerta o contêiner), então
    // a decisão é por GEOMETRIA: o ponteiro está dentro do retângulo do cabeçalho de algum painel?
    function arrastavel(el) {
        const topo = el.querySelector('h2');
        if (!topo) return;
        const p = registrar(el);
        p.topo = topo;
        topo.classList.add('ac-alca');
        topo.title = 'arraste para mover · duplo clique volta ao lugar';
    }

    function painelDoCabecalho(x, y) {
        for (const p of painel.values()) {
            if (!p.topo || !p.el.isConnected) continue;
            const r = p.topo.getBoundingClientRect();
            if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return p;
        }
        return null;
    }

    function voltarAoLugar(p) {
        p.dx = p.dy = p.vx = p.vy = 0; delete POS[p.id]; salvar();
        p.el.classList.add('voltando'); setTimeout(() => p.el.classList.remove('voltando'), 600); acordar();
    }

    addEventListener('pointerdown', (e) => {
        if (e.button !== 0 || e.target.closest && e.target.closest('a, button, input')) return;
        const p = painelDoCabecalho(e.clientX, e.clientY);
        if (!p) return;
        e.preventDefault();
        p.arrasta = true; p.vx = p.vy = 0;
        p.el.classList.add('arrastando');
        let ux = e.clientX, uy = e.clientY, t = performance.now();
        const mover = (ev) => {
            const agora = performance.now(), dt = Math.max(8, agora - t);
            const ddx = ev.clientX - ux, ddy = ev.clientY - uy;
            p.dx += ddx; p.dy += ddy; p.vx = ddx * 16 / dt; p.vy = ddy * 16 / dt;      // velocidade em px por quadro
            ux = ev.clientX; uy = ev.clientY; t = agora;
            acordar();
        };
        const soltar = () => {
            removeEventListener('pointermove', mover); removeEventListener('pointerup', soltar); removeEventListener('pointercancel', soltar);
            p.arrasta = false; p.el.classList.remove('arrastando');
            if (performance.now() - t > 90) { p.vx = p.vy = 0; }       // parou antes de soltar: sem arremesso
            limitar(p); POS[p.id] = [Math.round(p.dx), Math.round(p.dy)]; salvar(); acordar();
        };
        addEventListener('pointermove', mover); addEventListener('pointerup', soltar); addEventListener('pointercancel', soltar);
    }, true);
    addEventListener('dblclick', (e) => { const p = painelDoCabecalho(e.clientX, e.clientY); if (p) voltarAoLugar(p); }, true);

    function iniciarPaineis() {
        document.querySelectorAll('.painel').forEach((el) => {
            registrar(el); arrastavel(el);
            el.addEventListener('animationend', (e) => { if (e.target === el) el.classList.add('entrou'); });      // terminou a entrada: libera opacidade/filtro para o foco
        });
        acordar();
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciarPaineis); else iniciarPaineis();

    window.Acoes = { evento, onda, foco, cameraAbrir, cameraDisparo, cameraFechar, cartao, mira };
})();
