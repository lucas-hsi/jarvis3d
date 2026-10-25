/*
 * Decide se algo que o microfone ouviu ENQUANTO o Jarvis fala é você o interrompendo, ou só o eco da voz dele.
 *
 * O reconhecedor do Chrome transcreve tudo que o microfone capta, inclusive o alto-falante. Por isso comparamos o texto
 * reconhecido com o que o Jarvis está dizendo: se as palavras já estavam na fala dele, é eco e é ignorado.
 * Sem DOM e sem estado: testável em Node (scripts/teste_interrupcao.js) e usado por main.js.
 */
(function (raiz) {
    'use strict';

    const norm = (t) => String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
        .replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim();

    // Frases curtas de "pare de falar". Só valem se forem (quase) a fala inteira: "para" sozinho é cortar, "para você" não.
    const PARAR = /^(jarvis )?(para|pare|parar|chega|cala|cale|calma|espera|espere|aguarda|aguarde|silencio|ja entendi|ja chega|ok ok|nao precisa|deixa pra la|deixa quieto|para ai|espera ai|calma ai|pera ai)( jarvis| chefe| por favor)?$/;
    const CHAMOU = /\b(jarvis|jarbis|garvis|djarvis|jarvi|jarves)\b/;

    function palavras(t) { return norm(t).split(' ').filter((p) => p.length >= 3); }

    /** Fração das palavras de `texto` que o Jarvis já tinha dito (0 a 1). */
    function sobreposicao(texto, falado) {
        const ws = palavras(texto);
        if (!ws.length) return 1;                         // só palavrinhas curtas: trata como eco, não como comando
        const dito = new Set(palavras(falado));
        return ws.filter((p) => dito.has(p)).length / ws.length;
    }

    function ehPedidoDeParar(texto) { return PARAR.test(norm(texto)); }

    /**
     * ctx: { texto, final, confianca, falado, exigeNome, minNovasFinal, minNovasParcial }
     *  - falado: tudo que o Jarvis disse neste turno (as frases já tocadas e as que ainda vão tocar)
     *  - exigeNome: há música/vídeo tocando ou modo gravação: só interrompe quem chamar "Jarvis"
     * devolve { acao: 'interromper' | 'ignorar', motivo, parar }
     */
    function decidir(ctx) {
        const t = norm(ctx.texto);
        if (!t) return { acao: 'ignorar', motivo: 'vazio' };
        const eco = sobreposicao(ctx.texto, ctx.falado || '');
        const chamou = CHAMOU.test(t);
        if (eco >= 0.6) return { acao: 'ignorar', motivo: 'eco', eco };
        if (ctx.exigeNome && !chamou) return { acao: 'ignorar', motivo: 'sem o nome', eco };
        if (ctx.final && ctx.confianca > 0 && ctx.confianca < 0.4) return { acao: 'ignorar', motivo: 'confiança baixa', eco };
        if (ehPedidoDeParar(ctx.texto)) return { acao: 'interromper', motivo: 'pedido de parar', parar: true, eco };
        const dito = new Set(palavras(ctx.falado || ''));
        const novas = palavras(ctx.texto).filter((p) => !dito.has(p)).length;
        if (chamou && novas >= 1) return { acao: 'interromper', motivo: 'chamou pelo nome', eco, novas };
        const minimo = ctx.final ? (ctx.minNovasFinal || 3) : (ctx.minNovasParcial || 4);
        if (novas >= minimo) return { acao: 'interromper', motivo: 'falou algo novo', eco, novas };
        return { acao: 'ignorar', motivo: 'poucas palavras novas', eco, novas };
    }

    /**
     * Resposta falada a um pedido de confirmação. nivel 'medio' aceita sim/pode/isso; 'alto' (ação arriscada) só "confirmo"/"autorizo"/"pode executar".
     * Devolve true, false, 'fraco' (disse "sim" num pedido ALTO), 'ambiguo' (sim e não juntos) ou null (não entendi). Na dúvida, NUNCA confirma.
     */
    function confirmacao(texto, nivel) {
        const t = ' ' + norm(texto) + ' ';
        const nega = /\b(nao|cancela\w*|negativo|pare|parar|para tudo|deixa (pra la|quieto)|esquece|desiste|nem pensar|de jeito nenhum|espera|aguarda)\b/.test(t);
        const forte = /\b(confirm\w*|com firmo|conformo|autoriz\w*|pode (executar|seguir|rodar|apagar|instalar|fazer|continuar|mandar|ir))\b/.test(t);
        const fraco = forte || /\b(sim|pode|isso|vai|manda|faz|faca|ok|okay|beleza|claro|positivo|bora|certo|segue|prossiga|fechado|show)\b/.test(t);
        if (nega && fraco) return 'ambiguo';
        if (nega) return false;
        if (nivel === 'alto') return forte ? true : (fraco ? 'fraco' : null);
        return fraco ? true : null;
    }

    /** O que o microfone ouviu durante/logo depois do Jarvis LER o pedido de confirmação é eco dele? ("diga confirmo, ou cancela") */
    function ecoDaConfirmacao(texto, pedidoFalado) {
        if (/\bdiga\b/.test(norm(texto))) return true;
        return palavras(texto).length >= 3 && sobreposicao(texto, pedidoFalado) >= 0.6;
    }

    const api = { decidir, sobreposicao, ehPedidoDeParar, norm, confirmacao, ecoDaConfirmacao };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else raiz.Interrupcao = api;
})(typeof window !== 'undefined' ? window : globalThis);
