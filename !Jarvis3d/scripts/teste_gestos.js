// Testa as regras dos gestos com mãos e rostos SINTÉTICOS (sem câmera): node scripts\teste_gestos.js
const R = require('../frontend/gestos-regras.js');
let ok = true;
const checar = (cond, texto) => { ok = ok && !!cond; console.log(`  [${cond ? 'OK' : 'FALHOU'}] ${texto}`); };
const ASP = 1;

function mao({ cx = 0.5, cy = 0.5, s = 0.2, dedos = [true, true, true, true], polegar = true, pinca = false, pincaMedio = false }) {
    const p = Array.from({ length: 21 }, () => ({ x: cx, y: cy }));
    p[0] = { x: cx, y: cy + s };
    const xs = [-0.45, -0.15, 0.15, 0.45];             // base dos dedos 5, 9, 13, 17 (da esquerda para a direita)
    const base = [5, 9, 13, 17];
    base.forEach((b, i) => {
        const x = cx + xs[i] * s;
        p[b] = { x, y: cy };
        if (dedos[i]) { p[b + 1] = { x, y: cy - 0.35 * s }; p[b + 2] = { x, y: cy - 0.6 * s }; p[b + 3] = { x, y: cy - 0.85 * s }; }
        else { p[b + 1] = { x, y: cy - 0.2 * s }; p[b + 2] = { x, y: cy }; p[b + 3] = { x, y: cy + 0.2 * s }; }
    });
    p[1] = { x: cx - 0.3 * s, y: cy + 0.6 * s }; p[2] = { x: cx - 0.6 * s, y: cy + 0.35 * s };
    if (polegar) { p[3] = { x: cx - 0.8 * s, y: cy + 0.1 * s }; p[4] = { x: cx - 1.0 * s, y: cy - 0.1 * s }; }
    else { p[3] = { x: cx - 0.2 * s, y: cy + 0.3 * s }; p[4] = { x: cx - 0.1 * s, y: cy + 0.1 * s }; }
    if (pinca) p[4] = { x: p[8].x + 0.01 * s, y: p[8].y + 0.01 * s };
    if (pincaMedio) p[4] = { x: p[12].x + 0.01 * s, y: p[12].y + 0.01 * s };
    return p;
}

function rodar(mao_, quadros, fn, passo = 33) {          // fn(i) -> pontos; devolve todos os eventos
    const ev = []; let t = 1000;
    for (let i = 0; i < quadros; i++, t += passo) for (const e of mao_.atualizar(fn(i), t, ASP)) ev.push({ ...e, t, i });
    return ev;
}
const tipos = (ev) => ev.map((e) => e.tipo).filter((x) => x !== 'arrastar');

console.log('1) PINÇA');
{
    const m = R.criarMao();
    const ev = rodar(m, 30, (i) => (i < 6 ? mao({}) : i < 20 ? mao({ pinca: true, dedos: [true, true, true, true] }) : mao({})));
    const t = tipos(ev);
    checar(t.filter((x) => x === 'pinca').length === 1, 'pinça fechada e estável gera UM evento');
    checar(t.includes('pinca_fim'), 'soltar a pinça gera pinca_fim');
    checar(ev.some((e) => e.tipo === 'arrastar'), 'pinça fechada emite arrastar');
    const m2 = R.criarMao();
    const ev2 = rodar(m2, 12, (i) => (i === 5 ? mao({ pinca: true }) : mao({})));
    checar(!tipos(ev2).includes('pinca'), 'um quadro isolado de pinça (ruído) não dispara');
    const m3 = R.criarMao();
    checar(!tipos(rodar(m3, 40, () => mao({ dedos: [false, false, false, false], polegar: false }))).includes('pinca'), 'punho fechado não é pinça');
}

console.log('2) PALMA PARADA e PUNHO');
{
    const m = R.criarMao();
    const ev = rodar(m, 40, () => mao({}));
    checar(tipos(ev).filter((x) => x === 'palma').length === 1, 'palma aberta parada por ~1 s dispara uma vez');
    const m2 = R.criarMao();
    checar(!tipos(rodar(m2, 12, () => mao({}))).includes('palma'), 'palma por menos de 650 ms não dispara');
    const m3 = R.criarMao();
    checar(tipos(rodar(m3, 40, () => mao({ dedos: [false, false, false, false], polegar: false }))).includes('punho'), 'punho segurado dispara');
    const m4 = R.criarMao();
    checar(!tipos(rodar(m4, 40, (i) => mao({ cx: 0.4 + (i % 2) * 0.004 }))).includes('deslizar_direita'), 'tremor leve da mão parada não vira deslizar');
}

