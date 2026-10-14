// AudioWorklet: pega o áudio do microfone (44,1 ou 48 kHz) e entrega quadros de 20 ms em PCM 16 bits, 16 kHz, mono.
// Roda na thread de áudio; não toca no resto da página. O reconhecimento em si acontece no servidor (stt.py).
class JarvisPcm extends AudioWorkletProcessor {
    constructor() {
        super();
        this.razao = sampleRate / 16000;       // quantas amostras de entrada viram 1 de saída
        this.fase = 0;
        this.soma = 0;
        this.n = 0;
        this.saida = new Int16Array(320);      // 20 ms a 16 kHz
        this.k = 0;
    }

    process(entradas) {
        const x = entradas[0] && entradas[0][0];
        if (!x) return true;
        for (let i = 0; i < x.length; i++) {
            this.soma += x[i];
            this.n++;
            this.fase += 1;
            if (this.fase >= this.razao) {                       // média da janela = filtro simples contra serrilhado
                this.fase -= this.razao;
                const v = Math.max(-1, Math.min(1, this.soma / this.n));
                this.soma = 0;
                this.n = 0;
                this.saida[this.k++] = v < 0 ? v * 32768 : v * 32767;
                if (this.k === 320) {
                    const copia = new Int16Array(this.saida);
                    this.port.postMessage(copia.buffer, [copia.buffer]);
                    this.k = 0;
                }
            }
        }
        return true;
    }
}
registerProcessor('jarvis-pcm', JarvisPcm);
