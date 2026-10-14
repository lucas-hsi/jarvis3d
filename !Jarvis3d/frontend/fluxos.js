// Fluxos de dados entre os painéis e o reator: fios discretos ligam cada painel ao núcleo, e pacotes de luz
// correm por eles. Pensando: tudo converge para o reator. Falando: o reator manda dados para fora.
// Quando o Jarvis usa uma ferramenta, o painel relacionado dispara pacotes mais intensos.
(function () {
    'use strict';

    let cv = null, ctx = null, api = null;
    let centro = { x: 0, y: 0, R: 100 };
    let ancoras = [];
    let pacotes = [];
    const ativos = new Map();       // id do painel -> instante (s) até quando está ativo
    let medidoEm = -9, t = 0;

    function medir() {
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const w = Math.round(innerWidth * dpr), h = Math.round(innerHeight * dpr);
        if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
        const r = document.getElementById('reator').getBoundingClientRect();
        centro = { x: r.left + r.width / 2, y: r.top + r.height / 2, R: Math.min(r.width, r.height) / 2 * 0.97 };
        ancoras = [];
        document.querySelectorAll('.painel[data-painel]').forEach((p) => {
            if (p.offsetParent === null) return;
            const b = p.getBoundingClientRect();
            if (b.width < 20 || b.height < 20) return;
            const esq = b.left + b.width / 2 < centro.x;
            ancoras.push({ id: p.dataset.painel, x: esq ? b.right : b.left, y: b.top + b.height / 2 });
        });
    }

    function curva(an) {
        const ang = Math.atan2(an.y - centro.y, an.x - centro.x);
        const ex = centro.x + Math.cos(ang) * centro.R, ey = centro.y + Math.sin(ang) * centro.R;
        return { ax: an.x, ay: an.y, cx: (an.x + ex) / 2, cy: an.y, ex, ey };
    }

    const pos = (c, u) => {
        const k = 1 - u;
        return [k * k * c.ax + 2 * k * u * c.cx + u * u * c.ex, k * k * c.ay + 2 * k * u * c.cy + u * u * c.ey];
    };

    function ativar(id, segundos = 3) {
        ativos.set(id, t + segundos);
    }

    function laco(dt) {
        if (!cv) return;
        t += dt;
        if (t - medidoEm > 0.6) { medir(); medidoEm = t; }
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, cv.width, cv.height);
        ctx.scale(dpr, dpr);
        const rgb = Visual.rgbTema();
        const estado = api.estado();
        if (estado === 'offline' || !ancoras.length) return;

        // fios discretos
        ctx.lineWidth = 1;
        for (const an of ancoras) {
            const c = curva(an);
            const quente = (ativos.get(an.id) || 0) > t;
            ctx.strokeStyle = `rgba(${rgb},${quente ? .32 : .055})`;
            ctx.beginPath(); ctx.moveTo(c.ax, c.ay); ctx.quadraticCurveTo(c.cx, c.cy, c.ex, c.ey); ctx.stroke();
        }

        // quantos pacotes por segundo, e para onde
        const taxa = { pensando: 7, falando: 3.5, ouvindo: 1.4, espera: 0.4 }[estado] ?? 0.5;
        const sentido = estado === 'falando' ? -1 : 1;                 // falando: do reator para os painéis
        if (Math.random() < taxa * dt && ancoras.length) {
            pacotes.push({ an: ancoras[(Math.random() * ancoras.length) | 0], u: sentido > 0 ? 0 : 1, v: 0.35 + Math.random() * 0.35, s: sentido, forte: false });
        }
        for (const an of ancoras) {
            if ((ativos.get(an.id) || 0) > t && Math.random() < 9 * dt) {
                pacotes.push({ an, u: 0, v: 0.5 + Math.random() * 0.4, s: 1, forte: true });
            }
        }
        if (pacotes.length > 140) pacotes.splice(0, pacotes.length - 140);

        for (const p of pacotes) p.u += p.v * dt * p.s;
        pacotes = pacotes.filter((p) => p.u >= -0.02 && p.u <= 1.02);
        for (const p of pacotes) {
            const c = curva(p.an);
            for (let k = 6; k >= 0; k--) {                              // rastro
                const u = p.u - p.s * k * 0.018;
                if (u < 0 || u > 1) continue;
                const [x, y] = pos(c, u);
                const a = (1 - k / 7) * (p.forte ? 1 : .7);
                ctx.fillStyle = k === 0 ? `rgba(255,255,255,${a})` : `rgba(${rgb},${a * .55})`;
                ctx.beginPath(); ctx.arc(x, y, (p.forte ? 2.6 : 1.9) * (1 - k * .09), 0, 6.2832); ctx.fill();
            }
        }
    }

    function iniciar(canvas, apiExterna) {
        cv = canvas; ctx = cv.getContext('2d'); api = apiExterna;
        Visual.registrar((dt) => laco(dt));
        addEventListener('resize', () => { medidoEm = -9; });
    }

    window.Fluxos = { iniciar, ativar };
})();
