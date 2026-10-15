// J.A.R.V.I.S. — interface. Voz entra pelo microfone (reconhecimento do Chrome),
// o servidor pensa e devolve frases em áudio (ElevenLabs) ou texto (voz do navegador).
(function () {
    'use strict';

    const $ = (id) => document.getElementById(id);
    const AUTO = new URLSearchParams(location.search).get('auto') === '1';

    const ROTULOS = {
        offline: 'SEM CONEXÃO', espera: 'AGUARDANDO', ouvindo: 'OUVINDO',
        pensando: 'PROCESSANDO', falando: 'RESPONDENDO',
    };

    // ------------------------------------------------------------ estado
    let estado = 'offline';
    let ws = null;
    let turnoAtivo = false;     // o servidor ainda está trabalhando na resposta
    let mudo = false;           // microfone silenciado (tecla M)
    let dormindo = false;       // Jarvis pediu espera; palmas acordam
    let conectadoUmaVez = false;
    let emocaoAtual = null;     // emoção da frase que está tocando (tinge o reator e a interface)
    function setEmocao(e) { emocaoAtual = e; document.body.dataset.emocao = e || ''; }
    let confirmacao = null;     // { id, ... } enquanto o servidor espera o sim/não do usuário
    let confirmacaoTimer = null;
    let midiaAtiva = false;     // há música/vídeo tocando: só ouço comandos que comecem chamando "Jarvis"
    let duckAvisado = false;
    const CHAMOU_JARVIS = /\b(j[aá]r?v[iíy]s|j[aá]rbis|g[aá]rvis|d?j[aá]rvis|jarvi|jarves|ch?[aá]rvis|j[aá]rv[eo]s|j[aá]vis|[jg][eé]rv[iíy]s|jarvin)\b/i;
    // Modo conversa: enquanto vocês estão conversando (até `janelaConversaMs` sem ninguém falar) respondo tudo, sem precisar do nome.
    // Depois de um tempo em silêncio, ou se ele disser tchau/"me aguarda" (encerrar_conversa), só respondo se me chamarem por "Jarvis".
    let exigeChamada = true, janelaConversaMs = 90000, janelaAte = 0, conversaEncerrada = false;
    const CONFIANCA_MIN = 0.3;  // abaixo disso o reconhecedor está chutando (barulho, TV, outra pessoa)
    const CONFIANCA_LOCAL_MIN = 0.45;   // o reconhecimento próprio é mais exigente: uma fala duvidosa não pode acordar o Jarvis
    const decisao = (r, acao, motivo) => {
        if (r && r.id) enviar({ tipo: 'voz_decisao', id: r.id, acao, motivo });
        if (acao === 'ignorou' && r && r.transcript && /^sem o nome/.test(motivo || '')) dicaOuvi(r.transcript);       // ele ouviu, mas faltou o nome: mostra isso em vez de calar
    };
    let dicaT = 0;
    function dicaOuvi(texto) {
        const el = $('legenda-voce');
        el.textContent = `ouvi: “${String(texto).slice(0, 90)}”  ·  diga “Jarvis” primeiro (ou clique em AGUARDANDO / tecla T)`;
        el.classList.add('parcial');
        clearTimeout(dicaT); dicaT = setTimeout(() => { if (el.textContent.startsWith('ouvi:')) el.textContent = ''; }, 6000);
    }
    function abrirConversa() {                                        // clique no estado ou tecla T: fala sem dizer o nome durante a janela de conversa
        conversaEncerrada = false; janelaAte = performance.now() + janelaConversaMs;
        aviso('Pode falar: não precisa dizer “Jarvis” pelos próximos ' + Math.round(janelaConversaMs / 1000) + ' s.', 3500);
        if (estado === 'ouvindo' || estado === 'espera') iniciarReconhecimento();
    }   // alimenta o painel 'Últimas falas ouvidas'
    let gravando = false;       // modo gravação: silêncio total, e só respondo se me chamarem pelo nome
    // "Jarvis" só é uma chamada se estiver no COMEÇO ou no FIM da fala; no meio ("o Jarvis falou que...") é conversa sobre ele
    function chamouMesmo(texto) {
        if (!CHAMOU_JARVIS.test(texto)) return false;
        if (naJanela()) return true;
        const pal = texto.toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, ' ').split(/\s+/).filter(Boolean);
        const i = pal.findIndex((p) => CHAMOU_JARVIS.test(p));
        return i >= 0 && (i <= 3 || i >= pal.length - 2);
    }
    function naJanela() { return !gravando && performance.now() < janelaAte; }
    function estenderConversa() {
        if (conversaEncerrada) { conversaEncerrada = false; janelaAte = 0; return; }
        janelaAte = performance.now() + janelaConversaMs;
    }

    function setEstado(novo) {
        estado = novo;
        if (window.jarvisShell && window.jarvisShell.estado) window.jarvisShell.estado(novo);          // o ícone flutuante espelha o estado
        if (novo !== setEstado.ultimo) { const eraFalando = setEstado.ultimo === 'falando'; setEstado.ultimo = novo; if ((novo === 'falando' || eraFalando) && typeof enviar === 'function' && typeof usaLocal === 'function' && usaLocal()) enviar({ tipo: 'stt_falando', falando: novo === 'falando' }); }
        document.body.dataset.estado = novo;
        $('rotulo-estado').textContent = mudo && novo === 'ouvindo' ? 'MICROFONE MUDO' : ROTULOS[novo];
        $('pill-texto').textContent = ROTULOS[novo];
    }

    function aviso(texto, ms = 7000) {
        const el = $('aviso');
        el.textContent = texto;
        el.classList.add('visivel');
        clearTimeout(aviso.t);
        aviso.t = setTimeout(() => el.classList.remove('visivel'), ms);
    }

    // ------------------------------------------------------------ áudio
    const MUDO = new URLSearchParams(location.search).get('mudo') === '1';
    let ctx = null, analisador = null, ganho = null, dadosEspectro = null, saidaMestre = null;
    let fonteAtual = null;
    let tocando = false;
    let token = 0;              // muda a cada interrupção; invalida o que estava tocando
    const fila = [];
    let nivelSintetico = 0;     // quando fala a voz do navegador (sem espectro real)
    let nivelMic = 0;
    let micBuf = null;          // forma de onda do microfone (para o osciloscópio)
    const saidaBuf = new Uint8Array(256);

    function contexto() {
        if (!ctx) {
            ctx = new (window.AudioContext || window.webkitAudioContext)();
            analisador = ctx.createAnalyser();
            analisador.fftSize = 256;
            analisador.smoothingTimeConstant = 0.78;
            ganho = ctx.createGain();
            ganho.connect(analisador);
            saidaMestre = ctx.createGain();
            saidaMestre.gain.value = MUDO ? 0 : 1;           // ?mudo=1: os testes automáticos não fazem barulho
            analisador.connect(saidaMestre);
            saidaMestre.connect(ctx.destination);
            dadosEspectro = new Uint8Array(analisador.frequencyBinCount);
            Sfx.iniciar(ctx);
        }
        if (ctx.state === 'suspended') ctx.resume().catch(() => {});
        return ctx;
    }

    function b64ParaBuffer(b64) {
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        return bytes.buffer;
    }

    function receberFala(msg) {
        if (msg.silencioso || gravando) { addJarvis(msg.texto); return; }       // gravando: só texto, nada de voz
        abaixarMusica();
        marcarFalaRecebida();
        addJarvis(msg.texto);
        const item = { texto: msg.texto, emocao: msg.emocao || null, buffer: null, pronto: null };
        if (msg.audio) {
            item.pronto = contexto().decodeAudioData(b64ParaBuffer(msg.audio))
                .then((b) => { item.buffer = b; }).catch(() => {});
        }
        fila.push(item);
        if (!tocando) tocar();
    }

    // ---- voz em streaming (ElevenLabs): o áudio chega em pedaços e começa a tocar no PRIMEIRO (MediaSource), sem esperar a frase inteira
    const SUPORTA_STREAM = !!(window.MediaSource && MediaSource.isTypeSupported && MediaSource.isTypeSupported('audio/mpeg'));
    const streams = new Map();        // id -> { ms, el, sb, fila, fim, url }

    function criarStream(id) {
        const ms = new MediaSource();
        const el = new Audio();
        el.preload = 'auto';
        const st = { id, ms, el, sb: null, fila: [], fim: false, url: URL.createObjectURL(ms), falhou: false, tocou: false };
        el.src = st.url;
        ms.addEventListener('sourceopen', () => {
            try { st.sb = ms.addSourceBuffer('audio/mpeg'); } catch (_) { st.falhou = true; return; }
            st.sb.addEventListener('updateend', () => bombear(st));
            bombear(st);
        }, { once: true });
        streams.set(id, st);
        return st;
    }

    function bombear(st) {                                   // anexa o próximo pedaço quando o anterior terminou de entrar
        if (!st.sb || st.sb.updating || st.falhou) return;
        if (st.fila.length) {
            try { st.sb.appendBuffer(st.fila.shift()); } catch (_) { st.falhou = true; }
        } else if (st.fim && st.ms.readyState === 'open') {
            try { st.ms.endOfStream(); } catch (_) { /* já encerrado */ }
        }
    }

    function liberarStream(st) {
        try { st.el.pause(); } catch (_) {}
        try { st.el.removeAttribute('src'); st.el.load(); } catch (_) {}
        try { URL.revokeObjectURL(st.url); } catch (_) {}
        streams.delete(st.id);
    }

    function receberFalaStream(msg) {
        if (gravando) { addJarvis(msg.texto); return; }
        abaixarMusica();
        marcarFalaRecebida();
        addJarvis(msg.texto);
        fila.push({ texto: msg.texto, emocao: msg.emocao || null, buffer: null, pronto: null, stream: criarStream(msg.id) });
        if (!tocando) tocar();
    }

    function tocarStream(item) {
        const st = item.stream;
        return new Promise((resolve) => {
            let feito = false;
            const terminar = () => { if (feito) return; feito = true; fonteAtual = null; liberarStream(st); resolve(); };
            try { contexto().createMediaElementSource(st.el).connect(ganho); } catch (_) { /* já ligado */ }
            fonteAtual = { stop: terminar };
            const reg = (nome) => { (window.__streamLog = window.__streamLog || []).push([nome, performance.now(), st.el.currentTime, st.id]); };
            st.el.addEventListener('playing', () => { st.tocou = true; reg('playing'); marcarAudioTocando(); }, { once: true });
            st.el.addEventListener('ended', () => reg('ended'), { once: true });
            st.el.addEventListener('ended', terminar, { once: true });
            st.el.addEventListener('error', terminar, { once: true });
            st.el.play().catch(() => { /* bloqueado: o 'error' ou o tempo limite encerram */ });
            setTimeout(() => { if (!st.tocou && !(st.el.currentTime > 0)) terminar(); }, 12000);       // nada chegou: segue em frente
        });
    }

    async function tocar() {
        tocando = true;
        const meu = token;
        setEstado('falando');
        if (podeEscutarFalando()) iniciarReconhecimento(); else pararReconhecimento();   // aberto = dá para interrompê-lo falando
        while (fila.length && meu === token) {
            const item = fila.shift();
            if (item.pronto) await item.pronto;
            if (meu !== token) break;
            aplicarEmocao(item.emocao);
            if (!item.stream && !item.filler) marcarAudioTocando();           // no streaming, isto é marcado quando o som de fato começa
            if (item.stream) await tocarStream(item);
            else if (item.buffer) await tocarBuffer(item.buffer);
            else await falarNavegador(item.texto);
            setEmocao(null);
        }
        if (meu !== token) return;   // interrompido: quem interrompeu cuida do estado
        setEmocao(null);
        tocando = false;
        nivelSintetico = 0;
        ultimoFalado = legendaJarvis.join(' '); fimDaFalaEm = performance.now();
        depoisDeFalar();
    }

    function aplicarEmocao(e) {
        setEmocao(e);
        const fx = e && Sfx.deEmocao(e);
        if (fx) Sfx.tocar(fx);
    }

    function tocarBuffer(buffer) {
        return new Promise((resolve) => {
            const c = contexto();
            const fonte = c.createBufferSource();
            fonte.buffer = buffer;
            fonte.connect(ganho);
            fonteAtual = fonte;
            fonte.onended = () => { fonteAtual = null; resolve(); };
            fonte.start();
        });
    }

    let vozPT = null;
    function escolherVoz() {
        const vozes = speechSynthesis.getVoices().filter((v) => /^pt(-|_)BR/i.test(v.lang));
        const pref = ['Antonio', 'Daniel', 'Humberto', 'Ricardo', 'Google português'];
        vozPT = pref.map((p) => vozes.find((v) => v.name.includes(p))).find(Boolean) || vozes[0] || null;
    }
    if ('speechSynthesis' in window) {
        escolherVoz();
        speechSynthesis.onvoiceschanged = escolherVoz;
    }

    function falarNavegador(texto) {
        return new Promise((resolve) => {
            if (!('speechSynthesis' in window)) return resolve();
            const u = new SpeechSynthesisUtterance(texto);
            u.lang = 'pt-BR';
            if (vozPT) u.voice = vozPT;
            u.rate = 1.04;
            u.pitch = 0.85;
            u.onend = u.onerror = () => resolve();
            speechSynthesis.speak(u);
        });
    }

    function pararFala() {
        token++;
        for (const it of fila) if (it.stream) liberarStream(it.stream);
        fila.length = 0;
        setEmocao(null);
        tocando = false;
        nivelSintetico = 0;
        try { fonteAtual && fonteAtual.stop(); } catch (_) {}
        fonteAtual = null;
        if ('speechSynthesis' in window) speechSynthesis.cancel();
    }

    function depoisDeFalar() {
        if (confirmacao) { setEstado('ouvindo'); return iniciarReconhecimento(); }
        if (turnoAtivo) return setEstado('pensando');
        if (dormindo) { apagarMusica(() => {}); return setEstado('espera'); }
        if (musica) {
            // o microfone só abre depois que a música some, para não "ouvir" a letra
            setEstado('espera');
            return apagarMusica(() => {
                if (turnoAtivo || tocando || dormindo) return;
                estenderConversa();
                setEstado('ouvindo');
                iniciarReconhecimento();
            });
        }
        estenderConversa();
        setEstado('ouvindo');
        iniciarReconhecimento();
    }

    // ------------------------------------------------------------ webcam (uma foto, sob demanda)
    const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

    async function capturarCamera(msg) {
        const pip = $('camera-pip'), video = $('camera-video'), cont = $('camera-contagem');
        let fluxo = null;
        const responder = (dados) => enviar({ tipo: 'foto_camera', id: msg.id, ...dados });
        try {
            fluxo = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
            video.srcObject = fluxo;
            await video.play();
            pip.hidden = false;
            if (window.Acoes) Acoes.cameraAbrir();
            const n = Math.max(1, Math.min(8, Math.round(msg.segundos || 3)));
            for (let i = n; i >= 1; i--) {      // dá tempo de se posicionar e da câmera ajustar a exposição
                cont.textContent = i;
                Sfx.tocar('scan');
                await esperar(1000);
            }
            cont.textContent = '';
            const largura = Math.min(1024, video.videoWidth || 1024);
            const altura = Math.round(largura * (video.videoHeight || 576) / (video.videoWidth || 1024));
            const tela = document.createElement('canvas');
            tela.width = largura;
            tela.height = altura;
            tela.getContext('2d').drawImage(video, 0, 0, largura, altura);
            const flash = $('flash-camera');
            if (window.Acoes) Acoes.cameraDisparo(tela);
            flash.classList.add('on');
            Sfx.tocar('camera');
            setTimeout(() => flash.classList.remove('on'), 160);
            responder({ imagem: tela.toDataURL('image/jpeg', 0.85).split(',')[1] });
        } catch (e) {
            const erro = (e.name === 'NotAllowedError' || e.name === 'SecurityError') ? 'permissao'
                : (e.name === 'NotFoundError' || e.name === 'OverconstrainedError') ? 'sem_camera'
                : (e.name === 'NotReadableError') ? 'ocupada' : (e.message || e.name || 'falha');
            responder({ erro });
        } finally {
            if (fluxo) fluxo.getTracks().forEach((t) => t.stop());   // apaga a luz da câmera
            video.srcObject = null;
            pip.hidden = true;
            cont.textContent = '';
        }
    }

    // ------------------------------------------------------------ música de abertura
    let temMusica = false, volumeMusica = 0.85, musicaInicio = 0, avisouSemMusica = false, musicaNaAbertura = false;
    let musica = null, musicaDesde = 0;
    const MUSICA_MIN_MS = 9000;     // a música toca ao menos isso antes de sumir

    function rampa(audio, alvo, ms, fim) {
        const ini = audio.volume, t0 = performance.now();
        const passo = () => {
            const k = Math.min(1, (performance.now() - t0) / ms);
            audio.volume = Math.max(0, Math.min(1, ini + (alvo - ini) * k));
            if (k < 1) requestAnimationFrame(passo); else if (fim) fim();
        };
        passo();
    }

    function tocarMusica(trilha = false) {
        if (gravando || (musica && trilha)) return;      // gravando: nada de música
        if (!temMusica) {
            if (!avisouSemMusica) {
                avisouSemMusica = true;
                aviso('Sem música de abertura: dê dois cliques em "Escolher-Musica.cmd" (pasta do Jarvis) e escolha o MP3.', 12000);
            }
            return;
        }
        pararMusica(true);
        const m = new Audio('/api/musica');
        m.volume = volumeMusica;
        if (musicaInicio > 0) m.addEventListener('loadedmetadata', () => { if (m.duration > musicaInicio + 5) m.currentTime = musicaInicio; }, { once: true });
        musica = m;
        musicaDesde = performance.now();
        m.play().catch(() => { if (musica === m) musica = null; });
    }

    function abaixarMusica() {
        if (musica) rampa(musica, volumeMusica * 0.14, 700);
    }

    // some devagar (respeitando o mínimo) e só então chama o próximo passo
    function apagarMusica(depois) {
        const m = musica;
        if (!m) return depois();
        const espera = Math.max(0, MUSICA_MIN_MS - (performance.now() - musicaDesde));
        setTimeout(() => rampa(m, 0, 2500, () => {
            m.pause();
            if (musica === m) musica = null;
            depois();
        }), espera);
    }

    function pararMusica(rapido) {
        const m = musica;
        musica = null;
        if (!m) return;
        if (rapido) { m.pause(); return; }
        rampa(m, 0, 400, () => m.pause());
    }

    // ------------------------------------------------------------ microfone (nível para o visual)
    async function abrirNivelDoMicrofone() {
        try {
            const fluxo = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
            const c = contexto();
            const fonte = c.createMediaStreamSource(fluxo);
            const an = c.createAnalyser();
            an.fftSize = 512;
            fonte.connect(an);               // não vai para os alto-falantes
            const dados = new Uint8Array(an.fftSize);
            micBuf = dados;
            const ler = () => {
                an.getByteTimeDomainData(dados);
                let soma = 0;
                for (let i = 0; i < dados.length; i++) { const v = (dados[i] - 128) / 128; soma += v * v; }
                nivelMic = Math.min(1, Math.sqrt(soma / dados.length) * 5);
                requestAnimationFrame(ler);
            };
            ler();
        } catch (_) { /* o reconhecimento mostra o aviso de permissão */ }
    }

    // ------------------------------------------------------------ modo gravação (direção de vídeo)
    let dir = null;     // { fluxo, timer, medidor, anterior, detector, ... } enquanto a câmera está ao vivo para a direção

    function medidasDoQuadro(video, estado) {
        const c = estado.mini || (estado.mini = document.createElement('canvas'));
        c.width = 96; c.height = 54;
        const g = c.getContext('2d', { willReadFrequently: true });
        g.drawImage(video, 0, 0, 96, 54);
        const px = g.getImageData(0, 0, 96, 54).data;
        const hist = new Uint16Array(256);
        let soma = 0, estourado = 0, mov = 0;
        const lum = new Uint8Array(96 * 54);
        for (let i = 0, k = 0; i < px.length; i += 4, k++) {
            const y = (px[i] * 0.299 + px[i + 1] * 0.587 + px[i + 2] * 0.114) | 0;
            lum[k] = y; hist[y]++; soma += y;
            if (y > 245) estourado++;
            if (estado.anterior) mov += Math.abs(y - estado.anterior[k]);
        }
        const n = lum.length;
        let acum = 0, p5 = 0, p95 = 255;
        for (let v = 0; v < 256; v++) { acum += hist[v]; if (!p5 && acum >= n * 0.05) p5 = v; if (acum >= n * 0.95) { p95 = v; break; } }
        const m = { brilho: soma / n, contraste: p95 - p5, estourado: estourado / n, movimento: estado.anterior ? mov / n : 0 };
        estado.anterior = lum;
        const mic = estado.mic.splice(0);
        m.mic_medio = mic.length ? mic.reduce((a, b) => a + b, 0) / mic.length : 0;
        m.mic_pico = mic.length ? Math.max(...mic) : 0;
        return m;
    }

    async function enviarQuadro() {
        if (!dir) return;
        const video = $('camera-video');
        if (!video.videoWidth) return;
        const m = medidasDoQuadro(video, dir);
        if (dir.detector) {
            try {
                const rostos = await dir.detector.detect(video);
                m.rosto = rostos.length ? { cx: (rostos[0].boundingBox.x + rostos[0].boundingBox.width / 2) / video.videoWidth,
                                            cy: (rostos[0].boundingBox.y + rostos[0].boundingBox.height / 2) / video.videoHeight,
                                            w: rostos[0].boundingBox.width / video.videoWidth } : false;
            } catch (_) { /* detecção indisponível */ }
        }
        const largura = Math.min(768, video.videoWidth);
        const tela = document.createElement('canvas');
        tela.width = largura;
        tela.height = Math.round(largura * video.videoHeight / video.videoWidth);
        tela.getContext('2d').drawImage(video, 0, 0, tela.width, tela.height);
        enviar({ tipo: 'quadro', imagem: tela.toDataURL('image/jpeg', 0.72).split(',')[1], metricas: m });
        $('dir-estado').textContent = 'Analisando o quadro...';
    }

    async function iniciarDirecao(msg) {
        const pip = $('camera-pip'), video = $('camera-video');
        if (dir) pararDirecao(false);
        try {
            const fluxo = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
            video.srcObject = fluxo;
            await video.play();
            fluxo.getVideoTracks()[0].addEventListener('ended', () => { if (dir) pararDirecao(true, 'a câmera foi desligada'); });
            dir = { fluxo, mic: [], anterior: null, mini: null, detector: ('FaceDetector' in window) ? new window.FaceDetector({ fastMode: true, maxDetectedFaces: 1 }) : null };
            dir.medidor = setInterval(() => dir.mic.push(nivelMic), 200);
            const seg = Math.max(10, Math.min(120, msg.intervalo || 25));
            dir.timer = setInterval(enviarQuadro, seg * 1000);
            setTimeout(enviarQuadro, 4000);                 // 1º quadro depois da câmera ajustar a exposição
            gravando = true;
            Sfx.silenciar(true);
            pararFala();
            pararMusica(true);
            pip.hidden = false;
            document.querySelector('.camera-tag').lastChild.textContent = 'DIREÇÃO · AO VIVO';
            $('direcao').hidden = false;
            $('dir-notas').innerHTML = '';
            $('dir-estado').textContent = 'Câmera ao vivo. Primeira análise em instantes...';
            enviar({ tipo: 'direcao_pronta', ok: true });
        } catch (e) {
            const erro = (e.name === 'NotAllowedError' || e.name === 'SecurityError') ? 'permissao'
                : (e.name === 'NotFoundError' || e.name === 'OverconstrainedError') ? 'sem_camera'
                : (e.name === 'NotReadableError') ? 'ocupada' : (e.message || e.name || 'falha');
            enviar({ tipo: 'direcao_pronta', ok: false, erro });
        }
    }

    function pararDirecao(avisarServidor, motivo) {
        if (dir) {
            clearInterval(dir.timer); clearInterval(dir.medidor);
            dir.fluxo.getTracks().forEach((t) => t.stop());     // apaga a luz da câmera
            dir = null;
        }
        const video = $('camera-video');
        video.srcObject = null;
        $('camera-pip').hidden = true;
        $('direcao').hidden = true;
        document.querySelector('.camera-tag').lastChild.textContent = 'CÂMERA';
        gravando = false;
        Sfx.silenciar(false);
        if (avisarServidor) enviar({ tipo: 'direcao_fim' });
        if (motivo) aviso(`Modo gravação encerrado: ${motivo}.`, 8000);
    }

    function pintarDirecao(msg) {
        if (!dir) return;
        if (msg.erro) { $('dir-estado').textContent = `Não consegui analisar este quadro (${msg.erro}). Vou tentar de novo.`; return; }
        $('dir-estado').textContent = `${msg.analises} quadros analisados · último há instantes · ${msg.dica ? 'dica nova' : 'tudo certo'}`;
        if (!msg.dica) return;
        const li = document.createElement('li');
        li.className = 'g' + msg.dica.gravidade;
        const m = Math.floor(msg.dica.t / 60), s = String(msg.dica.t % 60).padStart(2, '0');
        li.innerHTML = '<small></small><span></span>';
        li.querySelector('small').textContent = `${m}:${s} · ${msg.dica.categoria}${msg.dica.gravidade >= 2 ? ' · corrigir já' : ''}`;
        li.querySelector('span').textContent = msg.dica.texto;
        const lista = $('dir-notas');
        lista.prepend(li);
        while (lista.children.length > 4) lista.lastChild.remove();
    }
    $('dir-parar').addEventListener('click', () => pararDirecao(true));

    // ------------------------------------------------------------ reconhecimento de voz
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    let rec = null, querEscutar = false, escutando = false;

    // ------------------------------------------------------------ interromper falando
    // Com o microfone aberto enquanto o Jarvis fala, o Chrome também transcreve a voz dele (eco). Interrupcao.decidir compara
    // o que foi reconhecido com o que o Jarvis está dizendo: eco é ignorado, você falando por cima corta a fala e o turno.
    let interromperPorVoz = true;                 // ajustes.json: interromper_falando
    let ultimoFalado = '', fimDaFalaEm = 0;       // o "rabo" do eco: o Chrome finaliza a transcrição ~1 s depois que o áudio acaba
    let ultimaInterrupcaoEm = 0;
    const GRACA_ECO_MS = 4000;
    const falandoAgora = () => tocando || (estado === 'falando');
    const podeEscutarFalando = () => interromperPorVoz && !gravando && !mudo && !confirmacao;

    function tratarDuranteFala(item) {
        const falado = legendaJarvis.join(' ');
        const d = Interrupcao.decidir({
            texto: item.transcript, final: item.isFinal, confianca: item.confidence || 0, falado,
            exigeNome: midiaAtiva || !!musica,
        });
        if (d.acao !== 'interromper') return false;
        ultimaInterrupcaoEm = performance.now();
        interromper();
        if (d.parar) mostrarVoce(item.transcript.trim(), false);
        return true;
    }

    // ------------------------------------------------------------ métricas do lado do navegador (o servidor não vê esse tempo)
    const T = { ultimoParcialEm: 0, atrasoFinalMs: null, envioEm: 0, falaRecebidaEm: 0, audioTocouEm: 0, enviada: false };
    function marcarEnvio() { T.envioEm = performance.now(); T.falaRecebidaEm = 0; T.audioTocouEm = 0; T.enviada = false; }
    function marcarFalaRecebida() { if (T.envioEm && !T.falaRecebidaEm) T.falaRecebidaEm = performance.now(); }
    function marcarAudioTocando() {
        if (!T.envioEm || T.audioTocouEm) return;
        T.audioTocouEm = performance.now();
        if (T.enviada) return;
        T.enviada = true;
        enviar({ tipo: 'metrica', final_apos_parcial_ms: T.atrasoFinalMs,
                 envio_ate_fala_ms: T.falaRecebidaEm ? Math.round(T.falaRecebidaEm - T.envioEm) : null,
                 envio_ate_audio_ms: Math.round(T.audioTocouEm - T.envioEm),
                 chegada_ate_audio_ms: T.falaRecebidaEm ? Math.round(T.audioTocouEm - T.falaRecebidaEm) : null });
    }

    function processarResultados(lista) {
        let parcial = '';
        for (const r of lista) {
            const agora = performance.now();
            if (falandoAgora() && !confirmacao) {                   // Jarvis falando: eco ou interrupção?
                if (podeEscutarFalando()) tratarDuranteFala(r);
                continue;
            }
            if (!r.isFinal) { T.ultimoParcialEm = agora; }
            if (r.isFinal) {
                const texto = r.transcript.trim();
                T.atrasoFinalMs = T.ultimoParcialEm ? Math.round(agora - T.ultimoParcialEm) : null;
                duckAvisado = false;
                if (!confirmacao) {
                    // o rabo do eco: a transcrição da última frase do Jarvis chega logo depois que ele termina de falar
                    if (agora - fimDaFalaEm < GRACA_ECO_MS && Interrupcao.sobreposicao(texto, ultimoFalado) >= 0.6) { decisao(r, 'ignorou', 'eco da voz do Jarvis'); continue; }
                    // acabou de ser cortado por "para"/"chega": o final desse pedido não vira um comando
                    if (agora - ultimaInterrupcaoEm < GRACA_ECO_MS && Interrupcao.ehPedidoDeParar(texto)) { decisao(r, 'ignorou', 'final do pedido de parar'); continue; }
                    const chamou = chamouMesmo(texto);
                    // sem o meu nome: ignora (conversa ao fundo, TV, letra de música). A janela pós-pergunta não vale com música tocando.
                    if ((exigeChamada || midiaAtiva || gravando) && !chamou && !(naJanela() && !midiaAtiva)) { decisao(r, 'ignorou', 'sem o nome Jarvis e fora da conversa'); continue; }
                    if (r.confidence > 0 && r.confidence < (r.id ? CONFIANCA_LOCAL_MIN : CONFIANCA_MIN)) { decisao(r, 'ignorou', 'confiança baixa (' + r.confidence + ')'); continue; }
                    if (conversaEncerrada) { /* já despediu: o próximo turno encerra */ } else janelaAte = performance.now() + janelaConversaMs;
                }
                if (confirmacao) {
                    const resp = interpretarConfirmacao(texto);
                    mostrarVoce(texto, false);
                    if (resp !== null) responderConfirmacao(resp);
                } else if (texto.length > 1) { decisao(r, 'enviou', naJanela() ? 'dentro da conversa' : 'chamou pelo nome'); enviarFala(texto); }
            } else {
                parcial += r.transcript;
            }
        }
        if (parcial) {
            if (midiaAtiva && !duckAvisado && CHAMOU_JARVIS.test(parcial)) {
                duckAvisado = true;
                enviar({ tipo: 'duck' });      // abaixa a música enquanto você fala o comando
            }
            if ((!exigeChamada && !midiaAtiva) || CHAMOU_JARVIS.test(parcial) || (naJanela() && !midiaAtiva)) mostrarVoce(parcial, true);
        }
    }

    function criarReconhecimento() {
        rec = new SR();
        rec.lang = 'pt-BR';
        rec.continuous = true;
        rec.interimResults = true;
        rec.onstart = () => { escutando = true; };
        rec.onresult = (e) => {
            const lista = [];
            for (let i = e.resultIndex; i < e.results.length; i++) {
                const r = e.results[i];
                lista.push({ transcript: r[0].transcript, isFinal: r.isFinal, confidence: r[0].confidence });
            }
            processarResultados(lista);
        };
        rec.onend = () => {
            escutando = false;
            if (querEscutar && !mudo) setTimeout(iniciarReconhecimento, 250);
        };
        rec.onerror = (e) => {
            if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
                querEscutar = false;
                aviso('O Chrome bloqueou o microfone. Clique no cadeado ao lado do endereço e permita.', 12000);
            } else if (e.error === 'network') {
                aviso('O reconhecimento de voz do Chrome precisa de internet.');
            }
        };
    }

    // ------------------------------------------------------------ motor de voz: o do Chrome x o PRÓPRIO (servidor, stt.py)
    // Dentro do app Electron não existe reconhecedor do Chrome (dá erro 'network'): lá a voz é sempre a própria.
    const NA_CASCA = new URLSearchParams(location.search).get('shell') === 'electron';
    let motorVoz = NA_CASCA ? 'local' : 'chrome';      // ajustes.json: "stt": "local" também liga no Chrome
    let sttPronto = false, sttPedido = false;
    const usaLocal = () => motorVoz === 'local';

    async function iniciarLocal() {
        if (mudo || dormindo || (tocando && !podeEscutarFalando())) return;
        querEscutar = true; escutando = true;
        try {
            await SttLocal.iniciar((buf) => { if (ws && ws.readyState === WebSocket.OPEN) ws.send(buf); });
        } catch (e) {
            querEscutar = false; escutando = false;
            aviso('Não consegui abrir o microfone (' + ((e && e.name) || e) + '). Confira a permissão e o microfone padrão do Windows.', 12000);
            return;
        }
        if (!querEscutar) return;                      // parou enquanto o microfone abria
        if (!sttPedido) { sttPedido = true; enviar({ tipo: 'stt', ligar: true }); }
        SttLocal.ligar(sttPronto);
    }

    function pararLocal() {
        querEscutar = false; escutando = false;
        SttLocal.ligar(false);
        if (sttPedido) { sttPedido = false; enviar({ tipo: 'stt', ligar: false }); }
    }

    function iniciarReconhecimento() {
        if (usaLocal()) return iniciarLocal();
        if (!SR) { aviso('Este navegador não tem reconhecimento de voz. Use o Chrome ou o Edge.', 12000); return; }
        if (mudo || dormindo || (tocando && !podeEscutarFalando())) return;
        querEscutar = true;
        if (!rec) criarReconhecimento();
        if (escutando) return;
        try { rec.start(); } catch (_) { /* já iniciado */ }
    }

    function pararReconhecimento() {
        if (usaLocal()) return pararLocal();
        querEscutar = false;
        if (rec && escutando) { try { rec.stop(); } catch (_) {} }
    }

    // ------------------------------------------------------------ conexão
    function conectar() {
        ws = new WebSocket(`ws://${location.host}/ws${AUTO ? '?app=1' : ''}`);
        ws.onopen = () => {
            $('i-conexao').textContent = 'LOCAL';
            enviar({ tipo: 'capacidades', stream_audio: SUPORTA_STREAM });      // o servidor só manda áudio em pedaços para quem sabe tocar
            if (estado === 'offline') setEstado('espera');
            sttPedido = false;
            if (usaLocal() && querEscutar) iniciarLocal();       // reconectou: pede a escuta própria de novo
            if (!conectadoUmaVez) {
                conectadoUmaVez = true;
                if (AUTO) iniciar();
            }
        };
        ws.onmessage = (ev) => tratar(JSON.parse(ev.data));
        ws.onclose = () => {
            $('i-conexao').textContent = 'OFF';
            pararFala();
            pararMusica(true);
            pararReconhecimento();
            turnoAtivo = false;
            setEstado('offline');
            setTimeout(conectar, 2000);
        };
    }

    function enviar(obj) {
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
    }

    function tratar(msg) {
        switch (msg.tipo) {
            case 'painel': pintarPainel(msg); break;
            case 'memoria':
                pintarMemoria(msg);
                Grafo.carregar();                                  // memória nova nasce no grafo
                if (msg.texto) { toastMemoria(msg.texto); Sfx.tocar('memoria'); ativarPaineis(['memoria'], 3); }
                break;
            case 'cerebro':                                        // o que o Jarvis usou nesta resposta acende
                Grafo.acender(msg);
                ativarPaineis(['memoria'], 3.5);
                break;
            case 'ui': UI.comando(msg); break;
            case 'sistema': pintarSistema(msg); break;
            case 'pensando':
                turnoAtivo = true;
                dormindo = false;
                if (!tocando) setEstado('pensando');
                break;
            case 'fala': receberFala(msg); break;
            case 'fala_ini': receberFalaStream(msg); break;
            case 'fala_chunk': { const st = streams.get(msg.id); if (st) { st.fila.push(b64ParaBuffer(msg.audio)); bombear(st); } break; }
            case 'fala_fim': { const st = streams.get(msg.id); if (st) { st.fim = true; bombear(st); } break; }
            case 'fim':
                turnoAtivo = false;
                if (!tocando) depoisDeFalar();
                break;
            case 'ferramenta':
                pintarFerramenta(msg);
                if (window.Acoes) Acoes.evento(msg);
                if (msg.estado === 'inicio') ativarPaineis(PAINEL_DO_ROTULO[msg.rotulo] || ['nucleo'], 4);
                if (msg.estado === 'erro') Sfx.tocar('erro');
                else if (msg.estado === 'fim') Sfx.tocar('ok');
                else if (msg.estado === 'inicio' && msg.rotulo !== 'CONTROLE') Sfx.tocar('scan');
                break;
            case 'dormir': dormindo = true; break;
            case 'midia': midiaAtiva = !!msg.ativa; break;
            case 'capturar_camera': capturarCamera(msg); break;
            case 'tocar_musica': if (musicaNaAbertura) tocarMusica(); if (!musicaNaAbertura || !temMusica) Sfx.tocar('ativacao'); break;
            case 'chamado':                                          // "hey Jarvis" detectado pelo modelo local: abre a conversa e interrompe se ele estava falando
                if (estado === 'falando' || estado === 'pensando') interromper();
                conversaEncerrada = false; janelaAte = performance.now() + janelaConversaMs;
                Sfx.tocar('recebi'); if (window.Acoes) Acoes.onda(0.5);
                break;
            case 'mouse_modo': { mouseNoAr = !!msg.ativo; if (window.Gestos) Gestos.mouse(mouseNoAr); const p = $('pill-mouse'); if (p) p.classList.toggle('on', mouseNoAr); break; }
            case 'mouse_pedido': alternarMouse(!!msg.ativo); break;
            case 'tela_ao_vivo': { const p = $('pill-tela'); if (p) p.classList.toggle('on', !!msg.ativo); break; }
            case 'conversa': if (msg.ativa === false) { conversaEncerrada = true; janelaAte = 0; } break;   // tchau / me aguarda
            case 'direcao_iniciar': iniciarDirecao(msg); break;
            case 'direcao_parar': pararDirecao(false, msg.motivo); break;
            case 'direcao': pintarDirecao(msg); break;
            case 'trilha':                                         // o Jarvis liga a trilha numa tarefa grande ou sob pressão
                if (msg.acao === 'iniciar') tocarMusica(true);
                else apagarMusica(() => {});
                break;
            case 'confirmar': mostrarConfirmacao(msg); break;
            case 'confirmar_fim': if (confirmacao && confirmacao.id === msg.id) fecharConfirmacao(); break;
            case 'controle':
                document.body.classList.toggle('controle', !!msg.ativo);
                Sfx.tocar(msg.ativo ? 'controle_on' : 'controle_off');
                break;
            case 'aviso': aviso(msg.texto); break;
            case 'stt_estado':                                     // o servidor avisa se a escuta própria está pronta
                if (msg.estado === 'pronto') {
                    sttPronto = true;
                    if (querEscutar && !mudo) SttLocal.ligar(true);
                    aviso(`Escuta própria ativa (${msg.dispositivo}).`, 3500);
                } else if (msg.estado === 'carregando') {
                    aviso('Carregando o reconhecimento de voz...', 4000);
                } else {
                    sttPronto = false; sttPedido = false;
                    aviso('Reconhecimento de voz próprio indisponível: ' + (msg.motivo || msg.estado), 14000);
                    if (SR && !NA_CASCA) { motorVoz = 'chrome'; SttLocal.ligar(false); if (querEscutar) iniciarReconhecimento(); }   // no Chrome ainda dá para usar o dele
                }
                break;
            case 'transcricao':                                    // fala reconhecida pelo servidor: mesmo caminho que o Chrome usava
                T.atrasoFinalMs = msg.transcricao_ms || null;
                processarResultados([{ transcript: msg.texto, isFinal: true, confidence: msg.confianca }]);
                break;
            case 'vad':                                            // o servidor ouviu você começar/parar de falar
                document.body.dataset.vad = msg.fala ? '1' : '0';
                if (msg.fala && !falandoAgora() && !confirmacao) mostrarVoce('…', true);
                break;
        }
    }

    // ------------------------------------------------------------ ações do usuário
    // A abertura só pode decidir "tem música?" depois do 1º painel do servidor (ele diz se há arquivo em musica\).
    let painelRecebido = false, aoReceberPainel = [];
    function esperarPainel(maxMs = 2500) {
        if (painelRecebido) return Promise.resolve();
        return new Promise((resolve) => {
            const fim = () => { clearTimeout(t); resolve(); };
            const t = setTimeout(fim, maxMs);
            aoReceberPainel.push(fim);
        });
    }

    function iniciar() {
        $('inicio').classList.add('oculto');
        contexto();
        abrirNivelDoMicrofone();
        esperarPainel().then(() => {
            if (musicaNaAbertura) tocarMusica();
            if (!musicaNaAbertura || !temMusica) Sfx.tocar('ativacao');
            dormindo = false;
            enviar({ tipo: 'ativar' });
        });
    }

    // ---- frase curta pré-gravada se a resposta demora: o silêncio é o que dá a sensação de lentidão
    let fillers = null, fillerAnterior = -1, fillerTimer = 0;
    const FILLER_APOS_MS = 1000;
    async function carregarFillers() {
        if (fillers) return fillers;
        fillers = [];
        try {
            const lista = (await (await fetch('/api/fillers')).json()).itens || [];
            for (const i of lista) {
                const dados = await (await fetch('/api/filler/' + i)).arrayBuffer();
                fillers.push({ i, buffer: await contexto().decodeAudioData(dados) });
            }
        } catch (_) { /* sem fillers: segue sem */ }
        return fillers;
    }
    function agendarFiller() {
        clearTimeout(fillerTimer);
        carregarFillers();
        if (MUDO) return;
        const meu = T.envioEm;
        fillerTimer = setTimeout(() => {
            if (T.envioEm !== meu || T.falaRecebidaEm || tocando || fila.length || !turnoAtivo || !fillers || !fillers.length) return;
            const opcoes = fillers.filter((f) => f.i !== fillerAnterior);
            const f = opcoes[Math.floor(Math.random() * opcoes.length)];
            fillerAnterior = f.i;
            fila.push({ texto: '', emocao: null, buffer: f.buffer, pronto: null, filler: true });
            tocar();
        }, FILLER_APOS_MS);
    }

    function enviarFala(texto) {
        pararMusica(false);
        pararFala();
        pararReconhecimento();
        legendaJarvis = [];
        $('legenda-jarvis').textContent = '';
        mostrarVoce(texto, false);
        marcarEnvio();
        enviar({ tipo: 'fala', texto });
        setEstado('pensando');             // feedback imediato: o reator reage já, sem esperar o servidor
        Sfx.tocar('recebi');
        agendarFiller();
    }

    function interromper() {
        if (confirmacao) return responderConfirmacao(false);
        if (estado !== 'falando' && estado !== 'pensando' && !musica) return;
        ultimoFalado = legendaJarvis.join(' '); fimDaFalaEm = performance.now();
        pararMusica(false);
        pararFala();
        enviar({ tipo: 'parar' });
        turnoAtivo = false;
        depoisDeFalar();
    }

    $('botao-iniciar').addEventListener('click', iniciar);
    $('reator').addEventListener('click', () => {
        if (!$('inicio').classList.contains('oculto')) return;
        if (estado === 'falando' || estado === 'pensando') interromper();
        else if (estado === 'espera') { dormindo = false; enviar({ tipo: 'ativar' }); }
    });

    $('form-comando').addEventListener('submit', (e) => {
        e.preventDefault();
        const campo = $('comando');
        const texto = campo.value.trim();
        if (texto) { enviarFala(texto); campo.value = ''; campo.blur(); }
    });

    document.addEventListener('keydown', (e) => {
        const digitando = document.activeElement === $('comando');
        if (digitando) { if (e.key === 'Escape') $('comando').blur(); return; }
        if (confirmacao) { if (e.key === 'Escape') responderConfirmacao(false); return; }
        if (e.key === '/') { e.preventDefault(); $('comando').focus(); }
        else if (e.key === ' ' || e.key === 'Escape') { e.preventDefault(); interromper(); }
        else if (e.key === 'm' || e.key === 'M') alternarMudo();
        else if (e.key === 'g' || e.key === 'G') alternarGestos();
        else if (e.key === 'b' || e.key === 'B') { if (window.UI) UI.alternarFoco(); }
        else if (e.key === 't' || e.key === 'T') abrirConversa();
        else if (e.key === 'f' || e.key === 'F') {
            if (document.fullscreenElement) document.exitFullscreen();
            else document.documentElement.requestFullscreen().catch(() => {});
        }
    });

    document.querySelector('.status-pill').addEventListener('click', abrirConversa);
    if ($('pill-tela')) $('pill-tela').addEventListener('click', () => enviar({ tipo: 'tela_ao_vivo', ativo: !$('pill-tela').classList.contains('on') }));
    document.querySelector('.status-pill').style.cursor = 'pointer';

    function alternarMudo() {
        mudo = !mudo;
        if (mudo) pararReconhecimento(); else if (estado === 'ouvindo') iniciarReconhecimento();
        setEstado(estado);
        aviso(mudo ? 'Microfone silenciado.' : 'Microfone ativo.', 2500);
    }

    // ------------------------------------------------------------ gestos por câmera (ligados só por escolha; ver gestos.js)
    // Palma aberta parada: interrompe o Jarvis falando; se ele está quieto, ARMA os gestos por 8 s. Só então valem deslizar, pinça e punho.
    // Cabeça: "não" cancela uma confirmação; "sim" NUNCA confirma ação (só por voz ou clique). Fora de confirmação, vale como resposta a uma pergunta dele.
    let armadoAte = 0;
    const armado = () => performance.now() < armadoAte;
    function chipGesto(texto, ok = true) {
        if (!window.Acoes) return;
        const id = 'g' + Math.random().toString(36).slice(2, 7);
        Acoes.evento({ id, estado: 'inicio', rotulo: 'GESTO', detalhe: texto });
        setTimeout(() => Acoes.evento({ id, estado: ok ? 'fim' : 'erro', rotulo: 'GESTO' }), 500);
    }
    function armar() {
        armadoAte = performance.now() + 8000;
        document.body.classList.add('gestos-armado');
        clearTimeout(armar.t);
        armar.t = setTimeout(() => { if (!armado()) document.body.classList.remove('gestos-armado'); }, 8100);
    }
    function respostaComACabeca(sim) {
        const perguntou = /\?\s*$/.test((ultimoFalado || '').trim());
        if (!perguntou || estado === 'falando' || !fimDaFalaEm || performance.now() - fimDaFalaEm > 9000) return;
        chipGesto('cabeça: ' + (sim ? 'sim' : 'não'));
        enviarFala(sim ? 'Sim.' : 'Não.');
    }
    function tratarGesto(ev) {
        const g = ev.tipo;
        if (g === 'arrastar' || g === 'pinca_fim') return;
        if (mouseNoAr) { if (g === 'palma') alternarMouse(false); return; }              // no mouse no ar a pinça é o clique: as ações de mídia ficam de fora
        if (g === 'palma') {
            if (estado === 'falando' || estado === 'pensando') { interromper(); chipGesto('palma: parar'); }
            else { armar(); Sfx.tocar('ui'); chipGesto('gestos armados (8 s)'); }
            return;
        }
        if (g === 'cabeca_nao') { if (confirmacao) { chipGesto('não: cancelado'); responderConfirmacao(false); } else respostaComACabeca(false); return; }
        if (g === 'cabeca_sim') { if (confirmacao) aviso('Por segurança, confirme por voz ou clique.', 3500); else respostaComACabeca(true); return; }
        if (!armado()) return;
        armar();
        if (g === 'punho') { alternarMudo(); chipGesto(mudo ? 'punho: microfone mudo' : 'punho: microfone ativo'); }
        else if (g.startsWith('deslizar') || g === 'pinca') enviar({ tipo: 'gesto', nome: g });      // o servidor faz a ação de mídia e devolve a etiqueta
    }
    // ---- MOUSE NO AR: só o usuário liga (botão MOUSE ou voz). O servidor aplica o ponteiro, o clique, a rolagem e o zoom; ESC, palma parada ou desligar soltam tudo.
    let mouseNoAr = false, ultimoMover = 0;
    async function alternarMouse(ligar) {
        if (!window.Gestos || !Gestos.disponivel()) { aviso('Gestos indisponíveis neste computador.', 3000); return; }
        if (ligar === undefined) ligar = !mouseNoAr;
        if (ligar && !Gestos.estado().ligado) await alternarGestos(true);
        if (ligar && !Gestos.estado().ligado) return;
        mouseNoAr = !!ligar && Gestos.mouse(true);
        if (!ligar) Gestos.mouse(false);
        enviar({ tipo: 'mouse_modo', ativo: mouseNoAr });
        const p = $('pill-mouse'); if (p) p.classList.toggle('on', mouseNoAr);
        aviso(mouseNoAr ? 'Mouse no ar ligado: a ponta do indicador move o ponteiro. Palma aberta parada, ESC ou o botão MOUSE desligam.' : 'Mouse no ar desligado.', 5000);
    }
    if (window.Gestos) {
        Gestos.ao('mouse', (ev) => {
            if (!mouseNoAr) return;
            if (ev.tipo === 'mover') { const agora = performance.now(); if (agora - ultimoMover < 14) return; ultimoMover = agora; }
            enviar({ tipo: 'mouse', acao: ev.tipo, x: ev.x, y: ev.y, passos: ev.passos });
        });
        $('pill-mouse').addEventListener('click', () => alternarMouse());
    }
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && mouseNoAr) alternarMouse(false); });

    async function alternarGestos(ligar) {
        if (!window.Gestos || !Gestos.disponivel()) { aviso('Gestos indisponíveis neste computador.', 3000); return; }
        if (ligar === undefined) ligar = !Gestos.estado().ligado;
        if (ligar) {
            aviso('Ligando os gestos (a câmera acende)...', 4000);
            const e = await Gestos.ligar();
            if (e.ligado) { try { localStorage.setItem('jarvis_gestos', '1'); } catch (_) {} aviso('Gestos ligados. Palma aberta parada arma os gestos.', 4500); }
            else aviso('Gestos indisponíveis: ' + (e.erro || 'falha') + '.', 6000);
        } else { Gestos.desligar(); try { localStorage.removeItem('jarvis_gestos'); } catch (_) {} aviso('Gestos desligados. A câmera apagou.', 3000); }
    }
    if (window.Gestos) {
        Gestos.ao('gesto', tratarGesto);
        Gestos.ao('estado', (e) => {
            document.body.classList.toggle('gestos-on', !!e.ligado);
            document.body.classList.toggle('gestos-carregando', !!e.carregando);
            const p = $('pill-gestos'); if (p) { p.classList.toggle('on', !!e.ligado); p.querySelector('span').textContent = e.carregando ? 'CARREGANDO' : 'GESTOS'; }
        });
        $('pill-gestos').addEventListener('click', () => alternarGestos());
        let pediuGestos = false; try { pediuGestos = localStorage.getItem('jarvis_gestos') === '1'; } catch (_) {}
        if (pediuGestos && !MUDO) setTimeout(() => alternarGestos(true), 4000);          // lembra a escolha; em testes (?mudo=1) nunca liga sozinho
    }

    // áudio bloqueado pelo navegador até haver um clique
    document.addEventListener('click', () => { if (ctx && ctx.state === 'suspended') ctx.resume(); });
    setInterval(() => {
        if (AUTO && ctx && ctx.state === 'suspended' && $('inicio').classList.contains('oculto')) {
            $('inicio').classList.remove('oculto');
        }
    }, 1500);

    // ------------------------------------------------------------ confirmação
    const sem = (t) => t.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    function interpretarConfirmacao(texto) {
        const t = sem(texto);
        if (/\b(nao|cancela|cancelar|cancelado|negativo|para|pare|deixa|esquece|desiste)\b/.test(t)) return false;
        if (/\b(confirmo|confirmado|confirma|autorizo|pode (fazer|executar|ir|sim|continuar)|sim|isso|vai|manda ver)\b/.test(t)) return true;
        return null;
    }

    function mostrarConfirmacao(m) {
        confirmacao = { id: m.id };
        $('conf-titulo').textContent = m.titulo;
        const ul = $('conf-detalhes');
        ul.replaceChildren();
        for (const d of m.detalhes || []) {
            const li = document.createElement('li');
            li.textContent = d;
            ul.append(li);
        }
        const barra = $('conf-barra');
        barra.style.transition = 'none';
        barra.style.transform = 'scaleX(1)';
        requestAnimationFrame(() => requestAnimationFrame(() => {
            barra.style.transition = 'transform 120s linear';
            barra.style.transform = 'scaleX(0)';
        }));
        $('confirmacao').hidden = false;
        Sfx.tocar('alerta');
    }

    function fecharConfirmacao() {
        confirmacao = null;
        $('confirmacao').hidden = true;
    }

    function responderConfirmacao(ok) {
        if (!confirmacao) return;
        enviar({ tipo: 'confirmacao', id: confirmacao.id, ok });
        fecharConfirmacao();
        pararReconhecimento();
        Sfx.tocar(ok ? 'confirmado' : 'negado');
        setEstado('pensando');
    }
    $('conf-sim').addEventListener('click', () => responderConfirmacao(true));
    $('conf-nao').addEventListener('click', () => responderConfirmacao(false));

    // ------------------------------------------------------------ legenda
    let legendaJarvis = [];
    function mostrarVoce(texto, parcial) {
        const el = $('legenda-voce');
        el.textContent = texto;
        el.classList.toggle('parcial', parcial);
    }
    function addJarvis(texto) {
        legendaJarvis.push(texto);
        $('legenda-jarvis').textContent = legendaJarvis.slice(-2).join(' ');
    }

    // ------------------------------------------------------------ painéis
    function pintarPainel(p) {
        if (p.stt === 'local' && p.stt_disponivel) motorVoz = 'local';
        else if (NA_CASCA && p.stt_disponivel === false && !pintarPainel.avisouStt) {
            pintarPainel.avisouStt = true;
            aviso('Falta o modelo do reconhecimento de voz próprio: rode scripts\\baixar_modelo_whisper.py.', 14000);
        }
        const c = p.clima;
        $('clima-temp').textContent = c ? `${c.temp}°` : '--°';
        $('clima-desc').textContent = c ? c.descricao : 'Sem dados';
        $('clima-extra').textContent = c ? `${c.cidade} · sensação ${c.sensacao}° · umidade ${c.umidade}% · vento ${c.vento} km/h` : '';
        $('i-modelo').textContent = p.modelo;
        if ($('i-custo') && p.custo_usd !== undefined) $('i-custo').textContent = 'US$ ' + p.custo_usd.toFixed(3) + ' / ' + p.orcamento_usd.toFixed(2);
        $('i-voz').textContent = p.voz;
        if (p.local) {
            const cidade = (p.local.cidade || '').toUpperCase();
            $('radar-legenda').textContent = p.local.lat != null ? `${cidade} ${p.local.lat.toFixed(2)}° ${p.local.lon.toFixed(2)}°` : cidade;
        }
        pintarManchetes(p.manchetes);
        pintarAgenda(p.agenda);
        temMusica = !!p.musica;
        if (!painelRecebido) { painelRecebido = true; aoReceberPainel.splice(0).forEach((f) => f()); }
        if (p.musica_volume) volumeMusica = p.musica_volume;
        musicaInicio = p.musica_inicio || 0;
        musicaNaAbertura = !!p.musica_abertura;
        exigeChamada = p.exigir_chamada !== false;
        interromperPorVoz = p.interromper_falando !== false;
        if (p.janela_conversa >= 0) janelaConversaMs = p.janela_conversa * 1000;

        pintarMemoria(p.memoria);
        if (!p.tem_chave) aviso('Falta a chave da Anthropic no config.json. Sem ela o Jarvis não consegue pensar.', 15000);
    }

    function pintarMemoria(m) {
        if (!m) return;
        $('mem-total').textContent = m.total;
        $('mem-notas').textContent = m.notas;
    }

    function pintarAgenda(a) {
        const ul = $('ag-lista');
        ul.replaceChildren();
        const linha = (texto, classe) => { const li = document.createElement('li'); li.textContent = texto; if (classe) li.className = classe; ul.append(li); return li; };
        if (!a || !a.conectado) {
            $('ag-naolidos').textContent = '--';
            $('ag-legenda').textContent = a && a.configurado ? 'Google pronto para conectar' : 'Google não configurado';
            linha(a && a.configurado ? 'Diga "conecta meu Google".' : 'Veja GOOGLE-SETUP.md.', 'vazio');
            return;
        }
        $('ag-naolidos').textContent = a.nao_lidos == null ? '--' : a.nao_lidos;
        $('ag-legenda').textContent = 'e-mails não lidos';
        if (!a.proximos || !a.proximos.length) linha('Nada marcado nos próximos dias.', 'vazio');
        for (const e of a.proximos || []) {
            const li = linha('', '');
            const q = document.createElement('i'); q.textContent = e.quando;
            li.append(document.createTextNode(e.titulo), q);
            li.title = `${e.titulo} — ${e.quando}`;
        }
        if (a.erro) linha(a.erro.slice(0, 70), 'vazio');
    }

    // letreiro de manchetes (só reconstrói se mudou, para a animação não reiniciar à toa)
    let manchetesAtuais = '';
    function pintarManchetes(lista) {
        const trilho = $('ticker-trilho');
        const chave = (lista || []).join('|');
        if (chave === manchetesAtuais) return;
        manchetesAtuais = chave;
        trilho.replaceChildren();
        for (const m of lista && lista.length ? lista : ['Sem manchetes no momento']) {
            trilho.append(document.createTextNode(m));
            const sep = document.createElement('b');
            sep.textContent = '◆';
            trilho.append(sep);
        }
        trilho.style.animationDuration = Math.max(45, trilho.textContent.length * 0.2) + 's';
    }

    // painéis que acendem conforme o que o Jarvis faz
    const PAINEL_DO_ROTULO = {
        AGENDA: ['agenda'], 'E-MAIL': ['agenda'], GOOGLE: ['agenda'],
        COFRE: ['memoria'], OBSIDIAN: ['memoria'], 'MEMÓRIA': ['memoria'],
        PESQUISA: ['rede'], LEITURA: ['rede'], ABRINDO: ['rede'], 'NOTÍCIAS': ['rede', 'manchetes'], YOUTUBE: ['rede'],
        'MÍDIA': ['rede'], NAVEGADOR: ['rede'], WINDOWS: ['sistema', 'processos'], ARQUIVOS: ['sistema', 'processos'],
        CONTROLE: ['sistema', 'processos'], 'CÂMERA': ['clima'], 'VISÃO': ['sistema'], PROGRAMA: ['processos'], INTERFACE: ['nucleo'],
    };
    function ativarPaineis(ids, segundos) {
        if (window.Acoes) Acoes.foco(ids, segundos);
        for (const id of ids) {
            document.querySelectorAll(`.painel[data-painel="${id}"]`).forEach((el) => {
                el.classList.add('pulsando');
                setTimeout(() => el.classList.remove('pulsando'), segundos * 1000);
            });
            Fluxos.ativar(id, segundos);
        }
    }

    let toastTimer = null;
    function toastMemoria(texto) {
        const el = $('toast-memoria');
        el.textContent = '';
        const tag = document.createElement('b');
        tag.textContent = 'MEMÓRIA ATUALIZADA';
        el.append(tag, document.createTextNode(texto));
        el.classList.add('visivel');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => el.classList.remove('visivel'), 6000);
    }

    function medidor(id, pct, texto) {
        const barra = $('b-' + id);
        barra.style.width = Math.max(0, Math.min(100, pct)) + '%';
        barra.classList.toggle('alto', pct >= 85);
        $('v-' + id).textContent = texto;
    }
    const graficos = {};
    function criarGraficos() {
        graficos.cpu = new Visual.Spark($('g-cpu'), { max: 100 });
        graficos.ram = new Visual.Spark($('g-ram'), { max: 100 });
        graficos.rede = new Visual.Spark($('g-rede'), { linhas: 2 });
        graficos.gpu = new Visual.Spark($('g-gpu'), { max: 100 });
    }

    function bytes(b) {
        if (b >= 1e6) return (b / 1e6).toFixed(1) + ' MB/s';
        if (b >= 1e3) return Math.round(b / 1e3) + ' KB/s';
        return Math.round(b) + ' B/s';
    }

    function pintarSistema(s) {
        $('v-cpu').textContent = Math.round(s.cpu) + '%';
        graficos.cpu && graficos.cpu.push(s.cpu);
        const nuc = $('nucleos');
        while (nuc.children.length < (s.nucleos || []).length) nuc.append(document.createElement('i'));
        (s.nucleos || []).forEach((v, i) => {
            nuc.children[i].style.height = Math.max(8, v) + '%';
            nuc.children[i].classList.toggle('alto', v >= 85);
        });
        $('v-ram').textContent = Math.round(s.ram) + '%';
        graficos.ram && graficos.ram.push(s.ram);
        medidor('disco', s.disco, Math.round(s.disco) + '%');
        if (s.bateria) medidor('bat', s.bateria.pct, s.bateria.pct + '%' + (s.bateria.tomada ? ' ⚡' : ''));
        else $('linha-bateria').style.display = 'none';
        Visual.fps(s.bateria && !s.bateria.tomada ? 15 : 30);      // economiza bateria

        if (s.rede) {
            $('v-rede').textContent = bytes(s.rede.down + s.rede.up);
            $('v-down').textContent = bytes(s.rede.down);
            $('v-up').textContent = bytes(s.rede.up);
            graficos.rede && graficos.rede.push(s.rede.down, s.rede.up);
        }
        $('v-ping').textContent = s.ping_ms != null ? s.ping_ms + ' ms' : '--';
        if (s.disco_io) $('v-dio').textContent = bytes(s.disco_io.leitura + s.disco_io.escrita);
        if (s.gpu) {
            $('v-gpu').textContent = Math.round(s.gpu.uso) + '%';
            graficos.gpu && graficos.gpu.push(s.gpu.uso);
            medidor('vram', (s.gpu.vram_usada / s.gpu.vram_total) * 100, `${Math.round(s.gpu.temp)}°C · ${Math.round(s.gpu.vram_usada)} MB`);
        } else {
            $('v-gpu').textContent = 'N/D';
        }
        if (s.procs) pintarProcessos(s.procs);
        const h = Math.floor((s.uptime_s || 0) / 3600), m = Math.floor(((s.uptime_s || 0) % 3600) / 60);
        $('i-uptime').textContent = `${h} h ${m} min`;
    }

    function pintarProcessos(lista) {
        const ul = $('lista-procs');
        ul.replaceChildren();
        const topo = Math.max(5, ...lista.map((p) => p.cpu));
        for (const p of lista) {
            const li = document.createElement('li');
            li.title = `${p.nome}: ${p.ram_mb} MB de RAM`;
            const nome = document.createElement('span'); nome.className = 'nome'; nome.textContent = p.nome;
            const mini = document.createElement('span'); mini.className = 'mini';
            const barra = document.createElement('b'); barra.style.width = Math.min(100, (p.cpu / topo) * 100) + '%'; mini.append(barra);
            const val = document.createElement('span'); val.className = 'val'; val.textContent = p.cpu.toFixed(1) + '%';
            li.append(nome, mini, val);
            ul.append(li);
        }
    }

    function pintarFerramenta(m) {
        const lista = $('atividade');
        lista.querySelector('.vazio')?.remove();
        let li = lista.querySelector(`[data-id="${CSS.escape(m.id)}"]`);
        if (!li) {
            li = document.createElement('li');
            li.dataset.id = m.id;
            const tag = document.createElement('span'); tag.className = 'tag'; tag.textContent = m.rotulo;
            const det = document.createElement('span'); det.className = 'det'; det.textContent = m.detalhe;
            const ponto = document.createElement('span'); ponto.className = 'ponto';
            li.append(tag, det, ponto);
            lista.prepend(li);
            while (lista.children.length > 6) lista.lastChild.remove();
        }
        li.classList.toggle('rodando', m.estado === 'inicio');
        li.classList.toggle('erro', m.estado === 'erro');
    }

    // ------------------------------------------------------------ relógio
    const DIAS = ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado'];
    const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
    function relogio() {
        const d = new Date();
        $('hora').textContent = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        $('data').textContent = `${DIAS[d.getDay()]}, ${d.getDate()} ${MESES[d.getMonth()]} ${d.getFullYear()}`;
    }
    relogio();
    setInterval(relogio, 1000);

    // forma de onda: a voz do Jarvis quando fala, o seu microfone quando ouve
    function dadosOsc() {
        if (estado === 'falando' && ctx && analisador && fonteAtual) {
            analisador.getByteTimeDomainData(saidaBuf);
            return saidaBuf;
        }
        if (estado === 'ouvindo' && !mudo && micBuf) return micBuf;
        return null;
    }

    // ------------------------------------------------------------ reator
    Reator.iniciar($('reator'), {
        estado: () => estado,
        estilo: () => UI.estilo(),
        brilho: () => UI.brilho(),
        emocao: () => emocaoAtual,
        nivel: () => {
            if (estado === 'falando') {
                if (ctx && analisador && fonteAtual) {
                    analisador.getByteFrequencyData(dadosEspectro);
                    let soma = 0;
                    for (let i = 0; i < 40; i++) soma += dadosEspectro[i];
                    return Math.min(1, soma / 40 / 160);
                }
                nivelSintetico = 0.45 + 0.35 * Math.abs(Math.sin(performance.now() / 140)) * Math.abs(Math.sin(performance.now() / 370));
                return nivelSintetico;
            }
            return estado === 'ouvindo' && !mudo ? nivelMic : 0;
        },
        espectro: () => {
            if (ctx && analisador && fonteAtual && estado === 'falando') {
                analisador.getByteFrequencyData(dadosEspectro);
                return dadosEspectro;
            }
            return null;
        },
    });

    criarGraficos();
    Visual.radar($('radar'));
    Visual.fluxoHex($('hex'), () => (estado === 'pensando' ? 1 : estado === 'falando' ? 0.5 : 0.1));
    Visual.osciloscopio($('osc'), dadosOsc);
    Grafo.iniciar($('grafo'), $('grafo-dica'));
    Fluxos.iniciar($('fluxos'), { estado: () => estado });
    UI.iniciar();

    setTimeout(() => document.body.classList.remove('boot'), 2500);
    $('usuario').textContent = (localStorage.getItem('jarvis_nome') || 'LUCAS').toUpperCase();
    setEstado('offline');
    conectar();

    // ganchos de teste (só leitura/visual)
    window.__jarvis = { UI, Grafo, ativarPaineis, pintarManchetes, toastMemoria, pintarMemoria, mostrarConfirmacao, aplicarEmocao, tratar, Sfx, setEstado, aviso, receberFala, pintarPainel, pintarSistema, pintarFerramenta, addJarvis, mostrarVoce,
        iniciarReconhecimento, estenderConversa, interromper, tratarGesto, enviar, enviarFala, streams: () => streams.size, motorVoz: () => motorVoz, sttPronto: () => sttPronto,
        processarResultados, interno: () => ({ estado, tocando, legenda: legendaJarvis.slice(), interromperPorVoz, ultimaInterrupcaoEm, filaTamanho: fila.length, turnoAtivo }) };
})();
