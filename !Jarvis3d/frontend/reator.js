// Reator Arc do Jarvis: desenhado em canvas, reage ao estado e ao áudio.
// Uso: Reator.iniciar(canvas, { estado: () => 'ouvindo', nivel: () => 0..1, espectro: () => Uint8Array|null })
(function () {
    'use strict';

    const TAU = Math.PI * 2;
    const CORES = {
        base:     [0, 229, 255],
        claro:    [125, 249, 255],
        ambar:    [255, 183, 3],
        erro:     [255, 77, 109],
    };
    // a emoção de cada frase tinge o reator e acelera (ou acalma) o giro
    const EMO = {
        animado:    { cor: [80, 255, 170],  giro: 1.3 },
        adrenalina: { cor: [255, 70, 60],   giro: 3.4 },
        triunfante: { cor: [255, 215, 64],  giro: 1.1 },
        preocupado: { cor: [255, 140, 0],   giro: 0.7 },
        sarcastico: { cor: [190, 130, 255], giro: 0.9 },
        risada:     { cor: [150, 255, 110], giro: 1.5 },
        curioso:    { cor: [70, 170, 255],  giro: 1.0 },
        irritado:   { cor: [255, 70, 150],  giro: 2.2 },
        suspiro:    { cor: [150, 170, 205], giro: 0.5 },
    };
    // velocidade de giro, brilho e cor dos arcos por estado
    const PERFIL = {
        offline:  { giro: 0.05, brilho: 0.25, arcos: 'erro' },
        espera:   { giro: 0.18, brilho: 0.55, arcos: 'base' },
        ouvindo:  { giro: 0.35, brilho: 0.8,  arcos: 'base' },
        pensando: { giro: 1.9,  brilho: 0.9,  arcos: 'ambar' },
        falando:  { giro: 0.55, brilho: 1.0,  arcos: 'claro' },
    };

    const lerp = (a, b, k) => a + (b - a) * k;
    const mix = (a, b, k) => [lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k)];
    const rgba = (c, a) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${Math.max(0, Math.min(1, a))})`;

    function definirTema(base, claro) {
        CORES.base = base.slice();
        CORES.claro = claro.slice();
    }

    // pontos de uma esfera (espiral de Fibonacci) para o estilo "esfera"
    const N_ESFERA = 280;
    const PONTOS_ESFERA = Array.from({ length: N_ESFERA }, (_, i) => {
        const y = 1 - (i / (N_ESFERA - 1)) * 2, r = Math.sqrt(1 - y * y), ang = i * 2.399963;
        return [Math.cos(ang) * r, y, Math.sin(ang) * r];
    });

    function iniciar(canvas, api) {
        const ctx = canvas.getContext('2d');
        let largura = 0, altura = 0, dpr = 1;

        // estado suavizado, para as transições não darem saltos
        const s = {
            giro: 0.2, brilho: 0.5, nivel: 0, cor: CORES.base.slice(),
            rot1: 0, rot2: 0, rot3: 0, rot4: 0,
            barras: new Float32Array(120), tomK: 0,
        };
        const particulas = Array.from({ length: 46 }, (_, i) => ({
            a: Math.random() * TAU, r: 0.56 + Math.random() * 0.4,
            v: (0.02 + Math.random() * 0.06) * (i % 2 ? 1 : -1), t: 0.6 + Math.random() * 1.6, f: Math.random() * TAU,
        }));

        function ajustar() {
            const caixa = canvas.getBoundingClientRect();
            dpr = Math.min(window.devicePixelRatio || 1, 2);
            largura = Math.max(1, caixa.width);
            altura = Math.max(1, caixa.height);
            canvas.width = Math.round(largura * dpr);
            canvas.height = Math.round(altura * dpr);
        }
        new ResizeObserver(ajustar).observe(canvas);
        ajustar();

        let ultimo = performance.now();

        function quadro(agora) {
            const dt = Math.min(0.05, (agora - ultimo) / 1000);
            ultimo = agora;
            desenhar(agora / 1000, dt);
            requestAnimationFrame(quadro);
        }

        function desenhar(t, dt) {
            const estado = api.estado();
            const alvo = PERFIL[estado] || PERFIL.espera;
            const k = 1 - Math.pow(0.0025, dt); // suavização independente do fps
            const emo = api.emocao ? EMO[api.emocao()] : null;
            s.giro = lerp(s.giro, emo ? Math.max(alvo.giro, emo.giro) : alvo.giro, k);
            s.tomK = lerp(s.tomK, emo ? 0.6 : 0, k);
            s.brilho = lerp(s.brilho, alvo.brilho, k);
            s.nivel = lerp(s.nivel, api.nivel(), 1 - Math.pow(0.0005, dt));
            s.cor = mix(s.cor, emo ? emo.cor : CORES[alvo.arcos], k);
            s.rot1 += dt * s.giro * 0.35;
            s.rot2 -= dt * s.giro * 0.6;
            s.rot3 += dt * s.giro * 1.25;
            s.rot4 -= dt * s.giro * 0.12;

            const cx = canvas.width / 2, cy = canvas.height / 2;
            const R = Math.min(canvas.width, canvas.height) / 2 * 0.94;
            const nivel = s.nivel;
            const base = mix(CORES.base, s.cor, s.tomK * 0.7), claro = mix(CORES.claro, s.cor, s.tomK);
            const estilo = api.estilo ? api.estilo() : 'classico';
            const b = s.brilho * (api.brilho ? api.brilho() : 1);
            const classico = estilo === 'classico', minimo = estilo === 'minimo', esfera = estilo === 'esfera';

            ctx.setTransform(1, 0, 0, 1, 0, 0);
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.globalCompositeOperation = 'lighter';
            ctx.lineCap = 'round';

            // halo
            const halo = ctx.createRadialGradient(cx, cy, R * 0.05, cx, cy, R * 1.0);
            halo.addColorStop(0, rgba(claro, 0.34 * b + 0.3 * nivel));
            halo.addColorStop(0.35, rgba(base, 0.13 * b + 0.12 * nivel));
            halo.addColorStop(1, rgba(base, 0));
            ctx.fillStyle = halo;
            ctx.beginPath(); ctx.arc(cx, cy, R * 1.0, 0, TAU); ctx.fill();

            const lw = Math.max(1, R * 0.006);

            // anel externo fino + marcações
            ctx.strokeStyle = rgba(base, 0.34 * b + 0.1);
            ctx.lineWidth = lw;
            ctx.beginPath(); ctx.arc(cx, cy, R * 0.985, 0, TAU); ctx.stroke();

            ctx.save(); ctx.translate(cx, cy); ctx.rotate(s.rot1);
            const marcas = (minimo ? 0 : 120);
            for (let i = 0; i < marcas; i++) {
                const a = (i / marcas) * TAU;
                const longa = i % 10 === 0, media = i % 5 === 0;
                const r0 = R * 0.925, r1 = R * (longa ? 0.965 : media ? 0.953 : 0.942);
                ctx.strokeStyle = rgba(longa ? claro : base, longa ? 0.8 * b : 0.38 * b);
                ctx.lineWidth = longa ? lw * 1.6 : lw;
                ctx.beginPath();
                ctx.moveTo(Math.cos(a) * r0, Math.sin(a) * r0);
                ctx.lineTo(Math.cos(a) * r1, Math.sin(a) * r1);
                ctx.stroke();
            }
            ctx.restore();

            // anel tracejado em sentido contrário
            ctx.save(); ctx.translate(cx, cy); ctx.rotate(s.rot2);
            ctx.setLineDash([R * 0.012, R * 0.05]);
            ctx.strokeStyle = rgba(base, minimo ? 0 : 0.5 * b);
            ctx.lineWidth = lw * 1.4;
            ctx.beginPath(); ctx.arc(0, 0, R * 0.875, 0, TAU); ctx.stroke();
            ctx.setLineDash([]);
            ctx.restore();

            // arcos grossos (a cor muda por estado)
            const cArco = s.cor;
            ctx.save(); ctx.translate(cx, cy); ctx.rotate(s.rot3);
            ctx.shadowColor = rgba(cArco, 0.9);
            ctx.shadowBlur = R * 0.04;
            const arcos = [[0, 0.62], [2.2, 0.38], [4.0, 0.5]];
            ctx.lineWidth = R * 0.016;
            for (const [ini, tam] of arcos) {
                ctx.strokeStyle = rgba(cArco, 0.9 * b);
                ctx.beginPath(); ctx.arc(0, 0, R * 0.81, ini, ini + tam); ctx.stroke();
            }
            ctx.restore();
            ctx.save(); ctx.translate(cx, cy); ctx.rotate(-s.rot3 * 0.7);
            ctx.shadowColor = rgba(cArco, 0.7);
            ctx.shadowBlur = R * 0.03;
            ctx.lineWidth = R * 0.009;
            ctx.strokeStyle = rgba(cArco, 0.7 * b);
            for (let i = 0; i < 4; i++) {
                ctx.beginPath(); ctx.arc(0, 0, R * 0.745, i * TAU / 4 + 0.15, i * TAU / 4 + 0.15 + 0.5); ctx.stroke();
            }
            ctx.restore();

            // barras radiais (espectro quando há áudio; ondulação suave nos outros estados)
            const espectro = api.espectro();
            const N = s.barras.length;
            const r0 = R * 0.555;
            for (let i = 0; i < N; i++) {
                let alvoBarra;
                const pos = i / N;
                if (espectro && estado === 'falando') {
                    const m = pos < 0.5 ? pos * 2 : (1 - pos) * 2; // espelha: graves em cima e embaixo
                    const idx = Math.min(espectro.length - 1, Math.floor(Math.pow(m, 1.35) * espectro.length * 0.7));
                    alvoBarra = espectro[idx] / 255;
                } else {
                    const onda = 0.5 + 0.5 * Math.sin(t * 2.2 + i * 0.37) * Math.sin(t * 0.9 + i * 0.11);
                    alvoBarra = (estado === 'falando' ? 0.15 + 0.7 * nivel : estado === 'ouvindo' ? 0.06 + 0.9 * nivel : estado === 'pensando' ? 0.1 + 0.12 * onda : 0.05 + 0.04 * onda) * (0.55 + 0.45 * onda);
                }
                s.barras[i] = lerp(s.barras[i], alvoBarra, 1 - Math.pow(0.0002, dt));
                const a = pos * TAU - Math.PI / 2 + s.rot4;
                const comp = R * (0.012 + s.barras[i] * 0.2);
                ctx.strokeStyle = rgba(s.barras[i] > 0.5 ? claro : base, 0.35 + 0.65 * s.barras[i]);
                ctx.lineWidth = Math.max(1.2, R * 0.0095);
                ctx.beginPath();
                ctx.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0);
                ctx.lineTo(cx + Math.cos(a) * (r0 + comp), cy + Math.sin(a) * (r0 + comp));
                ctx.stroke();
            }

            // anel interno
            ctx.strokeStyle = rgba(claro, 0.55 * b);
            ctx.lineWidth = lw * 2;
            ctx.beginPath(); ctx.arc(cx, cy, R * 0.525, 0, TAU); ctx.stroke();

            if (esfera) {
                // esfera de partículas girando; pulsa com a voz
                const rs = R * 0.44 * (1 + 0.16 * nivel);
                const ay = t * 0.35 + s.rot4, ax = 0.45 + Math.sin(t * 0.2) * 0.2;
                const cy1 = Math.cos(ay), sy1 = Math.sin(ay), cx1 = Math.cos(ax), sx1 = Math.sin(ax);
                for (const [px, py, pz] of PONTOS_ESFERA) {
                    const x1 = px * cy1 + pz * sy1, z1 = -px * sy1 + pz * cy1;
                    const y2 = py * cx1 - z1 * sx1, z2 = py * sx1 + z1 * cx1;
                    const prof = (z2 + 1) / 2;
                    ctx.fillStyle = rgba(prof > 0.6 ? claro : base, (0.18 + 0.75 * prof) * b);
                    ctx.beginPath(); ctx.arc(cx + x1 * rs, cy + y2 * rs, Math.max(0.8, R * (0.0035 + 0.0075 * prof)), 0, TAU); ctx.fill();
                }
            }
            // bobinas do reator (10 segmentos)
            ctx.save(); ctx.translate(cx, cy); ctx.rotate(s.rot4 * 0.6);
            const bobinas = classico ? 10 : 0;
            for (let i = 0; i < bobinas; i++) {
                const a0 = (i / bobinas) * TAU + 0.05, a1 = ((i + 1) / bobinas) * TAU - 0.05;
                ctx.strokeStyle = rgba(base, 0.28 * b + 0.45 * nivel + 0.08 * Math.sin(t * 3 + i));
                ctx.lineWidth = R * 0.082;
                ctx.lineCap = 'butt';
                ctx.beginPath(); ctx.arc(0, 0, R * 0.395, a0, a1); ctx.stroke();
                ctx.strokeStyle = rgba(claro, 0.5 * b + 0.4 * nivel);
                ctx.lineWidth = lw;
                ctx.beginPath(); ctx.arc(0, 0, R * 0.438, a0, a1); ctx.stroke();
                ctx.beginPath(); ctx.arc(0, 0, R * 0.352, a0, a1); ctx.stroke();
            }
            ctx.lineCap = 'round';
            ctx.restore();

            // anel do núcleo
            ctx.strokeStyle = rgba(claro, 0.85 * b);
            ctx.lineWidth = lw * 2.4;
            ctx.shadowColor = rgba(claro, 0.9); ctx.shadowBlur = R * 0.035;
            ctx.beginPath(); ctx.arc(cx, cy, R * 0.3, 0, TAU); ctx.stroke();
            ctx.shadowBlur = 0;

            // núcleo brilhante que pulsa com a voz
            const pulso = 1 + 0.05 * Math.sin(t * (estado === 'pensando' ? 9 : 2.4)) + 0.2 * nivel;
            const rn = R * 0.255 * pulso;
            const nucleo = ctx.createRadialGradient(cx, cy, 0, cx, cy, rn);
            nucleo.addColorStop(0, `rgba(255,255,255,${0.95 * Math.min(1, b + 0.2)})`);
            nucleo.addColorStop(0.35, rgba(claro, 0.75 * b + 0.2));
            nucleo.addColorStop(1, rgba(base, 0));
            ctx.fillStyle = nucleo;
            ctx.beginPath(); ctx.arc(cx, cy, rn, 0, TAU); ctx.fill();

            // triângulo interno (o reator Mark I)
            ctx.save(); ctx.translate(cx, cy); ctx.rotate(-Math.PI / 2 + s.rot4 * 0.3);
            ctx.strokeStyle = `rgba(255,255,255,${classico ? 0.55 + 0.4 * nivel : 0})`;
            ctx.lineWidth = lw * 1.5;
            ctx.beginPath();
            for (let i = 0; i < 3; i++) {
                const a = (i / 3) * TAU, rr = R * 0.17;
                i === 0 ? ctx.moveTo(Math.cos(a) * rr, Math.sin(a) * rr) : ctx.lineTo(Math.cos(a) * rr, Math.sin(a) * rr);
            }
            ctx.closePath(); ctx.stroke();
            ctx.restore();

            // partículas em órbita
            for (const p of (classico ? particulas : [])) {
                p.a += p.v * dt * (0.4 + s.giro);
                const rr = R * (p.r + 0.02 * Math.sin(t * p.t + p.f));
                const x = cx + Math.cos(p.a) * rr, y = cy + Math.sin(p.a) * rr;
                const tam = Math.max(1, R * 0.0045) * (0.7 + 0.6 * Math.sin(t * p.t * 2 + p.f) ** 2);
                ctx.fillStyle = rgba(claro, (0.25 + 0.5 * nivel) * b + 0.1);
                ctx.beginPath(); ctx.arc(x, y, tam, 0, TAU); ctx.fill();
            }

            ctx.globalCompositeOperation = 'source-over';
        }

        requestAnimationFrame(quadro);
    }

    window.Reator = { iniciar, definirTema };
})();
