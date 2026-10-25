// Visual AURORA: partículas soltas no centro reagindo à voz de verdade (analisador do áudio do Jarvis e nível do microfone),
// formas por assunto, chips do que ele está fazendo, cartões que nascem da nuvem, legenda palavra a palavra, barra flutuante
// com anexos temporários e cena 3D do clima (clima3d.js, carregada só quando precisa). Mesmo contrato do reator
// (iniciar(canvas, api) com api.estado/nivel) — quem escolhe é o ponte3d.js. Só desenha; não decide nada no servidor.
(function () {
    'use strict';
    const $ = (s) => document.querySelector(s);
    const rnd = Math.random, TAU = Math.PI * 2;
    const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
    const reduzido = matchMedia('(prefers-reduced-motion: reduce)').matches;

    // ---------------------------------------------------------------- ruído (Perlin 3D)
    const PERM = new Uint8Array(512);
    (() => { const p = [...Array(256).keys()]; for (let i = 255; i > 0; i--) { const j = (rnd() * (i + 1)) | 0; [p[i], p[j]] = [p[j], p[i]]; } for (let i = 0; i < 512; i++) PERM[i] = p[i & 255]; })();
    const fade = (t) => t * t * t * (t * (t * 6 - 15) + 10), lerp = (a, b, t) => a + (b - a) * t;
    function grad(h, x, y, z) { h &= 15; const u = h < 8 ? x : y, v = h < 4 ? y : (h === 12 || h === 14 ? x : z); return ((h & 1) ? -u : u) + ((h & 2) ? -v : v); }
    function noise(x, y, z) {
        const fx = Math.floor(x), fy = Math.floor(y), fz = Math.floor(z); const X = fx & 255, Y = fy & 255, Z = fz & 255; x -= fx; y -= fy; z -= fz;
        const u = fade(x), v = fade(y), w = fade(z);
        const A = PERM[X] + Y, AA = PERM[A] + Z, AB = PERM[A + 1] + Z, B = PERM[X + 1] + Y, BA = PERM[B] + Z, BB = PERM[B + 1] + Z;
        return lerp(lerp(lerp(grad(PERM[AA], x, y, z), grad(PERM[BA], x - 1, y, z), u), lerp(grad(PERM[AB], x, y - 1, z), grad(PERM[BB], x - 1, y - 1, z), u), v),
            lerp(lerp(grad(PERM[AA + 1], x, y, z - 1), grad(PERM[BA + 1], x - 1, y, z - 1), u), lerp(grad(PERM[AB + 1], x, y - 1, z - 1), grad(PERM[BB + 1], x - 1, y - 1, z - 1), u), v), w);
    }

    // ---------------------------------------------------------------- DOM
    const ICON = {
        clip: '<svg viewBox="0 0 24 24"><path d="M21 11.5l-8.6 8.6a5 5 0 01-7.1-7.1l8.9-8.9a3.4 3.4 0 014.8 4.8l-8.9 8.9a1.7 1.7 0 01-2.4-2.4l8.1-8.1"/></svg>',
        mic: '<svg viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0014 0M12 18v3"/></svg>',
        send: '<svg viewBox="0 0 24 24" style="stroke-width:2.2"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
        search: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg>',
        img: '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-8 8"/></svg>',
        file: '<svg viewBox="0 0 24 24"><path d="M6 3h8l5 5v13H6zM14 3v5h5"/></svg>',
        code: '<svg viewBox="0 0 24 24"><path d="M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/></svg>',
        term: '<svg viewBox="0 0 24 24"><rect x="2.5" y="4" width="19" height="16" rx="3"/><path d="M7 9l3 3-3 3M12.5 15H17"/></svg>',
    };
    let previasEl, turnoN = 0, statusEl, termsEl;
    let cv, cx2, gv, gx, cardsEl, actsEl, falaEl, voceEl, msgEl, trayEl, sendEl;
    function montarDOM() {
        const add = (html) => { const t = document.createElement('template'); t.innerHTML = html.trim(); const el = t.content.firstChild; document.body.appendChild(el); return el; };
        add('<div id="au-bg"><div class="blob b1"></div><div class="blob b2"></div><div class="blob b3"></div><div class="vig"></div></div>');
        cv = add('<canvas id="au-c"></canvas>'); gv = add('<canvas id="au-g"></canvas>');
        add('<canvas id="au-w3d"></canvas>'); add('<div id="au-wlabels"></div>'); add('<div id="au-flash"></div>');
        statusEl = add('<div id="au-status" data-e="espera"><span class="eq"><i></i><i></i><i></i><i></i><i></i></span><b>pronto</b></div>');
        actsEl = add('<div id="au-acts"></div>');
        termsEl = add('<div id="au-terms"></div>');
        cardsEl = add('<div id="au-cards"></div>');
        previasEl = add('<div id="au-previas"></div>');
        add('<div id="au-sub"><div id="au-voce"></div><div id="au-fala"></div></div>');
        falaEl = $('#au-fala'); voceEl = $('#au-voce');
        add(`<div id="au-bottom"><div id="au-tray"></div>
              <form id="au-form" autocomplete="off">
                <button type="button" class="au-ib" id="au-clip" title="Anexar imagem ou arquivo de texto (temporário)">${ICON.clip}</button>
                <input type="text" id="au-msg" maxlength="1000" placeholder="Fale ou escreva para o Jarvis…  ( / )" spellcheck="false">
                <button type="button" class="au-ib" id="au-mic" title="Falar sem dizer “Jarvis” (tecla T)">${ICON.mic}</button>
                <button type="submit" class="au-ib" id="au-send" title="Enviar">${ICON.send}</button>
              </form>
              <div id="au-hint">Anexos são temporários: valem só para este pedido e não ficam salvos. Arraste ou cole aqui.</div>
              <input type="file" id="au-file" multiple hidden accept="image/*,.txt,.md,.csv,.json,.log,.py,.js,.ts,.html,.css,.xml,.yml,.yaml,.ini,.sql">
            </div>`);
        add('<div id="au-drop">Solte para anexar (temporário)</div>');
        msgEl = $('#au-msg'); trayEl = $('#au-tray'); sendEl = $('#au-send');
        cx2 = cv.getContext('2d'); gx = gv.getContext('2d');
        ligarComposer();
        observarLegendas();
    }

    // ---------------------------------------------------------------- partículas
    const PAL = { cols: [[120, 138, 255], [56, 225, 255], [186, 110, 255], [235, 240, 255]], alpha: [0.5, 0.8, 1], size: 1.3, streak: 1.15 };
    let W = 0, H = 0, DPR = 1, CY = 0;
    const MAXN = 9000; let N = 5000, NALVO = 5000;
    const X = new Float32Array(MAXN), Y = new Float32Array(MAXN), Z = new Float32Array(MAXN), VX = new Float32Array(MAXN), VY = new Float32Array(MAXN), VZ = new Float32Array(MAXN), SD = new Float32Array(MAXN);
    const COL = new Uint8Array(MAXN), BIG = new Uint8Array(MAXN), GRP = new Uint8Array(MAXN);
    function resize() {
        DPR = Math.min(devicePixelRatio || 1, 1.5); W = innerWidth; H = innerHeight; CY = H * 0.43;
        cv.width = Math.round(W * DPR); cv.height = Math.round(H * DPR); cv.style.width = W + 'px'; cv.style.height = H + 'px';
        gv.width = Math.ceil(W / 5); gv.height = Math.ceil(H / 5);
        const b = $('#au-bottom'); if (b) document.documentElement.style.setProperty('--au-barh', Math.max(0, b.offsetHeight - 80) + 'px');
    }
    function initP() {
        const r0 = Math.min(W, H) * 0.32;
        for (let i = 0; i < MAXN; i++) {
            const r = Math.sqrt(rnd()) * r0, a = rnd() * TAU; X[i] = Math.cos(a) * r; Y[i] = Math.sin(a) * r; Z[i] = (rnd() - 0.5) * 400;
            SD[i] = rnd(); GRP[i] = (rnd() * 256) | 0; BIG[i] = rnd() < 0.035 ? 1 : 0; const q = rnd(); COL[i] = q < 0.46 ? 0 : q < 0.72 ? 1 : q < 0.92 ? 2 : 3;
        }
    }

    // ---------------------------------------------------------------- formas (pontos amostrados de um desenho)
    function raster(w, h, fillFn, edgeFn, M, edgeRatio) {
        const mk = (fn) => { const c = document.createElement('canvas'); c.width = w; c.height = h; const g = c.getContext('2d', { willReadFrequently: true }); g.fillStyle = g.strokeStyle = '#fff'; fn(g);
            const d = g.getImageData(0, 0, w, h).data, o = []; for (let y = 0; y < h; y += 2) for (let x = 0; x < w; x += 2) if (d[(y * w + x) * 4 + 3] > 140) o.push(x, y); return o; };
        const F = fillFn ? mk(fillFn) : [], E = edgeFn ? mk(edgeFn) : [];
        let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
        for (const L of [F, E]) for (let i = 0; i < L.length; i += 2) { x0 = Math.min(x0, L[i]); x1 = Math.max(x1, L[i]); y0 = Math.min(y0, L[i + 1]); y1 = Math.max(y1, L[i + 1]); }
        const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, pts = new Float32Array(M * 3);
        for (let k = 0; k < M; k++) { const L = (E.length && (!F.length || rnd() < edgeRatio)) ? E : F, i = ((rnd() * (L.length / 2)) | 0) * 2;
            pts[k * 3] = L[i] + (rnd() - 0.5) * 2 - cx; pts[k * 3 + 1] = L[i + 1] + (rnd() - 0.5) * 2 - cy; pts[k * 3 + 2] = (rnd() - 0.5) * 22; }
        return { pts, M, ax: Math.max(1, (x1 - x0) / 2), ay: Math.max(1, (y1 - y0) / 2) };
    }
    function gearPath(g) { const cx = 200, cy = 200, R = 172, r = 138, n = 11, st = TAU / n; g.beginPath(); for (let i = 0; i < n; i++) { const a = i * st; g.lineTo(cx + Math.cos(a - st * 0.3) * r, cy + Math.sin(a - st * 0.3) * r); g.lineTo(cx + Math.cos(a - st * 0.17) * R, cy + Math.sin(a - st * 0.17) * R); g.lineTo(cx + Math.cos(a + st * 0.17) * R, cy + Math.sin(a + st * 0.17) * R); g.lineTo(cx + Math.cos(a + st * 0.3) * r, cy + Math.sin(a + st * 0.3) * r); } g.closePath(); g.moveTo(cx + 62, cy); g.arc(cx, cy, 62, 0, TAU, true); }
    function dropPath(g) { g.beginPath(); g.moveTo(200, 22); g.bezierCurveTo(218, 85, 332, 160, 332, 250); g.bezierCurveTo(332, 330, 272, 382, 200, 382); g.bezierCurveTo(128, 382, 68, 330, 68, 250); g.bezierCurveTo(68, 160, 182, 85, 200, 22); g.closePath(); }
    function heartPath(g) { g.beginPath(); for (let i = 0; i <= 120; i++) { const t = (i / 120) * TAU, x = 16 * Math.pow(Math.sin(t), 3), y = -(13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t)); g[i ? 'lineTo' : 'moveTo'](200 + x * 11, 190 + y * 11); } g.closePath(); }
    const SHAPES = {
        globe() { const M = 3400, pts = new Float32Array(M * 3); let k = 0; const put = (x, y, z) => { if (k < M) { pts[k * 3] = x * 100; pts[k * 3 + 1] = y * 100; pts[k * 3 + 2] = z * 100; k++; } };
            let t = 0; while (k < 1700 && t++ < 200000) { const u = rnd() * 2 - 1, a = rnd() * TAU, s = Math.sqrt(1 - u * u), x = s * Math.cos(a), y = u, z = s * Math.sin(a); if (noise(x * 1.9 + 3, y * 1.9, z * 1.9) > 0.02) put(x, y, z); }
            for (let m = 0; m < 16; m++) { const lon = (m / 16) * TAU; for (let j = 0; j < 64 && k < M; j++) { const la = (j / 63) * Math.PI - Math.PI / 2; put(Math.cos(la) * Math.cos(lon), Math.sin(la), Math.cos(la) * Math.sin(lon)); } }
            for (let p = -4; p <= 4; p++) { const la = p * 0.33; for (let j = 0; j < 84 && k < M; j++) { const lo = (j / 84) * TAU; put(Math.cos(la) * Math.cos(lo), Math.sin(la), Math.cos(la) * Math.sin(lo)); } }
            while (k < M) { const u = rnd() * 2 - 1, a = rnd() * TAU, s = Math.sqrt(1 - u * u); put(s * Math.cos(a), u, s * Math.sin(a)); }
            return { pts, M, ax: 100, ay: 100, rotY: 0.5, tilt: 0.4 }; },
        gear() { return { ...raster(400, 400, (g) => { gearPath(g); g.fill('evenodd'); }, (g) => { gearPath(g); g.lineWidth = 7; g.stroke(); }, 3400, 0.5), rotZ: 0.3 }; },
        drop() { return raster(400, 400, (g) => { dropPath(g); g.fill(); }, (g) => { dropPath(g); g.lineWidth = 8; g.stroke(); }, 3200, 0.45); },
        heart() { return raster(400, 400, (g) => { heartPath(g); g.fill(); }, (g) => { heartPath(g); g.lineWidth = 8; g.stroke(); }, 3200, 0.4); },
        chart() { const P = [[40, 130], [110, 95], [180, 108], [250, 52], [325, 26]]; return raster(440, 320, (g) => { [[40, 150], [110, 110], [180, 125], [250, 70], [320, 45]].forEach(([x, y]) => g.fillRect(x, y, 46, 290 - y)); },
            (g) => { g.lineWidth = 9; g.lineCap = g.lineJoin = 'round'; g.beginPath(); g.moveTo(20, 10); g.lineTo(20, 300); g.lineTo(430, 300); g.moveTo(...P[0]); P.slice(1).forEach((p) => g.lineTo(...p)); g.stroke(); g.beginPath(); P.forEach(([x, y]) => { g.moveTo(x + 11, y); g.arc(x, y, 11, 0, TAU); }); g.fill(); }, 3400, 0.55); },
        doc() { const o = (g) => { g.beginPath(); g.moveTo(90, 30); g.lineTo(255, 30); g.lineTo(325, 100); g.lineTo(325, 370); g.lineTo(90, 370); g.closePath(); };
            return raster(400, 400, (g) => { [[130, 160, 150], [130, 200, 170], [130, 240, 170], [130, 280, 120], [130, 320, 150]].forEach(([x, y, w]) => g.fillRect(x, y, w, 11)); g.beginPath(); g.moveTo(255, 30); g.lineTo(255, 100); g.lineTo(325, 100); g.fill(); },
                (g) => { g.lineWidth = 8; g.lineJoin = 'round'; o(g); g.stroke(); g.beginPath(); g.moveTo(255, 30); g.lineTo(255, 100); g.lineTo(325, 100); g.stroke(); }, 3000, 0.5); },
    };
    function textShape(txt) {
        const f = '700 210px "Segoe UI Variable Display","Segoe UI",system-ui,sans-serif', m = document.createElement('canvas').getContext('2d'); m.font = f;
        const w = Math.ceil(m.measureText(txt).width + 60), h = 300;
        return { ...raster(w, h, (g) => { g.font = f; g.textBaseline = 'middle'; g.textAlign = 'center'; g.fillText(txt, w / 2, h / 2 + 8); },
            (g) => { g.font = f; g.textBaseline = 'middle'; g.textAlign = 'center'; g.lineWidth = 4; g.strokeText(txt, w / 2, h / 2 + 8); }, Math.min(4200, 1600 + txt.length * 260), 0.3), sway: 0.1 };
    }
    const shapeCache = {};
    let shape = null, coh = 0, cohT = 0, angY = 0, angZ = 0, formaNome = '';
    const FRAC = 0.64;
    function forma(nome, texto) {
        if (!api) return;
        if (!nome) { soltar(); return; }
        const chave = nome === 'texto' ? 'texto:' + texto : nome;
        if (chave === formaNome && cohT) return;
        try { shape = shapeCache[chave] || (shapeCache[chave] = nome === 'texto' ? textShape(String(texto).slice(0, 14)) : SHAPES[nome]()); } catch (_) { return; }
        formaNome = chave; cohT = 1; angY = 0; angZ = 0; ring(0, 0, 60, 340, 0.3, 1, 110);
    }
    function soltar() {
        if (!cohT) return; cohT = 0; formaNome = '';
        const nT = Math.floor(N * FRAC); for (let i = 0; i < nT; i++) { const a = rnd() * TAU, s = 60 + rnd() * 160; VX[i] += Math.cos(a) * s; VY[i] += Math.sin(a) * s; }
        ring(0, 0, 40, 520, 1, 1);
    }

    // ---------------------------------------------------------------- ondas, atratores, ponteiro
    const rings = [], atts = [];
    function ring(ox, oy, r, sp, str, imp, w) { rings.push({ ox, oy, r, sp, str, imp, w: w || 70 }); if (rings.length > 6) rings.shift(); }
    const ptr = { x: 0, y: 0, vx: 0, vy: 0, on: false, nx: 0, ny: 0 };
    addEventListener('pointermove', (e) => { const x = e.clientX - W / 2, y = e.clientY - CY; ptr.vx = ptr.vx * 0.5 + (x - ptr.x) * 30; ptr.vy = ptr.vy * 0.5 + (y - ptr.y) * 30; ptr.x = x; ptr.y = y; ptr.on = true; ptr.nx = e.clientX / W - 0.5; ptr.ny = e.clientY / H - 0.5; });
    document.addEventListener('pointerleave', () => { ptr.on = false; });

    // ---------------------------------------------------------------- estados (os do main.js) -> movimento
    const STP = {
        offline: { spread: 0.24, speed: 18, swirl: 6 }, espera: { spread: 0.3, speed: 40, swirl: 14 }, ouvindo: { spread: 0.28, speed: 50, swirl: 28 },
        pensando: { spread: 0.27, speed: 80, swirl: 150 }, falando: { spread: 0.4, speed: 70, swirl: 18 }, cena: { spread: 0.62, speed: 30, swirl: 0, wind: 38 },
    };
    const ZOOM = { offline: 0.96, espera: 1, ouvindo: 0.965, pensando: 1, falando: 1.035, cena: 0.9 };
    const S = { spread: 0.3, speed: 30, swirl: 10, wind: 0 };
    const voz = { a: 0, sA: 0, prev: 0, ultimaOnda: 0, out: false };
    let api = null, estadoAnt = '', cenaOn = false;

    // ---------------------------------------------------------------- laço
    let proxBatida = 6;
    let inited = false, last = performance.now(), time = 0, fpsA = 60, janelaFps = { t: 0, soma: 0, n: 0, bons: 0 };
    const FOV = 900, paths = new Array(48);
    function frame(now) {
        requestAnimationFrame(frame);
        if (innerWidth !== W || innerHeight !== H) resize();
        if (W < 2 || H < 2 || !cv.width || !gv.width) return;
        if (!inited) { inited = true; initP(); }
        let dt = (now - last) / 1000; last = now; if (dt > 0.05) dt = 0.05; if (dt <= 0) return; time += dt;
        qualidade(dt, now);
        const est = (api && api.estado()) || 'espera';
        if (est !== estadoAnt) mudouEstado(est, estadoAnt);
        // voz real: o analisador do áudio dele (falando) ou o nível do microfone (ouvindo)
        const raw = api ? clamp((+api.nivel() || 0) * 0.75, 0, 1) : 0, sai = est === 'falando';      // o analisador satura perto de 1: deixa folga para os picos
        voz.a += (raw - voz.a) * (1 - Math.exp(-dt * (raw > voz.a ? 30 : 7)));
        voz.sA += (voz.a - voz.sA) * (1 - Math.exp(-dt * 1.1)); voz.out = sai;
        if (raw - voz.prev > 0.07 && raw > 0.28 && now / 1000 - voz.ultimaOnda > 0.13 && !reduzido) {
            voz.ultimaOnda = now / 1000;
            if (sai) ring(0, 0, 30, 560, 0.22 + raw * 0.3, 1); else if (est === 'ouvindo') ring(0, 0, Math.max(W, H) * 0.45, -520, 0.15 + raw * 0.25, -1);
        }
        voz.prev = raw;
        document.documentElement.style.setProperty('--amp', voz.a.toFixed(3));
        window.__amp = voz.a;
        const P = STP[cenaOn && est !== 'ouvindo' ? 'cena' : est] || STP.espera, k = 1 - Math.exp(-dt * 2.2);
        S.spread += (P.spread - S.spread) * k; S.speed += (P.speed - S.speed) * k; S.swirl += (P.swirl - S.swirl) * k; S.wind += ((P.wind || 0) - S.wind) * k;
        coh += (cohT - coh) * (1 - Math.exp(-dt * (cohT > coh ? 1.7 : 2.6))); if (coh < 0.002 && !cohT) { coh = 0; shape = null; }
        // vida: em repouso a nuvem RESPIRA (dois ritmos lentos) e de vez em quando dá uma batida leve; trabalhando no terminal, gira mais
        const calmo = (est === 'espera' || est === 'ouvindo') && !cohT, resp = calmo && !reduzido ? Math.sin(time * 1.15) * 0.02 + Math.sin(time * 0.41) * 0.012 : 0;
        if (calmo && !reduzido && time > proxBatida) { proxBatida = time + 7 + rnd() * 6; ring(0, 0, 18, 260, 0.16, 1); setTimeout(() => ring(0, 0, 18, 300, 0.1, 1), 260); }
        if (termAtivo) S.swirl += (90 - S.swirl) * k;
        const mn = Math.min(W, H), mx = Math.max(W, H), R = mn * (S.spread + resp) + mx * 0.2 * voz.sA, spd = S.speed + (sai ? 175 : 80) * voz.a;
        for (let i = rings.length - 1; i >= 0; i--) { const r = rings[i]; r.r += r.sp * dt; r.str *= Math.exp(-dt * 0.9); if (r.r < -20 || r.r > mx * 1.1 || r.str < 0.04) rings.splice(i, 1); }
        for (let i = atts.length - 1; i >= 0; i--) if (now > atts[i].ate) atts.splice(i, 1);
        ptr.vx *= 0.9; ptr.vy *= 0.9;
        let cY = 1, sY = 0, cZ = 1, sZ = 0, cT = 1, sT = 0, SC = 1, M = 1, pts = null;
        if (shape && coh > 0) {
            angY += (shape.rotY || 0) * dt; angZ += (shape.rotZ || 0) * dt; const ay = angY + (shape.sway ? Math.sin(time * 0.6) * shape.sway : 0);
            cY = Math.cos(ay); sY = Math.sin(ay); cZ = Math.cos(angZ); sZ = Math.sin(angZ); cT = Math.cos(shape.tilt || 0); sT = Math.sin(shape.tilt || 0);
            SC = Math.min((W * 0.225) / shape.ax, (H * 0.3) / shape.ay); M = shape.M; pts = shape.pts;
        }
        const nT = pts ? Math.floor(N * FRAC) : 0, br = 1 + voz.a * 0.07 * (sai ? 1 : 0.3);
        const FS = 0.0021, FS2 = 0.0058, e = 0.06, tz = time * 0.13, detalhe = Math.min(1, 0.2 + voz.a * 1.3), w2 = 0.55 * detalhe, PR = 150, PR2 = PR * PR;
        const cx = W / 2, cy = CY;
        cx2.setTransform(DPR, 0, 0, DPR, 0, 0); cx2.clearRect(0, 0, W, H); cx2.globalCompositeOperation = 'lighter'; cx2.lineCap = 'round';
        for (let b = 0; b < 48; b++) paths[b] = null;
        const str = (0.018 + 0.02 * voz.a) * PAL.streak;
        for (let i = 0; i < N; i++) {
            let x = X[i], y = Y[i], z = Z[i], vx = VX[i], vy = VY[i], vz = VZ[i];
            const u = x * FS, v = y * FS, w = z * FS * 0.5 + tz;
            let fx = (noise(u, v + e, w) - noise(u, v - e, w)) / (2 * e), fy = -(noise(u + e, v, w) - noise(u - e, v, w)) / (2 * e);
            const fz = noise(u + 31.4, v + 17.7, w + 9.1) * 0.6;
            if (detalhe > 0.28) { const u2 = x * FS2 + 5.2, v2 = y * FS2 + 1.3, ww = z * FS2 * 0.5 + tz * 2.3; fx += (w2 * (noise(u2, v2 + e, ww) - noise(u2, v2 - e, ww))) / (2 * e); fy -= (w2 * (noise(u2 + e, v2, ww) - noise(u2 - e, v2, ww))) / (2 * e); }
            const d = Math.sqrt(x * x + y * y) + 0.001, ux = x / d, uy = y / d, sd = SD[i];
            // fluxo sem divergência confinado por uma janela que zera na borda (não amontoa em filamentos)
            const Rm = R * (0.55 + 0.9 * sd * sd), ss = (d * d) / (Rm * Rm);
            let gxv = 0, gyv = 0;
            if (ss < 1) { const m = 1 - ss, wv = m * m, gq = (-4 * m) / (Rm * Rm), psi = noise(u, v, w); gxv = wv * fx + (psi * gq * y) / FS; gyv = wv * fy - (psi * gq * x) / FS; }
            let tvx = gxv * spd, tvy = gyv * spd;
            const sw = S.swirl * Math.exp(-(d * d) / (R * R * 1.8)) * (0.5 + sd * 0.8);
            tvx -= uy * sw; tvy += ux * sw; tvx += S.wind * (0.6 + sd * 0.8);
            if (d > Rm) { const o = (d - Rm) * 1.6 * (1 - Math.min(1, S.wind / 38) * 0.92); tvx -= ux * o; tvy -= uy * o; }
            const temAlvo = i < nT, rel = Math.min(0.9, 5.5 * (temAlvo ? 1 - coh * 0.92 : 1) * dt);
            vx += (tvx - vx) * rel; vy += (tvy - vy) * rel; vz += (fz * spd * 0.5 - vz - z * 0.5) * rel; vx += (rnd() - 0.5) * dt * 150; vy += (rnd() - 0.5) * dt * 150;
            if (ptr.on) { const dx = x - ptr.x, dy = y - ptr.y, dd = dx * dx + dy * dy; if (dd < PR2) { const dist = Math.sqrt(dd) + 0.01, f = 1 - dist / PR, ff = f * f * Math.min(1, dt * 9); vx += ((dx / dist) * 170 + ptr.vx * 0.55) * ff; vy += ((dy / dist) * 170 + ptr.vy * 0.55) * ff; } }
            for (let q = 0; q < rings.length; q++) { const r = rings[q], dx = x - r.ox, dy = y - r.oy, dd = Math.sqrt(dx * dx + dy * dy) + 0.01, o = dd - r.r; if (o > -r.w * 3 && o < r.w * 3) { const g = (Math.exp(-(o * o) / (r.w * r.w)) * r.str * r.imp * dt * 520) / dd; vx += dx * g; vy += dy * g; } }
            if (atts.length && (GRP[i] & 7) === 0) for (let q = 0; q < atts.length; q++) { const a = atts[q], dx = a.x - x, dy = a.y - y, da = Math.sqrt(dx * dx + dy * dy) + 0.01, g = Math.exp(-(da * da) / (a.rad * a.rad)) * a.str * dt; vx += ((dx / da) * 340 - (dy / da) * 190) * g; vy += ((dy / da) * 340 + (dx / da) * 190) * g; }
            if (temAlvo) {
                const j = (i % M) * 3, sx = pts[j], sy = pts[j + 1], szz = pts[j + 2];
                let rx = sx * cY + szz * sY, rz = -sx * sY + szz * cY; const ry = sy * cT - rz * sT; rz = sy * sT + rz * cT;
                const qx = rx * cZ - ry * sZ, qy = rx * sZ + ry * cZ, jit = 12 * (1 + 2 * voz.a);
                const tx = qx * SC * br + fx * jit, ty = qy * SC * br + fy * jit, tzz = rz * SC * br, kk = coh * (9 + sd * 16), dm = coh * (5.5 + sd * 2);
                vx += ((tx - x) * kk - vx * dm) * dt; vy += ((ty - y) * kk - vy * dm) * dt; vz += ((tzz - z) * kk - vz * dm) * dt;
            }
            x += vx * dt; y += vy * dt; z += vz * dt;
            if (S.wind > 6 && x > W * 0.56) { x = -W * 0.56; y = (rnd() - 0.5) * H * 0.9; vx = S.wind; }
            X[i] = x; Y[i] = y; Z[i] = z; VX[i] = vx; VY[i] = vy; VZ[i] = vz;
            const pf = FOV / (FOV - clamp(z, -400, 400)), sx2 = cx + x * pf, sy2 = cy + y * pf;
            if (sx2 < -20 || sx2 > W + 20 || sy2 < -20 || sy2 > H + 20) continue;
            const sp = Math.abs(vx) + Math.abs(vy);
            let bl = sp < 50 ? 0 : sp < 150 ? 1 : 2;
            if (voz.a > 0.35 && (i & 31) === 0) bl = 2;
            const sz = BIG[i] ? 3 : pf < 0.88 ? 0 : pf > 1.14 ? 2 : 1, bi = (COL[i] * 3 + bl) * 4 + sz;
            let pth = paths[bi]; if (!pth) pth = paths[bi] = new Path2D();
            const tl = str * pf; pth.moveTo(sx2 - vx * tl, sy2 - vy * tl); pth.lineTo(sx2 + 0.01, sy2);
        }
        for (let b = 0; b < 48; b++) { const pth = paths[b]; if (!pth) continue; const sz = b & 3, bl = (b >> 2) % 3, ci = ((b >> 2) / 3) | 0, c = PAL.cols[ci];
            cx2.strokeStyle = `rgba(${c[0]},${c[1]},${c[2]},${PAL.alpha[bl] * (sz === 3 ? 0.3 : 1)})`; cx2.lineWidth = (sz === 0 ? 1 : sz === 1 ? 1.6 : sz === 2 ? 2.5 : 7) * PAL.size; cx2.stroke(pth); }
        gx.clearRect(0, 0, gv.width, gv.height); gx.drawImage(cv, 0, 0, gv.width, gv.height);
        // cartões flutuam (e seguem um pouco o mouse)
        for (const c of cartoes) { const dx = c.dx + Math.sin(time * c.f1 + c.ph) * 7 - ptr.nx * 16 * c.depth, dy = c.dy + Math.cos(time * c.f2 + c.ph) * 8 - ptr.ny * 12 * c.depth; c.el.style.transform = `translate3d(${dx.toFixed(1)}px,${dy.toFixed(1)}px,0)`; }
        legendaFrame(now);
    }

    // ---------------------------------------------------------------- qualidade automática (a gráfica é a Radeon integrada)
    function qualidade(dt, now) {
        const j = janelaFps; j.soma += dt; j.n++;
        if (now - j.t < 2000) return;
        const fps = j.n / j.soma; j.t = now; j.soma = 0; j.n = 0; fpsA = fps;
        if (document.hidden) return;
        if (fps < 42 && N > 1500) { N = Math.max(1500, Math.round(N * 0.8)); j.bons = 0; }
        else if (fps > 57 && N < NALVO) { if (++j.bons >= 3) { N = Math.min(NALVO, Math.round(N * 1.1)); j.bons = 0; } }
        else j.bons = 0;
    }

    // ---------------------------------------------------------------- reação aos estados
    let soltarT = 0, limparT = 0;
    function mudouEstado(novo, ant) {
        estadoAnt = novo;
        atualizarStatus();
        document.documentElement.style.setProperty('--au-zoom', ZOOM[cenaOn && novo !== 'ouvindo' ? 'cena' : novo] || 1);
        clearTimeout(soltarT);
        if (ant === 'falando' && novo !== 'falando' && novo !== 'pensando') {
            soltarT = setTimeout(soltar, 2500);
            clearTimeout(limparT); limparT = setTimeout(() => { limparCartoes(); fecharCena(); esconderFala(); }, 16000);
        }
        if (novo === 'pensando' && ant !== 'falando') ring(0, 0, 20, 420, 0.4, 1);
    }
    function novoTurno() {                                  // você mandou um pedido novo: o que era do anterior sai de cena
        if (!api) return;
        clearTimeout(limparT); clearTimeout(soltarT); limparCartoes(); fecharCena(); soltar(); actsLimpar();
        turnoN++; [...previasEl.children].forEach((el) => el.classList.add('velha'));          // as miniaturas do pedido anterior esmaecem; somem quando chegar outra pesquisa
    }

    // ---------------------------------------------------------------- chips de atividade
    const ROT = { PESQUISA: 'Pesquisando', PESQUISA_PROFUNDA: 'Pesquisando a fundo', LEITURA: 'Lendo a página', ABRINDO: 'Abrindo', 'VISÃO': 'Olhando a tela', 'NOTÍCIAS': 'Lendo as notícias', PROGRAMA: 'Abrindo o programa',
        COFRE: 'Consultando o Obsidian', MODO: 'Ligando ferramentas', BRIEFING: 'Montando o resumo do dia', CLIMA: 'Consultando o clima', 'CÂMERA': 'Olhando pela câmera',
        'MEMÓRIA': 'Consultando a memória', GESTO: 'Gesto', ALERTA: 'Aviso', CONTROLE: 'Controlando o PC', TERMINAL: 'Executando no PowerShell', AGENDA: 'Olhando a agenda', 'E-MAIL': 'Olhando os e-mails',
        OFICINA: 'Trabalhando na Oficina', ARQUIVOS: 'Mexendo nos arquivos', WINDOWS: 'Mexendo no Windows', JANELA: 'Lendo a janela' };
    const FORMA_DO = { PESQUISA: 'globe', PESQUISA_PROFUNDA: 'globe', 'NOTÍCIAS': 'globe', LEITURA: 'globe', COFRE: 'doc', 'MEMÓRIA': 'doc', PROGRAMA: 'gear', BRIEFING: 'chart', AGENDA: 'chart', ARQUIVOS: 'doc' };
    const FORMA_TEXTO = { TERMINAL: '>_', OFICINA: '</>' };            // a nuvem vira o símbolo do que ele está fazendo
    const chips = new Map();
    const seg = (ms) => (ms < 10000 ? (ms / 1000).toFixed(1) : Math.round(ms / 1000)).toString().replace('.', ',') + ' s';
    function ferramenta(m) {
        if (!api || !m || !m.id) return;
        if (m.estado === 'inicio') {
            const el = document.createElement('div'); el.className = 'au-act';
            const rot = String(m.rotulo || '').toUpperCase(), nome = ROT[rot] || (rot ? rot.charAt(0) + rot.slice(1).toLowerCase() : 'Trabalhando');
            el.innerHTML = '<i class="au-spin"></i><span></span><small class="au-tm"></small>';
            el.children[1].textContent = nome; if (m.detalhe) { const em = document.createElement('em'); em.textContent = ' · ' + String(m.detalhe).slice(0, 60); el.children[1].appendChild(em); }
            el.dataset.t0 = performance.now();
            actsEl.appendChild(el); requestAnimationFrame(() => el.classList.add('in'));
            chips.set(m.id, el); while (actsEl.children.length > 4) actsEl.firstChild.remove();
            if (FORMA_TEXTO[rot]) forma('texto', FORMA_TEXTO[rot]); else if (FORMA_DO[rot]) forma(FORMA_DO[rot]);
            ring(0, 0, 30, 460, 0.3, 1);
            setTimeout(() => { if (chips.get(m.id) === el) fimChip(m.id, 'fim'); }, rot === 'TERMINAL' ? 600000 : 30000);
        } else fimChip(m.id, m.estado);
    }
    function fimChip(id, estado) {
        const el = chips.get(id); if (!el) return; chips.delete(id);
        el.firstChild.className = estado === 'erro' ? 'au-x' : 'au-tick';
        el.classList.add(estado === 'erro' ? 'erro' : 'ok');
        const tm = el.querySelector('.au-tm'); if (tm) tm.textContent = seg(performance.now() - +el.dataset.t0);
        setTimeout(() => { el.classList.add('fade'); setTimeout(() => el.remove(), 600); }, 2600);
    }
    setInterval(() => {                                          // relógio dos chips em andamento: você vê há quanto tempo ele está nisso
        const agora = performance.now();
        for (const el of chips.values()) { const d = agora - +el.dataset.t0, tm = el.querySelector('.au-tm'); if (tm && d > 1200) tm.textContent = seg(d); }
    }, 250);

    // ---------------------------------------------------------------- terminal ao vivo (espelha a janela do PowerShell que abriu na tela)
    const terms = new Map();
    let termAtivo = 0;
    const NIVEL_TXT = { leitura: 'só leitura', oficina: 'Oficina', 'oficina (guarda)': 'Oficina · guarda', risco: 'risco · você confirmou' };
    function terminal(m) {
        if (!api || !m || !m.id) return;
        if (m.inicio) return abrirTerm(m);
        const t = terms.get(m.id); if (!t) return;
        if (m.linhas) addLinhas(t, m.linhas);
        if (m.fim) fecharTerm(t, m);
    }
    function abrirTerm(m) {
        while (terms.size >= 2) { const [id, velho] = terms.entries().next().value; tirarTerm(velho); terms.delete(id); }
        const el = document.createElement('div'); el.className = 'au-term rodando nv-' + String(m.nivel || '').split(' ')[0];
        el.innerHTML = `<div class="au-th">${ICON.term}<b></b><span class="au-nv"></span><span class="au-tt">0,0 s</span><button class="au-fechar" title="Fechar">×</button></div>
            <div class="au-tcmd"><span>PS&gt;</span><code></code></div><div class="au-tout"></div>
            <div class="au-tfoot"><i class="au-led"></i><span></span></div>`;
        el.querySelector('b').textContent = m.titulo || 'terminal';
        el.querySelector('.au-nv').textContent = NIVEL_TXT[m.nivel] || m.nivel || '';
        el.querySelector('code').textContent = String(m.comando || '').split('\n').slice(0, 4).join('\n');
        el.querySelector('.au-tfoot span').textContent = m.visivel ? 'rodando · a janela do PowerShell está aberta na tela' : 'rodando';
        termsEl.appendChild(el);
        const t = { id: m.id, el, out: el.querySelector('.au-tout'), t0: performance.now(), n: 0 };
        t.relogio = setInterval(() => { el.querySelector('.au-tt').textContent = seg(performance.now() - t.t0); }, 100);
        el.querySelector('.au-fechar').addEventListener('click', () => { tirarTerm(t); terms.delete(t.id); });
        terms.set(m.id, t); termAtivo++;
        const r = el.getBoundingClientRect(), dx = W / 2 - (r.left + r.width / 2), dy = CY - (r.top + r.height / 2);
        if (!reduzido) el.animate([{ transform: `translate(${dx}px,${dy}px) scale(.12)`, opacity: 0, filter: 'blur(14px)' }, { opacity: 1, offset: 0.4 }, { transform: 'none', opacity: 1, filter: 'blur(0px)' }], { duration: 1100, easing: SPRING });
        atts.push({ x: r.left + r.width / 2 - W / 2, y: r.top + r.height / 2 - CY, rad: 240, str: 1.2, ate: performance.now() + 1400 });
        ring(0, 0, 30, 520, 0.4, 1); forma('texto', '>_'); atualizarStatus();
    }
    function addLinhas(t, linhas) {
        const frag = document.createDocumentFragment();
        linhas.forEach((l, k) => {
            const d = document.createElement('div'); d.textContent = l || ' '; d.style.animationDelay = (k * 0.035).toFixed(3) + 's';
            if (/\[GUARDA DO JARVIS\]|traceback|error|erro|exception|falhou|denied|negad/i.test(l)) d.className = 'err';
            else if (/\b(ok|sucesso|conclu[ií]d|pronto|criad[oa]|done)\b/i.test(l)) d.className = 'ok';
            frag.appendChild(d); t.n++;
        });
        t.out.appendChild(frag);
        while (t.out.children.length > 160) t.out.firstChild.remove();
        t.out.scrollTop = t.out.scrollHeight;
        if (!reduzido && (t.n & 3) === 0) ring(0, 0, 24, 300, 0.12, 1);
    }
    function fecharTerm(t, m) {
        clearInterval(t.relogio); termAtivo = Math.max(0, termAtivo - 1);
        const ok = m.situacao === 'ok' && m.codigo === 0;
        t.el.classList.remove('rodando'); t.el.classList.add(ok ? 'ok' : 'erro');
        t.el.querySelector('.au-tt').textContent = seg((m.segundos || 0) * 1000);
        t.el.querySelector('.au-tfoot span').textContent = m.situacao === 'tempo' ? 'passou do tempo máximo e foi encerrado'
            : m.situacao === 'fechada' ? 'a janela foi fechada antes do fim' : ok ? 'concluído sem erros' : `terminou com código ${m.codigo}`;
        ring(0, 0, 30, 560, ok ? 0.5 : 0.35, 1); atualizarStatus();
        t.fim = setTimeout(() => { tirarTerm(t); terms.delete(t.id); }, 45000);
    }
    function tirarTerm(t) {
        clearInterval(t.relogio); clearTimeout(t.fim); if (t.el.classList.contains('rodando')) termAtivo = Math.max(0, termAtivo - 1);
        t.el.classList.add('sai'); setTimeout(() => t.el.remove(), 600); atualizarStatus();
    }

    // ---------------------------------------------------------------- Oficina: o código que ele acabou de escrever aparece num cartão
    function realce(linhaEsc) {                    // a linha JÁ vem escapada (&lt; &#39;...): só colore palavra-chave e comentário
        const c = linhaEsc.search(/(^|\s)(#|\/\/)(?!\d+;)/);
        const corpo = c >= 0 ? linhaEsc.slice(0, c) : linhaEsc, com = c >= 0 ? linhaEsc.slice(c) : '';
        return corpo.replace(/(&[a-z#0-9]+;)|\b(def|class|import|from|return|if|elif|else|for|while|try|except|finally|with|as|in|not|and|or|True|False|None|async|await|lambda|function|const|let|var|new|this|param|foreach|switch)\b/g,
            (m0, ent, kw) => (ent ? ent : `<b class="k">${kw}</b>`)) + (com ? `<em class="cm">${com}</em>` : '');
    }
    function oficina(m) {
        if (!api || !m) return;
        if (m.evento === 'abriu') { ring(0, 0, 30, 520, 0.4, 1); return; }
        if (m.evento !== 'arquivo') return;
        const linhas = String(m.previa || '').split('\n').slice(0, 22);
        const corpo = linhas.map((l, i) => `<span class="ln" style="--d:${(0.25 + i * 0.07).toFixed(2)}s"><i>${i + 1}</i>${realce(esc(l)) || ' '}</span>`).join('');
        const html = `<div class="au-ch">${ICON.code}<b title="${esc(m.caminho)}">${esc(m.caminho)}</b><button class="au-fechar" title="Fechar">×</button></div>
            <div class="au-csub"><span class="au-tag ${m.novo ? 'novo' : ''}">${m.novo ? 'novo' : 'atualizado'}</span>${esc(m.linhas)} linhas · Oficina</div>
            <pre class="au-code">${corpo}</pre>`;
        const o = cartao(html, 'tr'); if (o) o.el.classList.add('au-cw-code');
        forma('texto', '</>');
    }

    // ---------------------------------------------------------------- linha de estado (o que ele está fazendo AGORA) e alerta de confirmação
    const ROT_EST = { espera: 'pronto', ouvindo: 'ouvindo você', pensando: 'pensando', falando: 'falando', offline: 'sem conexão' };
    let confAberta = '', palSalva = null;
    function atualizarStatus() {
        if (!statusEl) return;
        const e = confAberta ? 'conf' : termAtivo ? 'term' : (estadoAnt || 'espera');
        const txt = confAberta ? (confAberta === 'alto' ? 'ação arriscada · diga “confirmo” ou “cancela”' : 'aguardando sua confirmação')
            : termAtivo ? 'executando no PowerShell' : (ROT_EST[e] || e);
        if (statusEl.dataset.e === e && statusEl.lastChild.textContent === txt) return;
        statusEl.dataset.e = e; statusEl.lastChild.textContent = txt;
        statusEl.classList.remove('troca'); void statusEl.offsetWidth; statusEl.classList.add('troca');
    }
    function observarConfirmacao() {
        const c = document.getElementById('confirmacao'); if (!c) return;
        new MutationObserver(() => {
            const n = c.hidden ? '' : (c.classList.contains('alto') ? 'alto' : 'medio');
            if (n === confAberta) return;
            confAberta = n; alerta(n); atualizarStatus();
        }).observe(c, { attributes: true, attributeFilter: ['hidden', 'class'] });
    }
    function alerta(n) {                            // a nuvem esquenta (âmbar; vermelho se for arriscado) enquanto espera o seu sim/não
        if (n) {
            if (!palSalva) palSalva = PAL.cols.map((c) => c.slice());
            const cor = n === 'alto' ? [[255, 92, 112], [255, 168, 92]] : [[255, 186, 84], [255, 228, 150]];
            PAL.cols[0] = cor[0]; PAL.cols[1] = cor[1];
            document.body.classList.add('au-alerta'); document.body.classList.toggle('au-alerta-alto', n === 'alto');
            ring(0, 0, 30, 480, 0.6, 1); atts.push({ x: 0, y: 0, rad: 260, str: -1.4, ate: performance.now() + 600 });
        } else if (palSalva) {
            palSalva.forEach((c, i) => { PAL.cols[i] = c; }); palSalva = null;
            document.body.classList.remove('au-alerta', 'au-alerta-alto');
            ring(0, 0, 20, 560, 0.4, 1);
        }
    }
    function actsLimpar() { chips.clear(); [...actsEl.children].forEach((e) => { e.classList.add('fade'); setTimeout(() => e.remove(), 500); }); }

    // ---------------------------------------------------------------- cartões (nascem do núcleo, voltam para ele)
    const cartoes = [], SLOTS = ['tl', 'tr', 'br', 'bl'];
    const SPRING = (() => { const f = (t) => 1 - Math.exp(-6.2 * t * 1.25) * Math.cos(9.5 * t * 1.25), p = []; for (let i = 0; i <= 48; i++) p.push(f((i / 48) * 1.6).toFixed(4)); const s = 'linear(' + p.join(',') + ')'; return CSS.supports('animation-timing-function', s) ? s : 'cubic-bezier(.2,.9,.25,1.15)'; })();
    const esc = (t) => String(t == null ? '' : t).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    function cartao(html, slot) {
        if (cartoes.length >= 4) tirarCartao(cartoes[0]);
        const usado = new Set(cartoes.map((c) => c.slot)); slot = slot && !usado.has(slot) ? slot : SLOTS.find((s) => !usado.has(s)) || 'tr';
        const w = document.createElement('div'); w.className = 'au-cw au-' + slot;
        w.innerHTML = `<div class="au-card">${html}</div>`; cardsEl.appendChild(w);
        const o = { el: w, slot, ph: rnd() * TAU, f1: 0.3 + rnd() * 0.25, f2: 0.28 + rnd() * 0.25, dx: 0, dy: 0, depth: 0.6 + rnd() };
        cartoes.push(o);
        const inner = w.firstElementChild, r = w.getBoundingClientRect(), dx = W / 2 - (r.left + r.width / 2), dy = CY - (r.top + r.height / 2);
        if (!reduzido) inner.animate([{ transform: `translate(${dx}px,${dy}px) scale(.12) rotate(${dx > 0 ? -8 : 8}deg)`, opacity: 0, filter: 'blur(16px)' }, { opacity: 1, offset: 0.35 }, { transform: 'none', opacity: 1, filter: 'blur(0px)' }], { duration: 1250, easing: SPRING, fill: 'backwards' });
        ring(0, 0, 40, 520, 0.35, 1);
        atts.push({ x: r.left + r.width / 2 - W / 2, y: r.top + r.height / 2 - CY, rad: 230, str: 1.1, ate: performance.now() + 1500 });
        const fechar = w.querySelector('.au-fechar'); if (fechar) fechar.addEventListener('click', (ev) => { ev.stopPropagation(); tirarCartao(o); });
        w.addEventListener('pointerdown', (e) => {
            if (e.target.closest('.au-fechar')) return;
            const sx = e.clientX - o.dx, sy = e.clientY - o.dy; w.classList.add('drag'); w.setPointerCapture(e.pointerId);
            const mv = (ev) => { o.dx = ev.clientX - sx; o.dy = ev.clientY - sy; }, up = () => { w.classList.remove('drag'); w.removeEventListener('pointermove', mv); w.removeEventListener('pointerup', up); };
            w.addEventListener('pointermove', mv); w.addEventListener('pointerup', up);
        });
        return o;
    }
    function tirarCartao(o, atraso = 0) {
        const i = cartoes.indexOf(o); if (i < 0) return; cartoes.splice(i, 1);
        const inner = o.el.firstElementChild, r = o.el.getBoundingClientRect(), dx = W / 2 - (r.left + r.width / 2), dy = CY - (r.top + r.height / 2);
        o.el.style.pointerEvents = 'none';
        const an = inner.animate([{ transform: 'none', opacity: 1, filter: 'blur(0px)' }, { transform: `translate(${dx}px,${dy}px) scale(.08)`, opacity: 0, filter: 'blur(12px)' }], { duration: 700, delay: atraso, easing: 'cubic-bezier(.55,0,.75,.25)', fill: 'forwards' });
        an.onfinish = () => { o.el.querySelectorAll('img').forEach((im) => { if (im.src.startsWith('blob:')) URL.revokeObjectURL(im.src); }); o.el.remove(); };
    }
    function limparCartoes() {
        const n = cartoes.length; [...cartoes].reverse().forEach((c, k) => tirarCartao(c, k * 70));
        if (n) setTimeout(() => { ring(0, 0, 20, 560, 0.55, 1); atts.push({ x: 0, y: 0, rad: 200, str: -1.2, ate: performance.now() + 500 }); }, 700 + n * 70);
    }
    const CORES = ['#2f6fed', '#e8453c', '#f59e0b', '#1fa971', '#6d4cff', '#e11d74'];
    // miniatura de página no canto: nasce da nuvem, fica até a próxima pesquisa (ou 5 min); clique abre no Chrome do Jarvis
    function previa(m) {
        if (!m.url) return;
        [...previasEl.children].forEach((el) => { if (+el.dataset.turno !== turnoN) el.remove(); });
        if ([...previasEl.children].some((el) => el.dataset.url === m.url)) return;
        while (previasEl.children.length >= 3) previasEl.firstElementChild.remove();
        const el = document.createElement('div'); el.className = 'au-pv'; el.dataset.url = m.url; el.dataset.turno = turnoN; el.title = 'Abrir no navegador';
        const site = String(m.site || '').slice(0, 40);
        el.innerHTML = `<div class="im"></div><div class="tx"><b></b><small><span></span><i>abrir ↗</i></small></div><button class="x" title="Fechar">×</button>`;
        const im = el.querySelector('.im');
        if (m.imagem) im.style.backgroundImage = `url(data:image/jpeg;base64,${m.imagem})`; else im.textContent = (site[0] || '?').toUpperCase();
        el.querySelector('b').textContent = m.titulo || site; el.querySelector('small span').textContent = site;
        el.querySelector('.x').addEventListener('click', (ev) => { ev.stopPropagation(); el.remove(); });
        el.addEventListener('click', () => {
            if (window.__jarvis && __jarvis.enviar) __jarvis.enviar({ tipo: 'abrir_pagina', url: m.url });
            el.classList.add('abrindo'); setTimeout(() => el.classList.remove('abrindo'), 1500);
        });
        previasEl.appendChild(el);
        const r = el.getBoundingClientRect(), dx = W / 2 - (r.left + r.width / 2), dy = CY - (r.top + r.height / 2);
        if (!reduzido) el.animate([{ transform: `translate(${dx}px,${dy}px) scale(.15)`, opacity: 0, filter: 'blur(12px)' }, { opacity: 1, offset: 0.4 }, { transform: 'none', opacity: 1, filter: 'blur(0px)' }], { duration: 1100, easing: SPRING });
        atts.push({ x: r.left + r.width / 2 - W / 2, y: r.top + r.height / 2 - CY, rad: 200, str: 1, ate: performance.now() + 1200 });
        setTimeout(() => el.remove(), 5 * 60 * 1000);
    }
    function cartaoServidor(m) {
        if (!api) return;
        if (m.cartao === 'pagina') { previa(m); return; }
        if (m.cartao === 'fontes' && Array.isArray(m.fontes) && m.fontes.length) {
            const lis = m.fontes.slice(0, 6).map((f, i) => `<li style="--d:${i * 0.35}s"><span class="au-fav" style="background:${CORES[i % CORES.length]}">${esc((f.site || '?')[0].toUpperCase())}</span><span title="${esc(f.titulo)}">${esc(f.site || f.titulo)}</span><i class="au-ld"></i></li>`).join('');
            cartao(`<div class="au-ch">${ICON.search}<b>${esc(m.titulo || 'Fontes')}</b><button class="au-fechar" title="Fechar">×</button></div><ul class="au-src">${lis}</ul>`, 'tl');
        }
    }

    // ---------------------------------------------------------------- cena 3D (clima)
    let mod3d = null;
    function cena(m) {
        if (!api) return;
        if (m.cena !== 'clima' || !Array.isArray(m.cidades) || !m.cidades.length) return;
        soltar(); limparCartoes(); cenaOn = true; document.body.classList.add('au-cena');
        document.documentElement.style.setProperty('--au-zoom', ZOOM.cena);
        (mod3d ? Promise.resolve(mod3d) : import('/static/clima3d.js').then((x) => (mod3d = x))).then((x) => { if (cenaOn) x.mostrar(m.cidades); })
            .catch((e) => { console.warn('cena 3D indisponível:', e); fecharCena(); });
    }
    function fecharCena() {
        if (!cenaOn) return; cenaOn = false; document.body.classList.remove('au-cena', 'au-raio');
        if (mod3d) mod3d.esconder();
        document.documentElement.style.setProperty('--au-zoom', ZOOM[estadoAnt] || 1);
    }

    // ---------------------------------------------------------------- legenda (espelha #legenda-jarvis / #legenda-voce do main.js)
    let palavras = [], revelar = [], revelarEm = 0, escondeT = 0;
    function observarLegendas() {
        const lj = document.getElementById('legenda-jarvis'), lv = document.getElementById('legenda-voce');
        if (lj) new MutationObserver(() => mostrarFala(lj.textContent)).observe(lj, { childList: true, characterData: true, subtree: true });
        if (lv) new MutationObserver(() => mostrarVoce(lv.textContent, lv.classList.contains('parcial'))).observe(lv, { childList: true, characterData: true, subtree: true, attributes: true });
    }
    function mostrarFala(texto) {
        clearTimeout(escondeT);
        texto = String(texto || '').trim();
        if (!texto) { esconderFala(); return; }
        const antes = palavras.map((p) => p.t).join(' '), novas = texto.split(/\s+/);
        // o main.js mostra as 2 últimas frases: o que já estava na tela continua aceso; o resto entra no ritmo da fala
        let comum = 0; const velhas = antes.split(/\s+/);
        for (let k = Math.max(0, velhas.length - novas.length); k <= velhas.length; k++) { const tail = velhas.slice(k); if (tail.length && tail.every((w, i) => novas[i] === w)) { comum = tail.length; break; } }
        falaEl.innerHTML = ''; palavras = []; revelar = [];
        novas.forEach((t, i) => { const s = document.createElement('span'); s.textContent = t + ' '; falaEl.appendChild(s); palavras.push({ t, el: s }); if (i < comum) s.classList.add('on'); else revelar.push(s); });
        revelarEm = performance.now(); falaEl.classList.add('show');
    }
    function legendaFrame(now) {
        if (!revelar.length) return;
        const ritmo = estadoAnt === 'falando' ? 330 : 60;
        while (revelar.length && now - revelarEm > ritmo) { revelar.shift().classList.add('on'); revelarEm += ritmo; }
        if (now - revelarEm > 1000) revelarEm = now - ritmo;
    }
    function esconderFala() { falaEl.classList.remove('show'); voceEl.style.opacity = 0; }
    function mostrarVoce(texto, parcial) {
        texto = String(texto || '').trim();
        if (!texto) { voceEl.style.opacity = 0; return; }
        voceEl.style.opacity = 1; voceEl.classList.toggle('parcial', !!parcial);
        voceEl.innerHTML = '<b>Você</b><span></span>'; voceEl.lastChild.textContent = texto.slice(0, 220);
    }

    // ---------------------------------------------------------------- barra de baixo: texto + anexos temporários
    let anexos = [];
    const TEXTO_EXT = /\.(txt|md|csv|json|log|py|js|ts|html?|css|xml|ya?ml|ini|sql)$/i;
    const kb = (n) => (n < 1024 ? n + ' B' : n < 1048576 ? (n / 1024).toFixed(0) + ' KB' : (n / 1048576).toFixed(1) + ' MB');
    function ligarComposer() {
        $('#au-form').addEventListener('submit', (e) => { e.preventDefault(); enviar(); });
        msgEl.addEventListener('input', () => { atualizarEnviar(); ring(0, H * 0.5 - CY, 10, 260, 0.07, 1, 45); });
        msgEl.addEventListener('keydown', (e) => { if (e.key === 'Escape') msgEl.blur(); });
        $('#au-clip').addEventListener('click', () => $('#au-file').click());
        $('#au-file').addEventListener('change', (e) => { adicionar(e.target.files); e.target.value = ''; });
        $('#au-mic').addEventListener('click', () => { const p = document.querySelector('.status-pill'); if (p) p.click(); });
        let n = 0; const drop = $('#au-drop');
        addEventListener('dragenter', (e) => { if (!e.dataTransfer || ![...e.dataTransfer.types].includes('Files')) return; e.preventDefault(); n++; drop.classList.add('on'); });
        addEventListener('dragleave', () => { n = Math.max(0, n - 1); if (!n) drop.classList.remove('on'); });
        addEventListener('dragover', (e) => e.preventDefault());
        addEventListener('drop', (e) => { e.preventDefault(); n = 0; drop.classList.remove('on'); if (e.dataTransfer && e.dataTransfer.files.length) adicionar(e.dataTransfer.files); });
        addEventListener('paste', (e) => { const fs = [...((e.clipboardData && e.clipboardData.files) || [])]; if (fs.length) { e.preventDefault(); adicionar(fs); } });
        addEventListener('beforeunload', () => anexos.forEach((a) => a.url && URL.revokeObjectURL(a.url)));
    }
    function atualizarEnviar() { sendEl.classList.toggle('ready', !!(msgEl.value.trim() || anexos.some((a) => a.ok))); }
    function adicionar(lista) {
        for (const f of lista) {
            if (anexos.length >= 4) break;
            const img = /^image\//.test(f.type), txt = !img && (/^text\//.test(f.type) || TEXTO_EXT.test(f.name)) && f.size <= 400 * 1024;
            anexos.push({ arquivo: f, nome: f.name || 'anexo', tamanho: f.size, img, ok: img || txt, url: img ? URL.createObjectURL(f) : null,
                motivo: img || txt ? '' : (f.size > 400 * 1024 ? 'grande demais' : 'tipo ainda não suportado') });
        }
        desenharBandeja();
        atts.push({ x: 0, y: H * 0.5 - CY - 40, rad: 300, str: 1.3, ate: performance.now() + 1300 }); ring(0, H * 0.5 - CY, 20, 420, 0.25, 1, 60);
    }
    function desenharBandeja() {
        trayEl.innerHTML = '';
        anexos.forEach((a) => {
            const c = document.createElement('div'); c.className = 'au-chip' + (a.ok ? '' : ' ruim');
            const ext = (a.nome.split('.').pop() || 'ARQ').slice(0, 4).toUpperCase();
            c.innerHTML = (a.url ? `<img class="th" src="${a.url}" alt="">` : `<div class="th">${esc(ext)}</div>`) + `<div class="nm"><b></b><small></small></div><button type="button" class="x" title="Remover">×</button>`;
            c.querySelector('b').textContent = a.nome; c.querySelector('small').textContent = a.ok ? 'temporário · ' + kb(a.tamanho) : a.motivo;
            c.querySelector('.x').onclick = () => { anexos = anexos.filter((z) => z !== a); if (a.url) URL.revokeObjectURL(a.url); desenharBandeja(); };
            trayEl.appendChild(c);
        });
        atualizarEnviar(); resize();
    }
    function imagemParaB64(arquivo) {
        return new Promise((ok, falha) => {
            const im = new Image(), url = URL.createObjectURL(arquivo);
            im.onload = () => { const lado = 1568, s = Math.min(1, lado / Math.max(im.width, im.height)), c = document.createElement('canvas');
                c.width = Math.max(1, Math.round(im.width * s)); c.height = Math.max(1, Math.round(im.height * s)); c.getContext('2d').drawImage(im, 0, 0, c.width, c.height);
                URL.revokeObjectURL(url); ok(c.toDataURL('image/jpeg', 0.85).split(',')[1]); };
            im.onerror = () => { URL.revokeObjectURL(url); falha(new Error('imagem inválida')); };
            im.src = url;
        });
    }
    async function enviar() {
        const texto = msgEl.value.trim(), lista = anexos.filter((a) => a.ok);
        if (!texto && !lista.length) return;
        if (!window.__jarvis || !__jarvis.enviarFala) return;
        const payload = [];
        for (const a of lista) {
            try {
                if (a.img) payload.push({ tipo: 'imagem', nome: a.nome, dados: await imagemParaB64(a.arquivo) });
                else payload.push({ tipo: 'texto', nome: a.nome, texto: (await a.arquivo.text()).slice(0, 40000) });
            } catch (_) { /* arquivo ilegível: segue sem ele */ }
        }
        msgEl.value = ''; msgEl.blur();
        const mostrar = lista; anexos.filter((a) => !a.ok && a.url).forEach((a) => URL.revokeObjectURL(a.url)); anexos = []; desenharBandeja();
        __jarvis.enviarFala(texto || 'Veja o que anexei.', payload.length ? payload : undefined);
        // o que foi anexado aparece flutuando enquanto ele lê (as prévias somem com o cartão; nada fica salvo)
        mostrar.forEach((a, i) => {
            if (a.url) cartao(`<div class="au-ch">${ICON.img}<b>${esc(a.nome)}</b><button class="au-fechar" title="Fechar">×</button></div><div class="au-imgw"><img src="${a.url}" alt=""><div class="au-scan"></div></div>`, i ? 'bl' : 'tr');
            else cartao(`<div class="au-ch">${ICON.file}<b>Arquivo</b><button class="au-fechar" title="Fechar">×</button></div><div class="au-file"><div class="au-fico">${esc((a.nome.split('.').pop() || 'ARQ').slice(0, 4).toUpperCase())}</div><div><b>${esc(a.nome)}</b><small>${kb(a.tamanho)} · lendo…</small></div></div>`, i ? 'bl' : 'tr');
        });
        if (mostrar.length) forma('doc');
    }

    // ---------------------------------------------------------------- tema por voz ("tema vermelho") tinge as partículas
    function definirTema(base, claro) {
        if (!base || (base[0] === 0 && base[1] === 229 && base[2] === 255)) { PAL.cols[0] = [120, 138, 255]; PAL.cols[1] = [56, 225, 255]; document.body.style.removeProperty('--au-acc'); return; }
        PAL.cols[0] = base.slice(); PAL.cols[1] = (claro || base).slice(); document.body.style.setProperty('--au-acc', `rgb(${base.join(',')})`);
    }

    // ---------------------------------------------------------------- partida
    function iniciar(_canvasAntigo, apiReator) {
        api = apiReator;
        document.body.classList.add('aurora');
        montarDOM(); resize();
        observarConfirmacao();
        window.Cena3D = { pulso: (f) => ring(0, 0, 30, 560, 0.4 * (f || 1), 1), ambiente() {}, definirTema() {} };     // acoes.js/ui.js chamam isso
        requestAnimationFrame(frame);
    }

    window.Aurora = {
        iniciar, definirTema, ferramenta, cartao: cartaoServidor, cena, novoTurno, forma, terminal, oficina,
        focar: () => { if (msgEl) { msgEl.focus(); return true; } return false; },
        fps: () => Math.round(fpsA), particulas: () => N,
    };
})();
