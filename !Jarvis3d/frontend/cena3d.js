// Cena 3D do Jarvis (Three.js): o reator em 3D de verdade (profundidade, luz, órbitas, partículas, brilho) com a mesma API do
// reator 2D: iniciar(canvas, { estado, nivel, espectro, emocao, estilo, brilho }, { ref }). `ref` = elemento que marca onde o
// reator fica na tela (o 3D alinha o centro e o tamanho a ele). Devolve { introMs, definirTema, destruir }.
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

const TAU = Math.PI * 2;
const CORES = { base: [0, 229, 255], claro: [125, 249, 255], ambar: [255, 183, 3], erro: [255, 77, 109] };
const EMO = {
    animado: { cor: [80, 255, 170], giro: 1.3 }, adrenalina: { cor: [255, 70, 60], giro: 3.4 }, triunfante: { cor: [255, 215, 64], giro: 1.1 },
    preocupado: { cor: [255, 140, 0], giro: 0.7 }, sarcastico: { cor: [190, 130, 255], giro: 0.9 }, risada: { cor: [150, 255, 110], giro: 1.5 },
    curioso: { cor: [70, 170, 255], giro: 1.0 }, irritado: { cor: [255, 70, 150], giro: 2.2 }, suspiro: { cor: [150, 170, 205], giro: 0.5 },
};
const PERFIL = {
    offline: { giro: 0.05, brilho: 0.25, arcos: 'erro' }, espera: { giro: 0.18, brilho: 0.55, arcos: 'base' },
    ouvindo: { giro: 0.35, brilho: 0.8, arcos: 'base' }, pensando: { giro: 1.9, brilho: 0.9, arcos: 'ambar' }, falando: { giro: 0.55, brilho: 1.0, arcos: 'claro' },
};
const INTRO_S = 3.8;

const lerp = (a, b, k) => a + (b - a) * k;
const mix = (a, b, k) => [lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k)];
const clamp01 = (x) => Math.max(0, Math.min(1, x));
const easeOut = (x) => 1 - Math.pow(1 - clamp01(x), 3);
const easeBack = (x) => { x = clamp01(x); const c = 1.4; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); };

export function definirTema(base, claro) { CORES.base = base.slice(); CORES.claro = claro.slice(); }

function texturaHalo() {
    const c = document.createElement('canvas'); c.width = c.height = 128;
    const g = c.getContext('2d'), r = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(0.25, 'rgba(255,255,255,.45)'); r.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = r; g.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(c);
}

