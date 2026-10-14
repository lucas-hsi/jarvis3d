/*
 * Captura do microfone para o reconhecimento de voz PRÓPRIO do Jarvis (servidor, stt.py).
 *
 * O microfone é aberto com echoCancellation/noiseSuppression do Chromium (o cancelamento de eco usa a própria saída de áudio
 * do app como referência, por isso a voz do Jarvis quase não volta pelo microfone) e vira quadros PCM de 20 ms (stt-worklet.js)
 * enviados por WebSocket binário. Quem decide o que fazer com o texto continua sendo o main.js.
 */
const SttLocal = (() => {
    'use strict';
    let ctx = null, fluxo = null, no = null, fonte = null;
    let enviarBin = null, enviando = false, iniciando = null, quadros = 0;

    async function iniciar(enviarBinario) {
        enviarBin = enviarBinario;
        if (no) return true;
        if (iniciando) return iniciando;
        iniciando = (async () => {
            fluxo = await navigator.mediaDevices.getUserMedia({
                audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
            });
            ctx = new (window.AudioContext || window.webkitAudioContext)({ latencyHint: 'interactive' });
            await ctx.audioWorklet.addModule('/static/stt-worklet.js');
            fonte = ctx.createMediaStreamSource(fluxo);
            no = new AudioWorkletNode(ctx, 'jarvis-pcm', { numberOfInputs: 1, numberOfOutputs: 0 });   // sem saída: nada vai para os alto-falantes
            no.port.onmessage = (e) => { if (enviando && enviarBin) { quadros++; enviarBin(e.data); } };
            fonte.connect(no);
            if (ctx.state === 'suspended') await ctx.resume().catch(() => {});
            return true;
        })().catch((e) => { iniciando = null; throw e; });
        return iniciando;
    }

    function ligar(v) { enviando = !!v; }
    function ativo() { return !!no; }
    function enviandoAgora() { return enviando; }
    function quadrosEnviados() { return quadros; }
    function parar() {
        enviando = false;
        try { fluxo && fluxo.getTracks().forEach((t) => t.stop()); } catch (_) {}
        try { ctx && ctx.close(); } catch (_) {}
        ctx = fluxo = no = fonte = null;
        iniciando = null;
    }

    return { iniciar, ligar, ativo, enviandoAgora, quadrosEnviados, parar };
})();
window.SttLocal = SttLocal;
