// Gestos por câmera: o modelo local do MediaPipe (mão e rosto, WASM no próprio app, sem rede) acha os PONTOS; as regras dos gestos são nossas
// (gestos-regras.js, determinísticas). Nada de imagem sai do computador nem é gravado. Ligado só por escolha (tecla G ou o botão GESTOS).
(function () {
    'use strict';
    const BASE = '/static/vendor/mediapipe';
    const R = window.GestosRegras;
    const estado = { ligado: false, carregando: false, erro: '', fps: 0, mao: false, rosto: false, delegate: '' };
    const ouvintes = { gesto: [], estado: [], mouse: [] };
    let video = null, fluxo = null, maoDet = null, rostoDet = null, laco = 0, mod = null;
    let regrasMao = null, regrasCabeca = null, suavizaMao = null, regrasMouse = null, suavizaMaos = [], modoMouse = false;
    let ultimo = { mao: null, rosto: null, medidas: null, mao_estado: null };
    let semMaoDesde = 0, contaQuadros = 0, t0Fps = performance.now(), ultimoRosto = 0;

    const emitir = (tipo, dado) => ouvintes[tipo].forEach((f) => { try { f(dado); } catch (_) { /* o ouvinte não derruba o laço */ } });
    const mudou = () => emitir('estado', { ...estado });

    async function carregarModelos() {
        if (maoDet && rostoDet) return;
        mod = mod || await import(BASE + '/vision_bundle.js');
        const vision = await mod.FilesetResolver.forVisionTasks(BASE + '/wasm');
        const criar = async (Classe, modelo, extra) => {
            for (const delegate of (new URLSearchParams(location.search).get('gestos_gpu') === '1' ? ['GPU', 'CPU'] : ['CPU'])) {      // medido: a CPU (XNNPACK) leva ~20 a 70 ms por quadro; o delegate de GPU na placa integrada levou 6 s
                try {
                    const d = await Classe.createFromOptions(vision, { baseOptions: { modelAssetPath: BASE + '/modelos/' + modelo, delegate }, runningMode: 'VIDEO', ...extra });
                    estado.delegate = delegate;
                    return d;
                } catch (e) { if (delegate === 'CPU') throw e; }
            }
        };
        maoDet = await criar(mod.HandLandmarker, 'hand_landmarker.task', { numHands: 1, minHandDetectionConfidence: 0.55, minHandPresenceConfidence: 0.5, minTrackingConfidence: 0.5 });
        rostoDet = await criar(mod.FaceLandmarker, 'face_landmarker.task', { numFaces: 1, minFaceDetectionConfidence: 0.55, minTrackingConfidence: 0.5 });
    }

    const espelha = (pts) => pts && pts.map((p) => ({ x: 1 - p.x, y: p.y, z: p.z }));     // a prévia é espelhada: "direita" é a direita de quem olha

    function quadro() {
        laco = 0;
        if (!estado.ligado || !video || video.readyState < 2) { if (estado.ligado) laco = setTimeout(quadro, 33); return; }
        const agora = performance.now();
        if (video.currentTime !== quadro.ult) {
            quadro.ult = video.currentTime;
            try {
                const asp = (video.videoWidth || 640) / (video.videoHeight || 480);
                const i0 = performance.now();
                const rm = maoDet.detectForVideo(video, agora);
                estado.ms_mao = Math.round(performance.now() - i0);
                const lista = rm && rm.landmarks ? rm.landmarks : [];
                const pm = suavizaMao(lista[0] ? espelha(lista[0]) : null, agora);      // One Euro: tira o tremor
                if (modoMouse) {                                                       // mouse no ar: até duas mãos (a segunda serve ao zoom)
                    const maos = lista.slice(0, 2).map((l, i) => suavizaMaos[i](espelha(l), agora));
                    if (!maos.length) { suavizaMaos[0](null, agora); suavizaMaos[1](null, agora); }
                    for (const ev of regrasMouse.atualizar(maos, agora, asp)) emitir('mouse', ev);
                }
                estado.mao = !!pm; ultimo.mao = pm;
                for (const ev of regrasMao.atualizar(pm, agora, asp)) emitir('gesto', ev);
                ultimo.mao_estado = pm ? regrasMao.estado(pm, asp) : null;
                if (agora - ultimoRosto > 90) {                                    // o rosto não precisa de tanta frequência
                    ultimoRosto = agora;
                    const j0 = performance.now();
                    const rr = rostoDet.detectForVideo(video, agora);
                    estado.ms_rosto = Math.round(performance.now() - j0);
                    const pr = rr && rr.faceLandmarks && rr.faceLandmarks[0] ? espelha(rr.faceLandmarks[0]) : null;
                    estado.rosto = !!pr; ultimo.rosto = pr; ultimo.medidas = pr ? regrasCabeca.medidas(pr) : null;
                    for (const ev of regrasCabeca.atualizar(pr, agora)) emitir('gesto', ev);
                }
            } catch (e) { estado.erro = String(e && e.message || e).slice(0, 120); }
            contaQuadros++;
            if (agora - t0Fps > 1000) { estado.fps = contaQuadros; contaQuadros = 0; t0Fps = agora; mudou(); }
        }
        // sem mão à vista a busca é mais cara e menos urgente: espia 8 vezes por segundo; com a mão rastreada, ~30
        if (estado.mao) semMaoDesde = 0; else if (!semMaoDesde) semMaoDesde = agora;
        laco = setTimeout(quadro, semMaoDesde && agora - semMaoDesde > 1200 ? 110 : 25);
    }

    async function ligar() {
        if (estado.ligado || estado.carregando) return estado;
        estado.carregando = true; estado.erro = ''; mudou();
        try {
            await carregarModelos();
            fluxo = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30 } }, audio: false });
            video = document.createElement('video');
            video.playsInline = true; video.muted = true; video.srcObject = fluxo;
            await video.play();
            regrasMao = R.criarMao(); regrasCabeca = R.criarCabeca(); suavizaMao = R.filtrarPontos(1.2, 8);
            regrasMouse = R.criarMouse(); suavizaMaos = [R.filtrarPontos(1.2, 8), R.filtrarPontos(1.2, 8)];
            estado.ligado = true;
            laco = setTimeout(quadro, 33);
        } catch (e) {
            estado.erro = (e && (e.name === 'NotAllowedError' ? 'permissao' : e.name === 'NotFoundError' ? 'sem_camera' : e.name === 'NotReadableError' ? 'camera_ocupada' : e.message)) || 'falha';
            desligar();
        }
        estado.carregando = false; mudou();
        return estado;
    }

    function desligar() {
        estado.ligado = false; estado.mao = estado.rosto = false; modoMouse = false;
        if (laco) clearTimeout(laco); laco = 0;
        if (fluxo) fluxo.getTracks().forEach((t) => t.stop());
        fluxo = null; if (video) { video.srcObject = null; video = null; }
        ultimo = { mao: null, rosto: null, medidas: null, mao_estado: null };
        mudou();
    }

    function mouse(ligar) {                                    // liga/desliga o MOUSE NO AR (precisa dos gestos ligados)
        modoMouse = !!ligar && estado.ligado;
        if (regrasMouse) regrasMouse.reiniciar();
        try { if (maoDet) maoDet.setOptions({ numHands: modoMouse ? 2 : 1 }); } catch (_) { /* segue com o que tem */ }
        return modoMouse;
    }

    window.Gestos = {
        mouse, modoMouse: () => modoMouse,
        ligar, desligar, estado: () => ({ ...estado }), ultimo: () => ultimo, video: () => video,
        ao(tipo, f) { ouvintes[tipo].push(f); },
        disponivel: () => !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && R),
    };
})();