export function iniciar(canvas, api, opcoes = {}) {
    const ref = opcoes.ref || canvas;
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'low-power' });
    renderer.setClearColor(0x02060d, 1);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.82;
    let pr = Math.min(window.devicePixelRatio || 1, 1.5);
    renderer.setPixelRatio(pr);

    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x02060d, 0.045);
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 80);
    const CAM_Z = 7;
    camera.position.set(0, 0, 13);

    scene.add(new THREE.AmbientLight(0x4d7f92, 0.55));
    const luzCentro = new THREE.PointLight(0x00e5ff, 8, 9, 1.8); luzCentro.position.set(0, 0, 0.7); scene.add(luzCentro);
    const luzFrente = new THREE.DirectionalLight(0x9fdfff, 0.9); luzFrente.position.set(2, 3, 6); scene.add(luzFrente);

    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.4, 0.5, 0.55);
    composer.addPass(bloom);
    composer.addPass(new OutputPass());
    let usarBloom = true;

    const cor = new THREE.Color(), corClara = new THREE.Color(), corAcento = new THREE.Color();
    const brilhoMat = (c, mult = 1) => new THREE.MeshBasicMaterial({ color: c.clone().multiplyScalar(mult), toneMapped: true, transparent: true, depthWrite: false });
    const todosBrilhos = [];                                      // materiais que seguem a cor do estado (cor, multiplicador)
    const brilho = (mult, opacidade = 1, acento = false) => { const m = new THREE.MeshBasicMaterial({ transparent: true, opacity: opacidade, depthWrite: false }); todosBrilhos.push({ m, mult, acento }); return m; };

    // ---------------------------------------------------------------- o reator
    const raiz = new THREE.Group(); scene.add(raiz);              // posiciona e escala no lugar do elemento de referência
    const eixo = new THREE.Group(); raiz.add(eixo);               // inclina com o mouse

    const placa = new THREE.Mesh(new THREE.CylinderGeometry(0.66, 0.66, 0.07, 64), new THREE.MeshStandardMaterial({ color: 0x071a24, metalness: 0.9, roughness: 0.4 }));
    placa.rotation.x = Math.PI / 2; placa.position.z = -0.1; eixo.add(placa);
    const aroPlaca = new THREE.Mesh(new THREE.TorusGeometry(0.66, 0.025, 12, 96), new THREE.MeshStandardMaterial({ color: 0x1a4a5e, metalness: 1, roughness: 0.25, emissive: 0x00a5c0, emissiveIntensity: 0.25 }));
    aroPlaca.position.z = -0.08; eixo.add(aroPlaca);

    const nucleoMat = brilho(1.45, 1, true);
    const nucleo = new THREE.Mesh(new THREE.IcosahedronGeometry(0.2, 3), nucleoMat); eixo.add(nucleo);
    const nucleoInterno = new THREE.Mesh(new THREE.IcosahedronGeometry(0.07, 2), new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false, transparent: true, opacity: 0.85 })); eixo.add(nucleoInterno);
    const aroNucleo = new THREE.Mesh(new THREE.TorusGeometry(0.29, 0.014, 10, 72), brilho(1.35, 1, true)); eixo.add(aroNucleo);
    const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: texturaHalo(), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, opacity: 0.7 }));
    halo.scale.set(1.5, 1.5, 1); halo.position.z = 0.05; todosBrilhos.push({ m: halo.material, mult: 1.0, acento: true }); eixo.add(halo);

    const bobinas = new THREE.Group(); eixo.add(bobinas);
    const matBob = new THREE.MeshStandardMaterial({ color: 0x0f3342, metalness: 0.92, roughness: 0.3, emissive: 0x00e5ff, emissiveIntensity: 0.14 });
    const geoBob = new THREE.BoxGeometry(0.17, 0.36, 0.16), geoFio = new THREE.BoxGeometry(0.03, 0.27, 0.02);
    for (let i = 0; i < 10; i++) {
        const a = (i / 10) * TAU, g = new THREE.Group();
        const b = new THREE.Mesh(geoBob, matBob); g.add(b);
        const f = new THREE.Mesh(geoFio, brilho(1.3, 1, true)); f.position.set(0, 0, 0.085); g.add(f);
        g.position.set(Math.cos(a) * 0.46, Math.sin(a) * 0.46, 0.02); g.rotation.z = a - Math.PI / 2; bobinas.add(g);
    }

    const aneisArcos = new THREE.Group(); eixo.add(aneisArcos);
    for (let i = 0; i < 6; i++) {
        const arco = new THREE.Mesh(new THREE.TorusGeometry(0.86, 0.024, 10, 64, TAU / 6 * 0.72), brilho(1.2, 1, true));
        arco.rotation.z = (i / 6) * TAU; aneisArcos.add(arco);
    }
    const aneiFino = new THREE.Mesh(new THREE.TorusGeometry(0.74, 0.007, 6, 160), brilho(1.0, 0.8)); eixo.add(aneiFino);
    const aneiExterno = new THREE.Mesh(new THREE.TorusGeometry(1.14, 0.007, 6, 200), brilho(0.8, 0.6)); eixo.add(aneiExterno);

    const NT = 72, ticks = new THREE.InstancedMesh(new THREE.BoxGeometry(0.012, 0.07, 0.012), brilho(1.0, 0.9), NT);
    const aux = new THREE.Object3D();
    for (let i = 0; i < NT; i++) { const a = (i / NT) * TAU, longo = i % 6 === 0; aux.position.set(Math.cos(a) * 1.0, Math.sin(a) * 1.0, 0); aux.rotation.set(0, 0, a - Math.PI / 2); aux.scale.set(1, longo ? 1.9 : 1, 1); aux.updateMatrix(); ticks.setMatrixAt(i, aux.matrix); }
    eixo.add(ticks);

    const NB = 96, barras = new THREE.InstancedMesh(new THREE.BoxGeometry(0.02, 1, 0.02), brilho(1.35, 0.95, true), NB);
    eixo.add(barras);
    const dados = new Float32Array(NB);

    const orbitas = [];
    [[1.34, 0.5, 0.2, 0.9], [1.5, -0.6, 0.45, -0.6], [1.62, 0.15, -0.5, 0.45]].forEach(([r, rx, ry, vel], i) => {
        const pivo = new THREE.Group(); pivo.rotation.set(rx, ry, i);
        const linha = new THREE.Mesh(new THREE.TorusGeometry(r, 0.004, 4, 160), brilho(0.9, 0.5)); pivo.add(linha);
        const sat = new THREE.Mesh(new THREE.SphereGeometry(0.045, 16, 12), brilho(1.8, 1, true)); sat.position.set(r, 0, 0);
        const braco = new THREE.Group(); braco.add(sat); pivo.add(braco); eixo.add(pivo);
        orbitas.push({ braco, vel, fase: i * 2.1 });
    });

    const NE = 420, esfera = new THREE.Points(new THREE.BufferGeometry(), new THREE.PointsMaterial({ size: 0.04, map: texturaHalo(), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    { const p = new Float32Array(NE * 3); for (let i = 0; i < NE; i++) { const y = 1 - (i / (NE - 1)) * 2, r = Math.sqrt(1 - y * y), a = i * 2.399963; p.set([Math.cos(a) * r * 0.78, y * 0.78, Math.sin(a) * r * 0.78], i * 3); } esfera.geometry.setAttribute('position', new THREE.BufferAttribute(p, 3)); }
    esfera.visible = false; eixo.add(esfera);

    // ---------------------------------------------------------------- ambiente: túnel de partículas e piso
    const NP = 1500, pPos = new Float32Array(NP * 3), pVel = new Float32Array(NP);
    for (let i = 0; i < NP; i++) { pPos.set([(Math.random() - 0.5) * 24, (Math.random() - 0.5) * 12, -24 + Math.random() * 28], i * 3); pVel[i] = 0.25 + Math.random() * 0.9; }
    const pGeo = new THREE.BufferGeometry(); pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
    const pMat = new THREE.PointsMaterial({ size: 0.05, map: texturaHalo(), transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true });
    scene.add(new THREE.Points(pGeo, pMat));

    const piso = new THREE.GridHelper(60, 100, 0x00e5ff, 0x00789a); piso.position.y = -2.7; piso.material.transparent = true; piso.material.opacity = 0; scene.add(piso);
    const teto = piso.clone(); teto.material = piso.material.clone(); teto.position.y = 4.6; scene.add(teto);

    // ---------------------------------------------------------------- texto de inicialização
    const boot = document.createElement('div'); boot.id = 'boot3d';
    const LINHAS = [[0.3, 'NÚCLEO ARC', 'ONLINE'], [0.95, 'SISTEMAS', 'SINCRONIZADOS'], [1.6, 'VOZ E MEMÓRIA', 'PRONTAS'], [2.25, 'J.A.R.V.I.S', 'ATIVO']];
    boot.innerHTML = LINHAS.map(([, a, b]) => `<div><span>${a}</span><i></i><b>${b}</b></div>`).join('');

    // ---------------------------------------------------------------- estado
    const s = { giro: 0.2, brilho: 0.5, nivel: 0, cor: CORES.base.slice(), r1: 0, r2: 0, r3: 0, r4: 0, tomK: 0, forcaBloom: 0.85 };
    const alvoMouse = { x: 0, y: 0 }, mouse = { x: 0, y: 0 };
    const aoMouse = (e) => { alvoMouse.x = (e.clientX / innerWidth - 0.5) * 2; alvoMouse.y = (e.clientY / innerHeight - 0.5) * 2; document.documentElement.style.setProperty('--mx', alvoMouse.x.toFixed(3)); document.documentElement.style.setProperty('--my', alvoMouse.y.toFixed(3)); };
    window.addEventListener('pointermove', aoMouse, { passive: true });

    let W = 1, H = 1, t0 = performance.now(), ultimo = t0, introPronta = false, nivelMs = 0, lentos = 0, qualidade = 2;
    function ajustar() {
        const c = canvas.getBoundingClientRect();
        W = Math.max(2, Math.round(c.width)); H = Math.max(2, Math.round(c.height));
        renderer.setPixelRatio(pr); renderer.setSize(W, H, false);
        composer.setPixelRatio(pr); composer.setSize(W, H);
        bloom.resolution.set(W / 2, H / 2);
        camera.aspect = W / H;
    }
    new ResizeObserver(ajustar).observe(canvas);
    ajustar();

    function posicionar() {                                       // centro e tamanho do reator = os do elemento de referência
        const r = ref.getBoundingClientRect();
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        camera.setViewOffset(W, H, W / 2 - cx, H / 2 - cy, W, H);
        const pxPorUnidade = (H / 2) / Math.tan((camera.fov * Math.PI / 180) / 2) / CAM_Z;
        const escala = (Math.min(r.width, r.height) * 0.44) / (pxPorUnidade * 1.5);
        raiz.scale.setScalar(Math.max(0.2, escala));
    }

    function atualizarCores(estado, emo, k, dt) {
        const alvo = PERFIL[estado] || PERFIL.espera;
        s.giro = lerp(s.giro, emo ? Math.max(alvo.giro, emo.giro) : alvo.giro, k);
        s.tomK = lerp(s.tomK, emo ? 0.6 : 0, k);
        s.brilho = lerp(s.brilho, alvo.brilho, k);
        s.nivel = lerp(s.nivel, api.nivel(), 1 - Math.pow(0.0005, dt));
        const alvoCor = emo ? emo.cor : (estado === 'falando' ? mix(CORES.base, CORES.claro, 0.38) : CORES[alvo.arcos]);   // 'claro' puro estoura para branco em 3D
        s.cor = mix(s.cor, alvoCor, k);
        const base = mix(CORES.base, s.cor, s.tomK * 0.7), claro = mix(CORES.claro, s.cor, s.tomK);
        cor.setRGB(base[0] / 255, base[1] / 255, base[2] / 255);
        corClara.setRGB(claro[0] / 255, claro[1] / 255, claro[2] / 255);
        corAcento.setRGB(s.cor[0] / 255, s.cor[1] / 255, s.cor[2] / 255);       // arcos, núcleo e barras seguem o estado (âmbar ao pensar)
        return alvo;
    }

    let rodando = true;
    // ondas de choque (quando o Jarvis age: abre um app, tira foto, mexe no PC) + surto de energia que decai
    const ondas = [];
    for (let i = 0; i < 3; i++) {
        const m = new THREE.Mesh(new THREE.RingGeometry(0.96, 1, 128), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide }));
        m.visible = false; eixo.add(m); ondas.push({ m, t: 99 });
    }
    let proxOnda = 0; s.surto = 0; s.amb = 1;                       // s.amb: força do piso/teto em grade (o visual moderno deixa bem mais discreto)
    function pulso(forca = 1) {
        s.surto = Math.max(s.surto, Math.min(1.4, forca));
        const o = ondas[proxOnda++ % ondas.length]; o.t = 0; o.m.visible = true;
    }

    function quadro(agora) {
        if (!rodando) return;
        requestAnimationFrame(quadro);
        if (document.hidden) return;
        const dt = Math.min(0.05, (agora - ultimo) / 1000); ultimo = agora;
        const t = (agora - t0) / 1000;
        const estado = api.estado();
        const emo = api.emocao ? EMO[api.emocao()] : null;
        const k = 1 - Math.pow(0.0025, dt);
        atualizarCores(estado, emo, k, dt);

        const intro = clamp01(t / INTRO_S);
        if (!introPronta && intro >= 1) { introPronta = true; boot.classList.add('fim'); setTimeout(() => boot.remove(), 900); }
        s.surto = Math.max(0, s.surto - dt * 1.5);
        const bril = s.brilho * (api.brilho ? api.brilho() : 1) + s.surto * 0.5;
        const nivel = s.nivel;
        const estilo = api.estilo ? api.estilo() : 'classico';

        // rotações: giram em eixos diferentes (profundidade real)
        s.r1 += dt * s.giro * 0.35; s.r2 -= dt * s.giro * 0.6; s.r3 += dt * s.giro * 1.25; s.r4 -= dt * s.giro * 0.12;

        // entrada: câmera vem de longe, peças montam em sequência, o núcleo acende com um clarão
        const peca = (atraso, dur) => easeBack((t - atraso) / dur);
        const girada = (1 - easeOut(intro)) * 9;
        camera.position.z = lerp(13, CAM_Z, easeOut(intro));
        mouse.x = lerp(mouse.x, alvoMouse.x, 1 - Math.pow(0.02, dt)); mouse.y = lerp(mouse.y, alvoMouse.y, 1 - Math.pow(0.02, dt));
        camera.position.x = mouse.x * 0.55 + Math.sin(t * 0.21) * 0.12; camera.position.y = -mouse.y * 0.32 + Math.cos(t * 0.17) * 0.08;
        camera.position.z -= easeOut(Math.min(1, s.surto)) * 0.5;               // um soco de câmera quando o surto acontece
        camera.lookAt(0, 0, 0);
        camera.rotation.z += (1 - easeOut(intro)) * 0.18;
        eixo.rotation.y = mouse.x * 0.34 + Math.sin(t * 0.32) * 0.07;
        eixo.rotation.x = mouse.y * 0.24 + Math.cos(t * 0.27) * 0.05;

        todosBrilhos.forEach((o) => { o.m.color.copy(o.acento ? corAcento : cor).multiplyScalar(o.mult * (0.55 + 0.7 * bril)); });
        luzCentro.color.copy(corAcento); luzCentro.intensity = 4 + 7 * bril + 12 * nivel;
        matBob.emissive.copy(corAcento); matBob.emissiveIntensity = 0.1 + 0.25 * bril + 0.5 * nivel;

        const ignicao = easeOut((t - 1.45) / 0.9);
        const clarao = Math.max(0, 1 - Math.abs(t - 1.75) / 0.45);
        const pulso = 1 + nivel * 0.4 + Math.sin(t * 2.4) * 0.04;
        nucleo.scale.setScalar(ignicao * pulso); nucleoInterno.scale.setScalar(ignicao * (0.9 + nivel * 0.8)); nucleoInterno.material.color.copy(corClara).lerp(new THREE.Color(1, 1, 1), 0.45);
        nucleo.rotation.y += dt * 0.8; nucleo.rotation.x += dt * 0.5;
        halo.scale.setScalar(1.5 * ignicao * (1 + nivel * 0.7) + clarao * 1.8);
        halo.material.opacity = (0.16 + 0.26 * bril + 0.22 * nivel) * ignicao;
        aroNucleo.scale.setScalar(peca(1.1, 0.9)); aroNucleo.rotation.z = s.r3; aroNucleo.rotation.x = Math.sin(t * 0.7) * 0.5;
        placa.scale.setScalar(Math.max(0.001, peca(0.2, 1.0))); aroPlaca.scale.setScalar(Math.max(0.001, peca(0.3, 1.0)));

        const mostraCompleto = estilo !== 'esfera', mostraTudo = estilo === 'classico';
        bobinas.visible = mostraCompleto; placa.visible = mostraCompleto; aroPlaca.visible = mostraCompleto;
        aneisArcos.visible = mostraCompleto; ticks.visible = mostraTudo; aneiExterno.visible = mostraTudo; aneiFino.visible = mostraTudo;
        esfera.visible = estilo === 'esfera'; barras.visible = mostraTudo;
        orbitas.forEach((o) => { o.braco.parent.visible = mostraTudo; });
        bobinas.scale.setScalar(Math.max(0.001, peca(0.6, 1.1))); bobinas.rotation.z = s.r1 * 0.6;
        aneisArcos.scale.setScalar(Math.max(0.001, peca(0.9, 1.1))); aneisArcos.rotation.z = s.r2; aneisArcos.rotation.x = Math.sin(t * 0.4) * 0.28; aneisArcos.rotation.y = Math.cos(t * 0.33) * 0.22;
        aneiFino.scale.setScalar(Math.max(0.001, peca(1.2, 1.0))); aneiFino.rotation.z = -s.r3 * 0.5; aneiFino.rotation.x = Math.sin(t * 0.5) * 0.35;
        aneiExterno.scale.setScalar(Math.max(0.001, peca(1.4, 1.0))); aneiExterno.rotation.z = s.r4;
        ticks.scale.setScalar(Math.max(0.001, peca(1.5, 1.0))); ticks.rotation.z = s.r4 * 1.4;
        esfera.rotation.y = s.r1 * 1.2; esfera.rotation.x = s.r4 * 2; esfera.material.color.copy(cor).multiplyScalar(1.2); esfera.material.opacity = 0.35 + 0.5 * bril;
        orbitas.forEach((o, i) => { o.braco.rotation.z = o.fase + t * o.vel * (0.5 + s.giro); o.braco.parent.scale.setScalar(Math.max(0.001, peca(1.7 + i * 0.2, 1.0))); });

        // barras de áudio em volta do reator
        const esp = api.espectro ? api.espectro() : null;
        for (let i = 0; i < NB; i++) {
            const m = i < NB / 2 ? i : NB - 1 - i;                       // espelha: simétrico, como o reator do filme
            let alvo;
            if (esp) alvo = esp[Math.min(esp.length - 1, 2 + Math.floor(m * 1.1))] / 255;
            else alvo = estado === 'ouvindo' ? (0.04 + nivel * 0.8) * (0.5 + 0.5 * Math.abs(Math.sin(t * 2 + i * 0.5))) : estado === 'pensando' ? 0.05 + 0.05 * Math.abs(Math.sin(t * 6 + i)) : 0.03;
            dados[i] = lerp(dados[i], alvo, 1 - Math.pow(0.0001, dt));
            const a = (i / NB) * TAU, h = (0.03 + dados[i] * 0.5) * clamp01((t - 2.3) / 0.7);
            aux.position.set(Math.cos(a) * (1.2 + h / 2), Math.sin(a) * (1.2 + h / 2), 0); aux.rotation.set(0, 0, a - Math.PI / 2); aux.scale.set(1, Math.max(0.001, h), 1); aux.updateMatrix();
            barras.setMatrixAt(i, aux.matrix);
        }
        barras.instanceMatrix.needsUpdate = true;

        // ambiente
        const ap = pPos;
        for (let i = 0; i < NP; i++) { ap[i * 3 + 2] += pVel[i] * dt * (0.6 + s.giro * 0.9); if (ap[i * 3 + 2] > 4) ap[i * 3 + 2] = -24; }
        pGeo.attributes.position.needsUpdate = true;
        pMat.color.copy(cor).multiplyScalar(1.4); pMat.opacity = 0.7 * easeOut((t - 0.3) / 1.6) * (0.5 + 0.5 * bril);
        piso.material.color.copy(cor); piso.material.opacity = 0.32 * s.amb * easeOut((t - 0.8) / 1.8); piso.position.z = (t * 0.55) % 0.6;
        teto.material.color.copy(cor); teto.material.opacity = 0.14 * s.amb * easeOut((t - 1.0) / 1.8); teto.position.z = piso.position.z;

        for (const o of ondas) {
            if (!o.m.visible) continue;
            o.t += dt; const p = o.t / 1.4;
            if (p >= 1) { o.m.visible = false; continue; }
            o.m.scale.setScalar(1.15 + easeOut(p) * 6); o.m.material.opacity = Math.pow(1 - p, 2) * 0.85; o.m.material.color.copy(corAcento).multiplyScalar(1.3);
        }
        s.forcaBloom = 0.3 + 0.18 * bril + 0.32 * nivel + clarao * 1.1 + s.surto * 0.35;
        bloom.strength = s.forcaBloom;

        posicionar();
        if (usarBloom) composer.render(); else renderer.render(scene, camera);

        // qualidade adaptativa: se a máquina não dá conta, simplifica sozinho
        if (dt > 0.036) lentos++; else lentos = Math.max(0, lentos - 2);
        if (lentos > 80 && qualidade > 0) {
            qualidade--; lentos = 0;
            if (qualidade === 1) { pr = 1; ajustar(); } else if (qualidade === 0) { usarBloom = false; document.body.classList.add('leve'); }
        }
    }
    renderer.compile(scene, camera);                              // compila os shaders agora: o 1º quadro não pode comer a abertura
    composer.render();
    t0 = performance.now(); ultimo = t0;
    document.body.appendChild(boot);                              // o texto de inicialização só entra quando a cena de fato começa
    requestAnimationFrame(quadro);

    return {
        introMs: INTRO_S * 1000,
        definirTema,
        pulso,
        ambiente: (k) => { s.amb = k; },
        qualidade: () => qualidade,
        info: () => ({ renderer: renderer.info.render, fps_lentos: lentos, qualidade, bloom: usarBloom, pixelRatio: pr }),
        destruir() { rodando = false; window.removeEventListener('pointermove', aoMouse); renderer.dispose(); boot.remove(); },
    };
}

window.dispatchEvent(new CustomEvent('cena3d-pronta'));
