// Efeitos sonoros do Jarvis, sintetizados na hora (WebAudio): sem arquivos, sem direitos autorais.
// Para trocar um efeito por um som seu, ponha frontend/sfx/<nome>.mp3 (ex.: adrenalina.mp3).
(function () {
    'use strict';

    let ctx = null, saida = null;
    const arquivos = {};            // nome -> AudioBuffer (se houver MP3 em frontend/sfx)
    const VOLUME = 0.42;

    function iniciar(contexto) {
        ctx = contexto;
        saida = ctx.createGain();
        saida.gain.value = VOLUME;
        const comp = ctx.createDynamicsCompressor();   // evita estourar quando vários sons juntam
        saida.connect(comp);
        comp.connect(ctx.destination);
        carregarArquivos();
    }

    async function carregarArquivos() {
        try {
            const nomes = await (await fetch('/api/sfx')).json();
            for (const n of nomes) {
                try {
                    const dados = await (await fetch(`/static/sfx/${n}.mp3`)).arrayBuffer();
                    arquivos[n] = await ctx.decodeAudioData(dados);
                } catch (_) { /* usa o sintetizado */ }
            }
        } catch (_) { /* sem lista: tudo sintetizado */ }
    }

    // ---------------------------------------------------------- blocos de síntese
    function osc(tipo, f0, t, dur, vol, f1, filtro) {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.type = tipo;
        o.frequency.setValueAtTime(f0, t);
        if (f1) o.frequency.exponentialRampToValueAtTime(f1, t + dur);
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(vol, t + Math.min(0.02, dur / 4));
        g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
        let no = o;
        if (filtro) {
            const f = ctx.createBiquadFilter();
            f.type = 'lowpass';
            f.frequency.setValueAtTime(filtro[0], t);
            f.frequency.exponentialRampToValueAtTime(filtro[1], t + dur);
            o.connect(f);
            no = f;
        }
        no.connect(g);
        g.connect(saida);
        o.start(t);
        o.stop(t + dur + 0.05);
    }

    let bufferRuido = null;
    function ruido(t, dur, vol, f0, f1, tipo = 'bandpass', q = 1.2) {
        if (!bufferRuido) {
            bufferRuido = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
            const d = bufferRuido.getChannelData(0);
            for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
        }
        const src = ctx.createBufferSource(), f = ctx.createBiquadFilter(), g = ctx.createGain();
        src.buffer = bufferRuido;
        f.type = tipo;
        f.Q.value = q;
        f.frequency.setValueAtTime(f0, t);
        f.frequency.exponentialRampToValueAtTime(f1, t + dur);
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(vol, t + dur * 0.85);
        g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
        src.connect(f); f.connect(g); g.connect(saida);
        src.start(t);
        src.stop(t + dur + 0.05);
    }

    // impacto grave (kick/boom): seno que despenca + estalo de ruído
    function boom(t, vol = 0.9) {
        osc('sine', 130, t, 0.55, vol, 38);
        ruido(t, 0.22, vol * 0.35, 2400, 200, 'lowpass', 0.7);
    }

    const nota = (n) => 440 * Math.pow(2, (n - 69) / 12);   // número MIDI -> Hz

    // ---------------------------------------------------------- os efeitos
    const EFEITOS = {
        // abertura: grave surgindo, varredura subindo e brilho no fim
        ativacao(t) {
            boom(t, 0.7);
            osc('sawtooth', 60, t, 1.3, 0.22, 700, [200, 5000]);
            ruido(t + 0.1, 1.1, 0.12, 400, 7000, 'bandpass', 2);
            [76, 83, 88].forEach((n, i) => osc('triangle', nota(n), t + 1.05 + i * 0.07, 0.8, 0.16));
        },
        memoria(t) {      // dado gravado: dois pings curtos e um brilho
            osc('sine', nota(91), t, 0.12, 0.13);
            osc('sine', nota(96), t + 0.09, 0.3, 0.13);
            ruido(t + 0.1, 0.25, 0.03, 7000, 11000, 'highpass');
        },
        camera(t) {       // obturador: estalo seco + ruído curto
            ruido(t, 0.05, 0.5, 4200, 1800, 'bandpass', 1.5);
            osc('square', 1800, t, 0.03, 0.12);
            ruido(t + 0.09, 0.07, 0.3, 2500, 900, 'bandpass', 1.2);
        },
        ui(t) {           // troca de visual: dois blips suaves
            osc('sine', nota(84), t, 0.07, 0.1);
            osc('sine', nota(91), t + 0.06, 0.12, 0.1);
        },
        recebi(t) {       // ouvi você: um toque curtinho, na hora
            osc('sine', 1760, t, 0.045, 0.07);
        },
        scan(t) {
            osc('sine', 1500, t, 0.05, 0.12);
            osc('sine', 2100, t + 0.07, 0.05, 0.1);
        },
        ok(t) {
            osc('sine', nota(81), t, 0.14, 0.2);
            osc('sine', nota(88), t + 0.08, 0.28, 0.2);
        },
        erro(t) {
            osc('sawtooth', 170, t, 0.16, 0.22, 120, [900, 300]);
            osc('sawtooth', 150, t + 0.2, 0.22, 0.22, 90, [900, 300]);
        },
        alerta(t) {
            [74, 78, 83].forEach((n, i) => osc('square', nota(n), t + i * 0.11, 0.1, 0.13, null, [3000, 1500]));
            osc('square', nota(83), t + 0.5, 0.18, 0.1, null, [3000, 1500]);
        },
        confirmado(t) {
            EFEITOS.ok(t);
            [88, 92, 95].forEach((n, i) => osc('triangle', nota(n), t + 0.25 + i * 0.06, 0.5, 0.12));
        },
        negado(t) {
            osc('triangle', nota(76), t, 0.16, 0.2);
            osc('triangle', nota(69), t + 0.14, 0.3, 0.2);
        },
        controle_on(t) {
            for (let i = 0; i < 4; i++) osc('square', 600 + i * 220, t + i * 0.06, 0.05, 0.09);
            osc('sawtooth', 90, t, 0.4, 0.16, 360, [300, 3000]);
        },
        controle_off(t) {
            for (let i = 0; i < 3; i++) osc('square', 1100 - i * 260, t + i * 0.06, 0.05, 0.09);
            osc('sawtooth', 360, t, 0.35, 0.14, 80, [3000, 300]);
        },
        // ---- emoções
        feliz(t) {
            [72, 76, 79, 84, 88, 91, 96].forEach((n, i) => osc('triangle', nota(n), t + i * 0.055, 0.35, 0.16));
            ruido(t + 0.35, 0.4, 0.05, 6000, 11000, 'highpass');
        },
        adrenalina(t) {   // subida tensa + impacto
            ruido(t, 0.95, 0.22, 300, 7000, 'bandpass', 3);
            osc('sawtooth', 70, t, 0.95, 0.2, 520, [250, 6000]);
            osc('square', 140, t + 0.35, 0.6, 0.07, 1040, [800, 6000]);
            boom(t + 0.95, 1);
            ruido(t + 0.95, 0.7, 0.2, 5000, 700, 'bandpass', 0.8);
        },
        triunfo(t) {      // fanfarra curta de metais
            const acorde = (inicio, notas, dur) => notas.forEach((n) => osc('sawtooth', nota(n), inicio, dur, 0.11, null, [900, 3600]));
            acorde(t, [60, 64, 67], 0.28);
            acorde(t + 0.22, [65, 69, 72], 0.28);
            acorde(t + 0.46, [67, 71, 74, 79], 0.95);
            boom(t + 0.46, 0.5);
            ruido(t + 0.46, 1.1, 0.07, 5000, 9000, 'highpass');
        },
        tensao(t) {       // drone dissonante que cresce
            osc('sine', 110, t, 1.4, 0.2);
            osc('sine', 116.5, t, 1.4, 0.2);
            osc('sine', 55, t, 1.4, 0.2);
            ruido(t, 1.2, 0.07, 150, 900, 'bandpass', 4);
        },
        sarcasmo(t) {     // "wah wah" descendente de trombone triste
            [[62, 0], [61, 0.24], [60, 0.48], [57, 0.72]].forEach(([n, d], i) =>
                osc('sawtooth', nota(n), t + d, i === 3 ? 0.7 : 0.2, 0.13, nota(n) * (i === 3 ? 0.88 : 1), [700, 1800]));
        },
    };

    const POR_EMOCAO = {
        animado: 'feliz', adrenalina: 'adrenalina', triunfante: 'triunfo', preocupado: 'tensao', sarcastico: 'sarcasmo',
        risada: 'feliz', irritado: 'tensao',
    };

    let silenciado = false;      // gravando vídeo: nenhum efeito sonoro (para não entrar na gravação)
    function tocar(nome) {
        if (!ctx || silenciado) return;
        if (ctx.state === 'suspended') ctx.resume().catch(() => {});
        if (arquivos[nome]) {
            const s = ctx.createBufferSource();
            s.buffer = arquivos[nome];
            s.connect(saida);
            s.start();
            return;
        }
        const fx = EFEITOS[nome];
        if (fx) fx(ctx.currentTime + 0.01);
    }

    window.Sfx = { iniciar, tocar, silenciar: (v) => { silenciado = !!v; }, deEmocao: (e) => POR_EMOCAO[e] || null, nomes: Object.keys(EFEITOS) };
})();