console.log('3) DESLIZAR');
{
    const por = (dx, dy, aberta = true) => {
        const m = R.criarMao();
        return tipos(rodar(m, 16, (i) => {
            const k = Math.max(0, i - 4);                       // 4 quadros parada, depois move 0,12 por quadro (~3,6 larguras/s)
            return mao({ cx: 0.5 + dx * k * 0.04, cy: 0.5 + dy * k * 0.04, dedos: aberta ? [true, true, true, true] : [false, false, false, false], polegar: aberta });
        }));
    };
    checar(por(1, 0).includes('deslizar_direita'), 'mão aberta para a direita (espelhada) → deslizar_direita');
    checar(por(-1, 0).includes('deslizar_esquerda'), 'para a esquerda → deslizar_esquerda');
    checar(por(0, -1).includes('deslizar_cima'), 'para cima → deslizar_cima');
    checar(por(0, 1).includes('deslizar_baixo'), 'para baixo → deslizar_baixo');
    checar(por(1, 0).filter((x) => x.startsWith('deslizar')).length === 1, 'um único evento por movimento (pausa de 800 ms)');
    checar(!por(1, 0, false).some((x) => x.startsWith('deslizar')), 'punho em movimento não desliza');
    const lento = (() => { const m = R.criarMao(); return tipos(rodar(m, 40, (i) => mao({ cx: 0.3 + i * 0.002 }))); })();
    checar(!lento.some((x) => x.startsWith('deslizar')), 'movimento lento da mão aberta não desliza');
}

console.log('4) CABEÇA');
{
    const rosto = (dx = 0, dy = 0) => {
        const p = Array.from({ length: 478 }, () => ({ x: 0.5, y: 0.5 }));
        p[10] = { x: 0.5, y: 0.2 }; p[152] = { x: 0.5, y: 0.8 }; p[234] = { x: 0.4, y: 0.5 }; p[454] = { x: 0.6, y: 0.5 };
        p[1] = { x: 0.5 + dx, y: 0.5 + dy };
        return p;
    };
    const roda = (fn, n = 60) => { const c = R.criarCabeca(); const out = []; let t = 0; for (let i = 0; i < n; i++, t += 33) out.push(...c.atualizar(fn(i), t)); return out.map((e) => e.tipo); };
    const onda = (i, per = 8) => Math.sin(i / per * Math.PI * 2);
    checar(roda((i) => rosto(0, 0.03 * onda(i))).includes('cabeca_sim'), 'balançar para cima e para baixo → cabeca_sim');
    checar(!roda((i) => rosto(0, 0.03 * onda(i))).includes('cabeca_nao'), '...e não confunde com "não"');
    checar(roda((i) => rosto(0.022 * onda(i), 0)).includes('cabeca_nao'), 'girar de um lado a outro → cabeca_nao');
    checar(!roda((i) => rosto(0.022 * onda(i), 0)).includes('cabeca_sim'), '...e não confunde com "sim"');
    checar(roda((i) => rosto(0.0015 * onda(i), 0.0015 * onda(i + 2)), 90).length === 0, 'tremor mínimo da cabeça não dispara nada');
    checar(roda((i) => rosto(0, i < 8 ? 0.03 * onda(i) : 0)).length === 0, 'um balanço só (menos de 3 movimentos) não dispara');
    checar(roda((i) => rosto(0, 0.03 * onda(i)), 200).filter((x) => x === 'cabeca_sim').length <= 4, 'não dispara sem parar enquanto continua balançando (pausa)');
}


