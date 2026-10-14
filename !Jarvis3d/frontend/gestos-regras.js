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

    return { LIM, dist, tamanhoMao, dedosEstendidos, centroPalma, criarMao, criarCabeca, medidasCabeca };
});
