// Gráficos do HUD: sparklines em tempo real, radar de localização, fluxo de dados em hexadecimal e osciloscópio.
// Tudo desenhado em canvas, sem bibliotecas. As cores vêm do tema atual (variável CSS --rgb).
(function () {
    'use strict';

    const dpr = () => Math.min(window.devicePixelRatio || 1, 2);

    function rgbTema() {
        return (getComputedStyle(document.body).getPropertyValue('--rgb') || '0,229,255').trim();
    }

    function ajustar(canvas) {
        const r = canvas.getBoundingClientRect(), d = dpr();
        const w = Math.max(1, Math.round(r.width * d)), h = Math.max(1, Math.round(r.height * d));
        if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
        return { w, h, d };
    }

    function visivel(canvas) {
        return canvas.offsetParent !== null && canvas.getBoundingClientRect().width > 4;
    }

    // ------------------------------------------------------------ laço único de animação
    const itens = [];
    let ultimo = 0, acumulado = 0, alvoFps = 30;
    function laco(agora) {
        const dt = Math.min(0.1, (agora - ultimo) / 1000 || 0.016);
        ultimo = agora;
        acumulado += dt;
        if (!document.hidden && acumulado >= 1 / alvoFps) {    // 30 quadros bastam para os enfeites (15 na bateria)
            for (const it of itens) { try { it(acumulado, agora / 1000); } catch (_) {} }
            acumulado = 0;
        }
        requestAnimationFrame(laco);
    }
    requestAnimationFrame(laco);
    const registrar = (fn) => itens.push(fn);

    // ------------------------------------------------------------ sparkline
    class Spark {
        // op: { max: número fixo (ou null = escala automática), linhas: 1|2, n: pontos guardados, formato: fn }
        constructor(canvas, op = {}) {
            this.c = canvas;
            this.max = op.max ?? null;
            this.n = op.n || 80;
            this.linhas = op.linhas || 1;
            this.dados = Array.from({ length: this.linhas }, () => []);
            this.pico = 1;
            new ResizeObserver(() => this.desenhar()).observe(canvas);
        }

        push(...valores) {
            valores.forEach((v, i) => {
                const a = this.dados[i];
                a.push(v);
                if (a.length > this.n) a.shift();
            });
            this.desenhar();
        }

        desenhar() {
            const c = this.c;
            if (!visivel(c)) return;
            const { w, h, d } = ajustar(c);
            const ctx = c.getContext('2d');
            ctx.clearRect(0, 0, w, h);
            const rgb = rgbTema();
            const teto = this.max ?? (() => {
                const pico = Math.max(1, ...this.dados.flat());
                this.pico = Math.max(pico * 1.15, this.pico * 0.97);   // sobe rápido, desce devagar
                return this.pico;
            })();

            ctx.strokeStyle = `rgba(${rgb},.1)`;
            ctx.lineWidth = d;
            for (let i = 1; i <= 3; i++) {
                const y = Math.round(h * i / 4) + .5;
                ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
            }

            this.dados.forEach((serie, idx) => {
                if (serie.length < 2) return;
                const passo = w / (this.n - 1);
                const x0 = w - (serie.length - 1) * passo;
                const pt = (v, i) => [x0 + i * passo, h - 2 * d - (Math.min(v, teto) / teto) * (h - 5 * d)];
                const cor = idx === 0 ? rgb : '255,183,3';
                if (idx === 0) {
                    const g = ctx.createLinearGradient(0, 0, 0, h);
                    g.addColorStop(0, `rgba(${cor},.34)`);
                    g.addColorStop(1, `rgba(${cor},0)`);
                    ctx.beginPath();
                    serie.forEach((v, i) => { const [x, y] = pt(v, i); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
                    ctx.lineTo(w, h); ctx.lineTo(x0, h); ctx.closePath();
                    ctx.fillStyle = g; ctx.fill();
                }
                ctx.beginPath();
                serie.forEach((v, i) => { const [x, y] = pt(v, i); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
                ctx.strokeStyle = `rgba(${cor},.95)`;
                ctx.lineWidth = 1.6 * d;
                ctx.shadowColor = `rgba(${cor},.8)`;
                ctx.shadowBlur = 6 * d;
                ctx.stroke();
                ctx.shadowBlur = 0;
                const [ux, uy] = pt(serie[serie.length - 1], serie.length - 1);   // ponto atual
                ctx.fillStyle = '#fff';
                ctx.beginPath(); ctx.arc(ux - d, uy, 2 * d, 0, 6.2832); ctx.fill();
            });
        }
    }

    // ------------------------------------------------------------ radar de localização
    function radar(canvas) {
        let angulo = 0, ultimoPing = -9;
        registrar((dt, t) => {
            if (!visivel(canvas)) return;
            const { w, h, d } = ajustar(canvas);
            const ctx = canvas.getContext('2d');
            const rgb = rgbTema();
            const cx = w / 2, cy = h / 2, R = Math.min(w, h) / 2 - 2 * d;
            angulo = (angulo + dt * 1.6) % (Math.PI * 2);
            ctx.clearRect(0, 0, w, h);
            ctx.lineWidth = d;
            for (const f of [0.34, 0.67, 1]) {
                ctx.strokeStyle = `rgba(${rgb},${f === 1 ? .6 : .22})`;
                ctx.beginPath(); ctx.arc(cx, cy, R * f, 0, 6.2832); ctx.stroke();
            }
            ctx.strokeStyle = `rgba(${rgb},.2)`;
            ctx.beginPath(); ctx.moveTo(cx - R, cy); ctx.lineTo(cx + R, cy); ctx.moveTo(cx, cy - R); ctx.lineTo(cx, cy + R); ctx.stroke();
            if (ctx.createConicGradient) {                               // varredura com rastro
                const g = ctx.createConicGradient(angulo - 1.1, cx, cy);
                g.addColorStop(0, `rgba(${rgb},0)`);
                g.addColorStop(0.17, `rgba(${rgb},.5)`);
                g.addColorStop(0.1801, `rgba(${rgb},0)`);
                ctx.fillStyle = g;
                ctx.beginPath(); ctx.arc(cx, cy, R, 0, 6.2832); ctx.fill();
            }
            ctx.strokeStyle = `rgba(${rgb},.95)`;
            ctx.lineWidth = 1.5 * d;
            ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(angulo) * R, cy + Math.sin(angulo) * R); ctx.stroke();
            // marcador da sua posição: acende quando a varredura passa
            const bx = cx + R * 0.34, by = cy - R * 0.22;
            const alvo = Math.atan2(by - cy, bx - cx);
            const diff = ((angulo - alvo) % 6.2832 + 6.2832) % 6.2832;
            if (diff < 0.18) ultimoPing = t;
            const brilho = Math.max(0.35, 1 - (t - ultimoPing) / 1.4);
            ctx.fillStyle = `rgba(255,255,255,${brilho})`;
            ctx.shadowColor = `rgba(${rgb},1)`; ctx.shadowBlur = 8 * d;
            ctx.beginPath(); ctx.arc(bx, by, 2.6 * d, 0, 6.2832); ctx.fill();
            ctx.shadowBlur = 0;
            ctx.strokeStyle = `rgba(${rgb},${0.55 * brilho})`;
            ctx.beginPath(); ctx.arc(bx, by, (4 + (1 - brilho) * 8) * d, 0, 6.2832); ctx.stroke();
        });
    }

    // ------------------------------------------------------------ fluxo de dados (hexadecimal rolando)
    function fluxoHex(canvas, atividade) {
        const linhas = 4, hex = '0123456789ABCDEF';
        const fita = Array.from({ length: linhas }, () => Array.from({ length: 120 }, () => hex[(Math.random() * 16) | 0] + hex[(Math.random() * 16) | 0]));
        const desloc = new Array(linhas).fill(0);
        registrar((dt) => {
            if (!visivel(canvas)) return;
            const { w, h, d } = ajustar(canvas);
            const ctx = canvas.getContext('2d');
            const rgb = rgbTema();
            const a = atividade();                                      // 0 (parado) a 1 (pensando)
            ctx.clearRect(0, 0, w, h);
            const tam = Math.max(8, Math.min(12, h / (linhas + 0.6) / d)) * d;
            ctx.font = `${tam}px "Cascadia Mono", Consolas, monospace`;
            ctx.textBaseline = 'top';
            const larg = tam * 2.2;
            for (let l = 0; l < linhas; l++) {
                desloc[l] += dt * (14 + 38 * a + l * 9) * (l % 2 ? -1 : 1) * d;
                const y = l * (h / linhas);
                const total = fita[l].length * larg;
                for (let i = 0; i < fita[l].length; i++) {
                    let x = (i * larg + desloc[l]) % total;
                    if (x < 0) x += total;
                    if (x > w + larg) continue;
                    const borda = Math.min(x, w - x) / (w * 0.25);
                    const quente = Math.random() < 0.0009 + 0.01 * a;
                    if (quente) fita[l][i] = hex[(Math.random() * 16) | 0] + hex[(Math.random() * 16) | 0];
                    ctx.fillStyle = quente ? '#fff' : `rgba(${rgb},${Math.max(0, Math.min(1, borda)) * (0.28 + 0.5 * a)})`;
                    ctx.fillText(fita[l][i], x, y);
                }
            }
        });
    }

    // ------------------------------------------------------------ osciloscópio (microfone ou voz do Jarvis)
    function osciloscopio(canvas, dados) {
        let fase = 0;
        registrar((dt) => {
            if (!visivel(canvas)) return;
            const { w, h, d } = ajustar(canvas);
            const ctx = canvas.getContext('2d');
            const rgb = rgbTema();
            ctx.clearRect(0, 0, w, h);
            const amostras = dados();                                  // Uint8Array (128 = silêncio) ou null
            fase += dt * 2;
            ctx.beginPath();
            const n = 160;
            for (let i = 0; i <= n; i++) {
                const x = (i / n) * w;
                let v;
                if (amostras && amostras.length) {
                    const k = Math.min(amostras.length - 1, Math.floor((i / n) * amostras.length));
                    v = (amostras[k] - 128) / 128;
                } else {
                    v = 0.04 * Math.sin(fase + i * 0.21) * Math.sin(fase * 0.7 + i * 0.05);   // linha viva em repouso
                }
                const janela = Math.sin((i / n) * Math.PI);            // afina nas pontas
                const y = h / 2 + v * (h * 0.46) * janela;
                i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
            }
            ctx.strokeStyle = `rgba(${rgb},.95)`;
            ctx.lineWidth = 1.6 * d;
            ctx.shadowColor = `rgba(${rgb},.9)`;
            ctx.shadowBlur = 8 * d;
            ctx.stroke();
            ctx.shadowBlur = 0;
        });
    }

    window.Visual = { fps: (n) => { alvoFps = n; }, registrar, Spark, radar, fluxoHex, osciloscopio, rgbTema };
})();