console.log('5) MOUSE NO AR');
{
    const rodar2 = (fn, n, passo = 33) => { const m = R.criarMouse(); const ev = []; let t = 1000; for (let i = 0; i < n; i++, t += passo) for (const e of m.atualizar(fn(i), t, ASP)) ev.push({ ...e, i, t }); return ev; };
    const dedoUm = [true, false, false, false];
    const ponteiro = { dedos: dedoUm, polegar: false };
    // posição: centro da região útil -> centro da tela; bordas ficam presas em 0 e 1
    let ev = rodar2(() => [mao({ ...ponteiro, cx: 0.59, cy: 0.635 })], 3);          // a PONTA do indicador cai no centro da região útil
    const m0 = ev.find((e) => e.tipo === 'mover');
    checar(m0 && Math.abs(m0.x - 0.5) < 0.03 && Math.abs(m0.y - 0.5) < 0.03, `ponta do indicador no centro da região -> centro da tela (${m0 && m0.x.toFixed(2)}, ${m0 && m0.y.toFixed(2)})`);
    ev = rodar2(() => [mao({ ...ponteiro, cx: 0.97, cy: 0.97 })], 3);
    checar(ev.some((e) => e.tipo === 'mover' && e.x === 1 && e.y === 1), 'mão no canto da imagem prende o ponteiro no canto da tela (sem passar do limite)');
    // pinça = botão esquerdo; o ponteiro não pula ao fechar
    const fases = (i) => (i < 6 ? mao({ ...ponteiro }) : i < 24 ? mao({ ...ponteiro, pinca: true, dedos: [true, true, false, false] }) : mao({ ...ponteiro }));
    ev = rodar2((i) => [fases(i)], 36);
    const baixou = ev.find((e) => e.tipo === 'baixar'), soltou = ev.find((e) => e.tipo === 'soltar');
    checar(baixou && soltou && soltou.i > baixou.i, 'pinça fechada e estável baixa o botão; abrir solta');
    checar(ev.filter((e) => e.tipo === 'baixar').length === 1 && ev.filter((e) => e.tipo === 'soltar').length === 1, 'um único baixar e um único soltar');
    const moves = ev.filter((e) => e.tipo === 'mover');
    const salto = Math.max(0, ...moves.slice(1).map((e, k) => Math.hypot(e.x - moves[k].x, e.y - moves[k].y)));
    checar(salto < 0.08, `o ponteiro não pula ao fechar a pinça (maior salto ${salto.toFixed(3)} da tela)`);
    // arrastar: pinça mantida e a mão andando -> mover enquanto está baixo
    ev = rodar2((i) => [mao({ ...ponteiro, pinca: i >= 4, dedos: i >= 4 ? [true, true, false, false] : dedoUm, cx: 0.4 + Math.max(0, i - 8) * 0.01 })], 30);
    const b = ev.findIndex((e) => e.tipo === 'baixar'), mv = ev.slice(b + 1).filter((e) => e.tipo === 'mover');
    checar(b >= 0 && mv.length >= 5 && mv[mv.length - 1].x > mv[0].x + 0.1, 'arrastar: com a pinça mantida o ponteiro acompanha a mão');
    // botão direito: polegar + médio
    ev = rodar2((i) => [mao({ ...ponteiro, dedos: [true, true, false, false], polegar: false, pincaMedio: i > 3 })], 20);
    checar(ev.filter((e) => e.tipo === 'clique_direito').length === 1, 'polegar+médio = UM clique direito');
    // rolar: dois dedos (V) subindo
    ev = rodar2((i) => [mao({ dedos: [true, true, false, false], polegar: false, cy: 0.6 - i * 0.02 })], 20);
    const rol = ev.filter((e) => e.tipo === 'rolar');
    checar(rol.length >= 1 && rol.every((e) => e.passos < 0) && !ev.some((e) => e.tipo === 'baixar'), 'dois dedos subindo rolam (sem clicar nem arrastar)');
    // punho: estaciona (não move)
    ev = rodar2((i) => [mao({ dedos: [false, false, false, false], polegar: false, cx: 0.3 + i * 0.01 })], 12);
    checar(!ev.some((e) => e.tipo === 'mover' || e.tipo === 'baixar'), 'punho não move nem clica');
    // zoom: duas mãos em pinça se afastando e se aproximando
    const duas = (i, sep) => [mao({ cx: 0.5 - sep(i) / 2, pinca: true, dedos: [true, true, false, false] }), mao({ cx: 0.5 + sep(i) / 2, pinca: true, dedos: [true, true, false, false] })];
    ev = rodar2((i) => duas(i, (k) => 0.2 + k * 0.02), 20);
    const z1 = ev.filter((e) => e.tipo === 'zoom');
    checar(z1.length >= 1 && z1.every((e) => e.passos > 0) && !ev.some((e) => e.tipo === 'mover' || e.tipo === 'baixar'), 'duas mãos em pinça se afastando = zoom + (sem mexer o ponteiro)');
    ev = rodar2((i) => duas(i, (k) => 0.6 - k * 0.02), 20);
    checar(ev.filter((e) => e.tipo === 'zoom').every((e) => e.passos < 0) && ev.some((e) => e.tipo === 'zoom'), 'aproximando = zoom -');
    // mão some com o botão baixo: solta depois de ~1,2 s
    ev = rodar2((i) => (i < 12 ? [mao({ ...ponteiro, pinca: true, dedos: [true, true, false, false] })] : []), 60);
    const sol = ev.filter((e) => e.tipo === 'soltar');
    checar(sol.length === 1 && sol[0].t - 1000 >= 12 * 33 + 1100, 'a mão sumiu com o botão baixo: solta sozinho depois de ~1,2 s (nunca fica preso)');
}

console.log('\nRESULTADO:', ok ? 'TUDO OK' : 'HÁ FALHAS');
process.exit(ok ? 0 : 1);
