// Regras dos gestos: matemática pura sobre os pontos que o modelo local da mão/rosto devolve (nada de rede, nada de IA generativa).
// Testável em Node (scripts\teste_gestos.js). Convenção: coordenadas normalizadas 0..1 da imagem ESPELHADA (como a prévia), y para baixo.
(function (raiz, fabrica) {
    if (typeof module === 'object' && module.exports) module.exports = fabrica();
    else raiz.GestosRegras = fabrica();
})(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    const LIM = {
        pinca_fecha: 0.22, pinca_abre: 0.35,         // distância polegar-indicador / tamanho da mão (histerese)
        pinca_estavel_ms: 90,
        deslizar_vel: 1.25,                          // larguras de mão por 250 ms
        deslizar_pausa_ms: 800,
        palma_ms: 650, punho_ms: 650, parada_vel: 0.5,
        cabeca_pitch: 0.032, cabeca_yaw: 0.065, cabeca_janela_ms: 1500, cabeca_movimentos: 4, cabeca_pausa_ms: 1800,
    };

    const dist = (a, b, asp = 1) => Math.hypot((a.x - b.x) * asp, a.y - b.y);

    function tamanhoMao(p, asp) { return dist(p[0], p[9], asp) || 1e-6; }

    function dedosEstendidos(p, asp) {
        const ext = (ponta, junta) => dist(p[ponta], p[0], asp) > dist(p[junta], p[0], asp) * 1.08;
        const dedos = [ext(8, 6), ext(12, 10), ext(16, 14), ext(20, 18)];
        const polegar = dist(p[4], p[17], asp) > dist(p[3], p[17], asp) * 1.02;
        return { dedos, polegar, n: dedos.filter(Boolean).length };
    }

    const centroPalma = (p) => ({ x: (p[0].x + p[5].x + p[9].x + p[13].x + p[17].x) / 5, y: (p[0].y + p[5].y + p[9].y + p[13].y + p[17].y) / 5 });

    // ------------------------------------------------------------------ mão
    function criarMao(opcoes = {}) {
        const lim = { ...LIM, ...opcoes };
        let fechada = false, fechouEm = 0, pincaDisparada = false;
        let abertaDesde = 0, punhoDesde = 0, palmaDisparada = false, punhoDisparado = false, ultimoDeslizar = -1e9;
        const hist = [];

        return {
            reiniciar() { fechada = false; pincaDisparada = false; abertaDesde = punhoDesde = 0; palmaDisparada = punhoDisparado = false; hist.length = 0; },
            atualizar(p, t, asp = 16 / 9) {
                const ev = [];
                if (!p || p.length < 21) { this.reiniciar(); return ev; }
                const tam = tamanhoMao(p, asp);
                const c = centroPalma(p);
                hist.push({ t, x: c.x * asp, y: c.y });
                while (hist.length && t - hist[0].t > 400) hist.shift();
                const { dedos, polegar, n } = dedosEstendidos(p, asp);

                // velocidade em larguras de mão por 250 ms
                let vx = 0, vy = 0;
                const ref = hist.find((h) => t - h.t <= 250);
                if (ref && t - ref.t >= 60) { const k = 250 / (t - ref.t); vx = (c.x * asp - ref.x) / tam * k; vy = (c.y - ref.y) / tam * k; }
                const vel = Math.hypot(vx, vy);

                // pinça (com histerese e estabilidade): só vale com os outros dedos soltos (não confundir com punho)
                const razao = dist(p[4], p[8], asp) / tam;
                if (!fechada && razao < lim.pinca_fecha && n >= 1) { fechada = true; fechouEm = t; pincaDisparada = false; }
                else if (fechada && razao > lim.pinca_abre) { fechada = false; if (pincaDisparada) ev.push({ tipo: 'pinca_fim' }); pincaDisparada = false; }
                if (fechada && !pincaDisparada && t - fechouEm >= lim.pinca_estavel_ms) { pincaDisparada = true; ev.push({ tipo: 'pinca' }); }
                if (fechada && pincaDisparada) ev.push({ tipo: 'arrastar', dx: vx, dy: vy, x: c.x, y: c.y });

                const aberta = n >= 4 && polegar && !fechada;
                const punho = n === 0 && !fechada;

                // deslizar: mão aberta, rápida, eixo dominante
                if (aberta && vel > lim.deslizar_vel && t - ultimoDeslizar > lim.deslizar_pausa_ms) {
                    const horizontal = Math.abs(vx) > Math.abs(vy) * 1.4, vertical = Math.abs(vy) > Math.abs(vx) * 1.4;
                    if (horizontal) { ultimoDeslizar = t; ev.push({ tipo: vx > 0 ? 'deslizar_direita' : 'deslizar_esquerda' }); }
                    else if (vertical) { ultimoDeslizar = t; ev.push({ tipo: vy > 0 ? 'deslizar_baixo' : 'deslizar_cima' }); }
                    abertaDesde = 0; palmaDisparada = true;     // um movimento rápido não é palma parada
                }

                // palma aberta parada
                if (aberta && vel < lim.parada_vel) {
                    if (!abertaDesde) abertaDesde = t;
                    if (!palmaDisparada && t - abertaDesde >= lim.palma_ms) { palmaDisparada = true; ev.push({ tipo: 'palma' }); }
                } else if (!aberta) { abertaDesde = 0; palmaDisparada = false; }
                else if (vel >= lim.parada_vel) { abertaDesde = 0; }

                // punho segurado
                if (punho && vel < lim.parada_vel * 1.5) {
                    if (!punhoDesde) punhoDesde = t;
                    if (!punhoDisparado && t - punhoDesde >= lim.punho_ms) { punhoDisparado = true; ev.push({ tipo: 'punho' }); }
                } else if (!punho) { punhoDesde = 0; punhoDisparado = false; }

                return ev;
            },
            estado(p, asp = 16 / 9) {
                if (!p || p.length < 21) return null;
                const tam = tamanhoMao(p, asp), e = dedosEstendidos(p, asp);
                return { pinca: +(dist(p[4], p[8], asp) / tam).toFixed(2), dedos: e.n, polegar: e.polegar, fechada };
            },
        };
    }

    // ------------------------------------------------------------------ cabeça (sim / não)
    function medidasCabeca(p) {
        const topo = p[10], queixo = p[152], nariz = p[1], bocheE = p[234], bocheD = p[454];
        const alt = (queixo.y - topo.y) || 1e-6, larg = (bocheD.x - bocheE.x) || 1e-6;
        return { pitch: (nariz.y - topo.y) / alt, yaw: (nariz.x - bocheE.x) / larg };
    }

    function criarCabeca(opcoes = {}) {
        const lim = { ...LIM, ...opcoes };
        const eixo = (amp) => ({ ext: null, dir: 0, movs: [], amp });
        let P = eixo(lim.cabeca_pitch), Y = eixo(lim.cabeca_yaw), ultimo = -1e9;

        function passo(e, v, t) {                           // conta vai-e-volta com amplitude mínima
            if (e.ext === null) { e.ext = v; return; }
            const d = v - e.ext;
            if (e.dir === 0) { if (Math.abs(d) >= e.amp) { e.dir = Math.sign(d); e.ext = v; e.movs.push(t); } else if (Math.abs(d) < e.amp * 0.25) e.ext = e.ext * 0.9 + v * 0.1; return; }
            if (Math.sign(d) === e.dir) { e.ext = v; }
            else if (Math.abs(d) >= e.amp) { e.dir = Math.sign(d); e.ext = v; e.movs.push(t); }
            while (e.movs.length && t - e.movs[0] > lim.cabeca_janela_ms) e.movs.shift();
            if (!e.movs.length) { e.dir = 0; }
        }

        return {
            reiniciar() { P = eixo(lim.cabeca_pitch); Y = eixo(lim.cabeca_yaw); },
            atualizar(p, t) {
                if (!p || p.length < 455) { this.reiniciar(); return []; }
                const m = medidasCabeca(p);
                passo(P, m.pitch, t); passo(Y, m.yaw, t);
                if (t - ultimo < lim.cabeca_pausa_ms) return [];
                const nP = P.movs.length, nY = Y.movs.length;
                if (nP >= lim.cabeca_movimentos && nP >= nY + 2) { ultimo = t; this.reiniciar(); return [{ tipo: 'cabeca_sim' }]; }
                if (nY >= lim.cabeca_movimentos && nY >= nP + 2) { ultimo = t; this.reiniciar(); return [{ tipo: 'cabeca_nao' }]; }
                return [];
            },
            medidas: medidasCabeca,
        };
    }

    // ------------------------------------------------------------------ filtro One Euro (Casiez et al.): suaviza o tremor parado e quase não atrasa o movimento rápido
    function umEuro(minCutoff = 1.2, beta = 8, dCutoff = 1.0) {
        let xAnt = null, dxAnt = 0, tAnt = 0;
        const alfa = (cutoff, dt) => { const tau = 1 / (2 * Math.PI * cutoff); return 1 / (1 + tau / dt); };
        return (x, t) => {                                 // t em ms
            if (xAnt === null) { xAnt = x; tAnt = t; return x; }
            const dt = Math.max(0.001, (t - tAnt) / 1000);
            const dx = (x - xAnt) / dt;
            const ad = alfa(dCutoff, dt);
            dxAnt = ad * dx + (1 - ad) * dxAnt;
            const a = alfa(minCutoff + beta * Math.abs(dxAnt), dt);
            xAnt = a * x + (1 - a) * xAnt; tAnt = t;
            return xAnt;
        };
    }
    function filtrarPontos(minCutoff, beta) {              // um filtro por coordenada de cada ponto; devolve (pontos, t) -> pontos suavizados
        let fx = [], fy = [];
        return (p, t) => {
            if (!p) { fx = []; fy = []; return p; }
            return p.map((q, i) => {
                if (!fx[i]) { fx[i] = umEuro(minCutoff, beta); fy[i] = umEuro(minCutoff, beta); }
                return { x: fx[i](q.x, t), y: fy[i](q.y, t), z: q.z };
            });
        };
    }

    // ------------------------------------------------------------------ MOUSE NO AR (só enquanto o usuário liga o modo)
    // Uma mão: o ponteiro segue o meio entre as pontas do polegar e do indicador (não pula ao fechar a pinça); pinça = botão esquerdo (arrastar ícones
    // é só manter a pinça e mover); polegar+médio = botão direito; dois dedos (V) subindo/descendo = rolar; punho = estaciona o ponteiro.
    // Duas mãos em pinça se afastando/aproximando = zoom. Saídas em coordenadas 0..1 da TELA (a região útil da câmera é esticada para a tela inteira).
    function criarMouse(opcoes = {}) {
        const c = { x0: 0.2, x1: 0.8, y0: 0.15, y1: 0.78, fecha: 0.22, abre: 0.35, baixar_ms: 60, perdida_ms: 1200, rolar_passo: 0.5, zoom_passo: 0.55, dir_pausa_ms: 700, ...opcoes };
        let baixo = false, pinca = false, fechouEm = 0, visto = 0, ultX = -1, ultY = -1;
        let dirPress = false, dirAte = 0, scrollAcc = 0, scrollY = null, zoomBase = null, emZoom = false;
        const lim = (v) => Math.max(0, Math.min(1, v));
        const mapa = (x, y) => [lim((x - c.x0) / (c.x1 - c.x0)), lim((y - c.y0) / (c.y1 - c.y0))];
        const soltarTudo = (ev) => { if (baixo) { baixo = false; ev.push({ tipo: 'soltar' }); } pinca = false; };
        return {
            reiniciar() { baixo = false; pinca = false; zoomBase = null; emZoom = false; scrollY = null; scrollAcc = 0; ultX = ultY = -1; },
            ativo: () => ({ baixo, emZoom }),
            atualizar(maos, t, asp = 16 / 9) {
                const ev = [];
                if (!maos || !maos.length) {
                    if (t - visto > c.perdida_ms) { soltarTudo(ev); zoomBase = null; emZoom = false; scrollY = null; }
                    return ev;
                }
                visto = t;
                if (maos.length >= 2) {                                              // zoom: as duas mãos em pinça
                    const info = maos.slice(0, 2).map((p) => { const tam = tamanhoMao(p, asp); return { razao: dist(p[4], p[8], asp) / tam, tam, m: { x: (p[4].x + p[8].x) / 2, y: (p[4].y + p[8].y) / 2 } }; });
                    const ambas = info.every((i) => i.razao < (emZoom ? c.abre : c.fecha));
                    if (ambas) {
                        soltarTudo(ev);
                        const d = Math.hypot((info[0].m.x - info[1].m.x) * asp, info[0].m.y - info[1].m.y) / ((info[0].tam + info[1].tam) / 2);
                        if (zoomBase === null) { zoomBase = d; emZoom = true; return ev; }
                        const passos = Math.trunc((d - zoomBase) / c.zoom_passo);
                        if (passos) { ev.push({ tipo: 'zoom', passos }); zoomBase += passos * c.zoom_passo; }
                        return ev;
                    }
                    if (emZoom) { emZoom = false; zoomBase = null; }
                }
                const p = maos[0];
                const tam = tamanhoMao(p, asp), e = dedosEstendidos(p, asp);
                const rI = dist(p[4], p[8], asp) / tam, rM = dist(p[4], p[12], asp) / tam;
                const fator = lim((0.45 - rI) / (0.45 - c.fecha));
                const px = p[8].x + (((p[4].x + p[8].x) / 2) - p[8].x) * fator, py = p[8].y + (((p[4].y + p[8].y) / 2) - p[8].y) * fator;

                const punho = e.n === 0 && rI >= c.fecha;
                const rolando = e.dedos[0] && e.dedos[1] && !e.dedos[2] && !e.dedos[3] && rI > 0.4;
                if (rolando) {
                    soltarTudo(ev);
                    const cy = (p[0].y + p[9].y) / 2;
                    if (scrollY !== null) {
                        scrollAcc += (cy - scrollY) / tam;
                        const passos = Math.trunc(scrollAcc / c.rolar_passo);
                        if (passos) { ev.push({ tipo: 'rolar', passos }); scrollAcc -= passos * c.rolar_passo; }       // mão sobe -> passos negativos = roda para baixo (como arrastar o conteúdo)
                    }
                    scrollY = cy;
                    return ev;
                }
                scrollY = null; scrollAcc = 0;
                if (punho) { soltarTudo(ev); return ev; }

                const [sx, sy] = mapa(px, py);
                if (Math.abs(sx - ultX) > 0.002 || Math.abs(sy - ultY) > 0.002) { ev.push({ tipo: 'mover', x: sx, y: sy }); ultX = sx; ultY = sy; }
                if (!pinca && rI < c.fecha) { pinca = true; fechouEm = t; }
                else if (pinca && rI > c.abre) { pinca = false; if (baixo) { baixo = false; ev.push({ tipo: 'soltar' }); } }
                if (pinca && !baixo && t - fechouEm >= c.baixar_ms) { baixo = true; ev.push({ tipo: 'baixar' }); }
                if (!dirPress && rM < c.fecha && rI > 0.27 && t > dirAte) { dirPress = true; dirAte = t + c.dir_pausa_ms; ev.push({ tipo: 'clique_direito' }); }
                else if (dirPress && rM > c.abre) dirPress = false;
                return ev;
            },
        };
    }

    return { criarMouse, umEuro, filtrarPontos, LIM, dist, tamanhoMao, dedosEstendidos, centroPalma, criarMao, criarCabeca, medidasCabeca };
});
