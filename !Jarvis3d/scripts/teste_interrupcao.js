// Testa a decisão "interrupção de verdade x eco da voz do Jarvis" (frontend/interrupcao.js), sem navegador.
// Uso:  node scripts/teste_interrupcao.js
const path = require('path');
const I = require(path.join(__dirname, '..', 'frontend', 'interrupcao.js'));

let ok = true;
const checar = (cond, texto) => { ok = ok && !!cond; console.log(`  [${cond ? 'OK' : 'FALHOU'}] ${texto}`); };

const FALADO = 'Hoje você tem duas reuniões na agenda. A primeira é às dez horas com o cliente da loja, e a segunda é depois do almoço. Quer que eu detalhe os horários?';

console.log('ECO: o Chrome transcrevendo a própria voz do Jarvis NUNCA interrompe');
for (const eco of [
    'hoje você tem duas reuniões na agenda',
    'a primeira é às dez horas com o cliente da loja',
    'e a segunda é depois do almoço quer que eu detalhe',
    'hoje voce tem duas reunioes na agenda a primeira e as dez',      // transcrição sem acento / quase igual
    'duas reuniões na agenda a primeira às dez com o cliente',
]) {
    const r = I.decidir({ texto: eco, final: false, confianca: 0, falado: FALADO });
    checar(r.acao === 'ignorar', `eco ignorado: "${eco}" (${r.motivo}, sobreposição ${(r.eco || 0).toFixed(2)})`);
}
checar(I.decidir({ texto: FALADO, final: true, confianca: 0.9, falado: FALADO }).acao === 'ignorar', 'a fala inteira do Jarvis, como final, é eco');

console.log('\nINTERROMPER: você falando por cima');
for (const [texto, motivoEsperado] of [
    ['para', 'pedido de parar'],
    ['Jarvis, para', 'pedido de parar'],
    ['chega', 'pedido de parar'],
    ['espera aí', 'pedido de parar'],
    ['calma jarvis', 'pedido de parar'],
    ['jarvis esquece isso e abre o youtube', 'chamou pelo nome'],
    ['não, eu quero saber da reunião de amanhã de manhã', 'falou algo novo'],
]) {
    const r = I.decidir({ texto, final: true, confianca: 0.9, falado: FALADO });
    checar(r.acao === 'interromper' && r.motivo === motivoEsperado, `"${texto}" → ${r.acao} (${r.motivo})`);
}

console.log('\nCUIDADOS: preposição "para" dentro de frase não é pedido de parar');
checar(!I.ehPedidoDeParar('para você ver'), '"para você ver" não é pedido de parar');
checar(!I.ehPedidoDeParar('a reunião para amanhã'), '"a reunião para amanhã" não é pedido de parar');
checar(I.ehPedidoDeParar('Para!'), '"Para!" sozinho é');
{
    const r = I.decidir({ texto: 'para você', final: true, confianca: 0.9, falado: 'Isso é para você, chefe.' });
    checar(r.acao === 'ignorar', `"para você" que o Jarvis acabou de dizer é eco (${r.motivo})`);
}

console.log('\nRUÍDO: pouca coisa ou baixa confiança não corta o Jarvis');
checar(I.decidir({ texto: 'hum', final: true, confianca: 0.9, falado: FALADO }).acao === 'ignorar', '"hum" ignorado');
checar(I.decidir({ texto: 'sei lá o que', final: false, confianca: 0, falado: FALADO }).acao === 'ignorar', 'parcial curto ignorado');
checar(I.decidir({ texto: 'aham sim claro entendi tudo bem', final: true, confianca: 0.2, falado: FALADO }).acao === 'ignorar', 'final com confiança baixa ignorado');
checar(I.decidir({ texto: '', final: true, confianca: 1, falado: FALADO }).acao === 'ignorar', 'vazio ignorado');

console.log('\nMÚSICA/VÍDEO TOCANDO (ou gravando): só quem chama "Jarvis" interrompe');
checar(I.decidir({ texto: 'quero saber da reunião de amanhã de manhã', final: true, confianca: 0.9, falado: FALADO, exigeNome: true }).acao === 'ignorar', 'sem o nome, ignorado');
checar(I.decidir({ texto: 'jarvis para', final: true, confianca: 0.9, falado: FALADO, exigeNome: true }).acao === 'interromper', 'com o nome, interrompe');

console.log('\nPARCIAL: exige mais palavras novas que o final (o parcial ainda pode mudar)');
checar(I.decidir({ texto: 'não eu quero', final: false, confianca: 0, falado: FALADO }).acao === 'ignorar', 'parcial com 3 palavras novas ainda espera');
checar(I.decidir({ texto: 'não eu quero saber outra coisa agora', final: false, confianca: 0, falado: FALADO }).acao === 'interromper', 'parcial com várias palavras novas interrompe');

console.log('\nCONFIRMAÇÃO POR VOZ: risco médio aceita "sim"; risco ALTO só "confirmo"; na dúvida nunca confirma');
for (const [texto, nivel, esperado] of [
    ['sim', 'medio', true], ['pode', 'medio', true], ['isso, pode fazer', 'medio', true], ['confirmo', 'medio', true], ['beleza', 'medio', true],
    ['não', 'medio', false], ['cancela', 'medio', false], ['espera', 'medio', false], ['nem pensar', 'medio', false],
    ['confirmo', 'alto', true], ['Confirmo.', 'alto', true], ['autorizo', 'alto', true], ['pode executar', 'alto', true], ['com firmo', 'alto', true],
    ['sim', 'alto', 'fraco'], ['pode', 'alto', 'fraco'], ['isso', 'alto', 'fraco'],
    ['não, cancela', 'alto', false], ['sim, não, espera', 'medio', 'ambiguo'], ['não pode', 'alto', 'ambiguo'],
    ['que horas são', 'medio', null], ['hum', 'alto', null], ['', 'medio', null],
]) {
    const r = I.confirmacao(texto, nivel);
    checar(r === esperado, `"${texto}" (${nivel}) → ${r}`);
}
const PEDIDO = 'Atenção, senhor: isso é arriscado. Executar no terminal. Para seguir, diga confirmo. Para parar, diga cancela.';
checar(I.ecoDaConfirmacao('diga confirmo', PEDIDO), 'eco "diga confirmo" é ignorado (não confirma sozinho)');
checar(I.ecoDaConfirmacao('para parar diga cancela', PEDIDO), 'eco "para parar diga cancela" é ignorado (não cancela sozinho)');
checar(I.ecoDaConfirmacao('isso é arriscado executar no terminal', PEDIDO), 'eco longo da própria fala é ignorado');
checar(!I.ecoDaConfirmacao('confirmo', PEDIDO), 'você dizendo "confirmo" NÃO é eco');
checar(!I.ecoDaConfirmacao('cancela', PEDIDO), 'você dizendo "cancela" NÃO é eco');

console.log('\nRESULTADO:', ok ? 'TUDO OK' : 'HÁ FALHAS');
process.exit(ok ? 0 : 1);
