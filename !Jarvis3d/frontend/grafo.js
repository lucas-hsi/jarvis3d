// Grafo vivo do cérebro do Jarvis: você no centro, as categorias de memória pessoal, as pastas do Obsidian,
// cada memória e cada nota, e os [[links]] entre as notas. Memória nova nasce na tela; o que o Jarvis usa
// numa resposta acende. Física simples (repulsão + molas) rodando no laço de animação.
(function () {
    'use strict';

    let canvas = null, dica = null;
    let nos = [], arestas = [], porId = new Map();
    let acesos = new Map();          // id -> instante (s) até quando fica aceso
    let girar = 0, relogio = 0, vistaX = 1, vistaY = 1;
    let ponteiro = null;
    const REPULSAO = 340, GRAVIDADE = 0.02, AMORTECIMENTO = 0.86;

    const MOLAS = { 'eu|categoria': [46, 0.06], 'eu|pasta': [58, 0.06], 'categoria|memoria': [24, 0.08],
                    'pasta|nota': [22, 0.08], 'nota|nota': [36, 0.012] };
    const molaDe = (a, b) => MOLAS[`${a.tipo}|${b.tipo}`] || MOLAS[`${b.tipo}|${a.tipo}`] || [30, 0.03];

    function criarNo(d, perto) {
        const ang = Math.random() * 6.2832;
        const raio = { centro: 0, categoria: 40, pasta: 56, memoria: 62, nota: 74 }[d.tipo] || 60;
        const base = perto || { x: 0, y: 0 };
        return {
            ...d, x: base.x + Math.cos(ang) * (perto ? 8 : raio), y: base.y + Math.sin(ang) * (perto ? 8 : raio), vx: 0, vy: 0,
            r: { centro: 5, categoria: 3.6, pasta: 3.6, memoria: 2.5, nota: 1.9 }[d.tipo] || 2, nasc: relogio,
        };
    }

    async function carregar() {
        try {
            const g = await (await fetch('/api/grafo')).json();
            const antigos = porId;
            const primeira = antigos.size === 0;
            nos = g.nos.map((d) => {
                const velho = antigos.get(d.id);
                if (velho) return Object.assign(velho, { rotulo: d.rotulo, imp: d.imp });
                const novo = criarNo(d);
                if (!primeira && d.tipo === 'memoria') acesos.set(d.id, relogio + 3.2);   // memória nova: nasce acesa
                return novo;
            });
            porId = new Map(nos.map((n) => [n.id, n]));
            arestas = g.arestas.map(([a, b]) => [porId.get(a), porId.get(b)]).filter(([a, b]) => a && b);
            const centro = porId.get('eu');
            if (centro) { centro.x = centro.y = 0; }
        } catch (_) { /* sem servidor: tenta de novo no próximo aviso */ }
    }

    function adicionarMemoria(m) {
        if (porId.has('m:' + m.id)) return;
        const hub = porId.get('c:' + m.categoria);
        if (!hub && m.categoria) {      // categoria nova ainda não está no grafo: recarrega tudo
            carregar().then(() => acender({ memorias: [m.id], notas: [] }));
            return;
        }
        const n = criarNo({ id: 'm:' + m.id, tipo: 'memoria', rotulo: (m.texto || '').slice(0, 70), imp: m.imp || 2 }, hub);
        nos.push(n);
        porId.set(n.id, n);
        if (hub) arestas.push([hub, n]);
        acesos.set(n.id, relogio + 3.2);
    }

    function acender({ memorias = [], notas = [] }) {
        const ate = relogio + 3.2;
        for (const id of memorias) if (porId.has('m:' + id)) acesos.set('m:' + id, ate);
        for (const t of notas) {
            const n = porId.get('n:' + t);
            if (n) {
                acesos.set(n.id, ate);
                // acende também o caminho até o centro (pasta e você), como o impulso de um neurônio
                const pai = arestas.find(([a, b]) => b === n && a.tipo === 'pasta');
                if (pai) { acesos.set(pai[0].id, ate); acesos.set('eu', ate); }
            }
        }
    }

    // ------------------------------------------------------------ física
    function passo(dt) {
        const n = nos.length;
        for (let i = 0; i < n; i++) {
            const a = nos[i];
            for (let j = i + 1; j < n; j++) {
                const b = nos[j];
                let dx = a.x - b.x, dy = a.y - b.y;
                let d2 = dx * dx + dy * dy;
                if (d2 < 4) { dx = Math.random() - .5; dy = Math.random() - .5; d2 = 4; }
                const f = REPULSAO / d2;
                const d = Math.sqrt(d2);
                const fx = (dx / d) * f, fy = (dy / d) * f;
                a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
            }
        }
        for (const [a, b] of arestas) {
            const [rep, k] = molaDe(a, b);
            const dx = b.x - a.x, dy = b.y - a.y;
            const d = Math.sqrt(dx * dx + dy * dy) || 1;
            const f = (d - rep) * k;
            a.vx += (dx / d) * f; a.vy += (dy / d) * f; b.vx -= (dx / d) * f; b.vy -= (dy / d) * f;
        }
        for (const a of nos) {
            if (a.tipo === 'centro') { a.x = a.y = a.vx = a.vy = 0; continue; }
            a.vx -= a.x * GRAVIDADE; a.vy -= a.y * GRAVIDADE;
            a.vx = Math.max(-6, Math.min(6, a.vx)) * AMORTECIMENTO;
            a.vy = Math.max(-6, Math.min(6, a.vy)) * AMORTECIMENTO;
            a.x += a.vx * dt * 30; a.y += a.vy * dt * 30;
        }
    }

    // ------------------------------------------------------------ desenho
    function desenhar() {
        const r = canvas.getBoundingClientRect();
        if (r.width < 8) return;
        const d = Math.min(window.devicePixelRatio || 1, 2);
        const w = Math.round(r.width * d), h = Math.round(r.height * d);
        if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
        const ctx = canvas.getContext('2d');
        const rgb = Visual.rgbTema();
        ctx.clearRect(0, 0, w, h);
        // enquadramento automático: mede o tamanho do grafo e estica para preencher a caixa (que é larga e baixa)
        const cosA = Math.cos(girar), senA = Math.sin(girar);
        let ex = 24, ey = 24;
        for (const n of nos) {
            ex = Math.max(ex, Math.abs(n.x * cosA - n.y * senA));
            ey = Math.max(ey, Math.abs(n.x * senA + n.y * cosA));
        }
        vistaX += ((w / 2 * 0.9) / ex - vistaX) * 0.06;
        vistaY += ((h / 2 * 0.84) / ey - vistaY) * 0.06;
        const escX = vistaX, escY = vistaY;
        const tela = (n) => [w / 2 + (n.x * cosA - n.y * senA) * escX, h / 2 + (n.x * senA + n.y * cosA) * escY];

        const aceso = (n) => (acesos.get(n.id) || 0) > relogio;
        ctx.lineWidth = d * 0.8;
        for (const [a, b] of arestas) {
            const [x1, y1] = tela(a), [x2, y2] = tela(b);
            const luz = aceso(a) && aceso(b);
            ctx.strokeStyle = luz ? `rgba(255,255,255,.85)` : `rgba(${rgb},${a.tipo === 'nota' && b.tipo === 'nota' ? .08 : .17})`;
            ctx.lineWidth = (luz ? 1.6 : .8) * d;
            ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
        }

        const rotulos = [];
        for (const n of nos) {
            const [x, y] = tela(n);
            n._x = x; n._y = y;
            const idade = relogio - n.nasc;
            const nascendo = Math.min(1, idade / 0.6);
            const luz = aceso(n);
            let cor = rgb, alfa = .55, raio = n.r;
            if (n.tipo === 'centro') { cor = '255,255,255'; alfa = 1; }
            else if (n.tipo === 'categoria') alfa = .9;
            else if (n.tipo === 'pasta') { cor = '190,235,255'; alfa = .85; }
            else if (n.tipo === 'memoria') { if ((n.imp || 2) >= 3) cor = '255,183,3'; alfa = n.imp === 1 ? .55 : .95; raio += (n.imp === 3 ? .7 : 0); }
            else if (n.tipo === 'nota') alfa = .5;
            raio = raio * 1.15 * nascendo * d * (luz ? 1.7 : 1);
            if (luz || n.tipo !== 'nota') {
                ctx.shadowColor = `rgba(${luz ? '255,255,255' : cor},.95)`;
                ctx.shadowBlur = (luz ? 16 : 7) * d;
            }
            ctx.fillStyle = `rgba(${luz ? '255,255,255' : cor},${luz ? 1 : alfa})`;
            ctx.beginPath(); ctx.arc(x, y, Math.max(.8, raio), 0, 6.2832); ctx.fill();
            ctx.shadowBlur = 0;
            if (idade < 1.4 && n.tipo === 'memoria') {                 // anel de "nascimento"
                ctx.strokeStyle = `rgba(255,255,255,${1 - idade / 1.4})`;
                ctx.lineWidth = 1.4 * d;
                ctx.beginPath(); ctx.arc(x, y, raio + idade * 22 * d, 0, 6.2832); ctx.stroke();
            }
            if (luz) {
                const t = (relogio * 2) % 1;
                ctx.strokeStyle = `rgba(255,255,255,${0.7 * (1 - t)})`;
                ctx.lineWidth = d;
                ctx.beginPath(); ctx.arc(x, y, raio + t * 14 * d, 0, 6.2832); ctx.stroke();
            }
            if (n.tipo === 'centro' || n.tipo === 'categoria' || n.tipo === 'pasta' || luz) rotulos.push([n, x, y, luz]);
        }

        ctx.font = `${Math.round(8.5 * d)}px Bahnschrift, "Segoe UI", sans-serif`;
        ctx.textBaseline = 'middle';
        for (const [n, x, y, luz] of rotulos) {
            const texto = n.tipo === 'memoria' ? n.rotulo.slice(0, 38) : String(n.rotulo).slice(0, 26);
            ctx.fillStyle = luz ? 'rgba(255,255,255,1)' : `rgba(${rgb},.75)`;
            if (luz) {
                const tw = ctx.measureText(texto).width;
                ctx.fillStyle = 'rgba(2,8,14,.8)';
                ctx.fillRect(x + 7 * d, y - 8 * d, tw + 8 * d, 16 * d);
                ctx.fillStyle = '#fff';
            }
            ctx.fillText(texto, x + 11 * d, y);
        }

        // dica ao passar o mouse
        if (ponteiro) {
            let melhor = null, dist = 12 * d;
            for (const n of nos) {
                const dd = Math.hypot(n._x - ponteiro.x * d, n._y - ponteiro.y * d);
                if (dd < dist) { dist = dd; melhor = n; }
            }
            dica.textContent = melhor ? `${{ memoria: 'Memória', nota: 'Nota', categoria: 'Categoria', pasta: 'Pasta', centro: '' }[melhor.tipo]}${melhor.tipo === 'centro' ? '' : ': '}${melhor.rotulo}` : '';
        }
    }

    function iniciar(cv, dicaEl) {
        canvas = cv; dica = dicaEl;
        canvas.addEventListener('pointermove', (e) => {
            const r = canvas.getBoundingClientRect();
            ponteiro = { x: e.clientX - r.left, y: e.clientY - r.top };
        });
        canvas.addEventListener('pointerleave', () => { ponteiro = null; dica.textContent = ''; });
        Visual.registrar((dt) => {
            relogio += dt;
            if (canvas.offsetParent === null) return;
            girar += dt * 0.04;
            if (nos.length) { passo(dt); passo(dt); }
            if (nos.length) desenhar();
        });
        carregar();
    }

    window.Grafo = { iniciar, carregar, adicionarMemoria, acender };
})();
