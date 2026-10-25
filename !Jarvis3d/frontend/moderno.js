// Menu de layout (botão no topo / tecla B) e botões do painel Atalhos. Só mexe na interface: muda o estado do UI.js e manda "abrir programa" ao servidor.
(function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    const NOMES = { clima: 'Clima', atalhos: 'Atalhos', sistema: 'Sistema', rede: 'Rede e GPU', processos: 'Processos', nucleo: 'Núcleo', memoria: 'Cérebro',
        agenda: 'Agenda e e-mail', atividade: 'Atividade', fluxo: 'Fluxo de dados', manchetes: 'Manchetes', osciloscopio: 'Barra de voz' };
    const ORDEM = ['clima', 'atalhos', 'sistema', 'agenda', 'atividade', 'memoria', 'rede', 'processos', 'nucleo', 'manchetes', 'osciloscopio', 'fluxo'];

    // ---------------------------------------------------------------- atalhos
    async function montarAtalhos() {
        const grade = $('atalhos-grade');
        if (!grade) return;
        let programas = [];
        try { programas = ((await (await fetch('/api/atalhos')).json()).programas || []).slice(0, 6); } catch (_) { /* sem lista: só os fixos */ }
        grade.innerHTML = '';
        const cap = (t) => t.charAt(0).toUpperCase() + t.slice(1);
        for (const nome of programas) {
            const b = document.createElement('button');
            b.type = 'button'; b.className = 'atalho'; b.textContent = cap(nome);
            b.addEventListener('click', () => { if (window.__jarvis) __jarvis.enviar({ tipo: 'abrir_programa', nome }); });
            grade.appendChild(b);
        }
        const falas = [['Resumo do dia', 'Bom dia, me atualiza'], ['Notícias', 'Quais as principais notícias de hoje?']];
        for (const [rotulo, texto] of falas) {
            const b = document.createElement('button');
            b.type = 'button'; b.className = 'atalho sec'; b.textContent = rotulo;
            b.addEventListener('click', () => { if (window.__jarvis) __jarvis.enviarFala(texto); });
            grade.appendChild(b);
        }
    }

    // ---------------------------------------------------------------- menu de layout
    const menu = document.createElement('div');
    menu.id = 'menu-layout'; menu.hidden = true;
    document.body.appendChild(menu);

    function desenhar() {
        const e = UI.estado();
        const nenhum = !Object.values(e.paineis).some(Boolean);
        const preset = nenhum ? (e.cinema ? 'cinema' : 'foco') : ORDEM.every((id) => e.paineis[id]) ? 'completo' : null;
        const btn = (rot, atual, acao) => `<button type="button" class="ml-botao${atual ? ' on' : ''}" data-a="${acao}">${rot}</button>`;
        menu.innerHTML = `
            <h4>Visual</h4>
            <div class="ml-linha">${btn('Aurora', window.VISUAL === 'aurora', 'visual:aurora')}${btn('Moderno', window.VISUAL !== 'aurora' && e.estilo !== 'matrix', 'visual:moderno')}${btn('Clássico (matrix)', window.VISUAL !== 'aurora' && e.estilo === 'matrix', 'visual:matrix')}</div>
            <h4>Modo</h4>
            <div class="ml-linha">${btn('Moderno', false, 'preset:moderno')}${btn('Completo', preset === 'completo', 'preset:completo')}${btn('Só o centro', preset === 'foco', 'preset:foco')}${btn('Cinema', preset === 'cinema', 'preset:cinema')}</div>
            <h4>Painéis</h4>
            ${ORDEM.map((id) => `<div class="ml-chave${e.paineis[id] ? ' on' : ''}" data-a="painel:${id}"><span>${NOMES[id]}</span><i></i></div>`).join('')}
            <h4>Posições</h4>
            <div class="ml-linha">${btn('Devolver painéis ao lugar', false, 'resetar')}</div>
            <div class="ml-dica">Arraste um painel pelo título. Tecla B esconde/mostra as laterais.</div>`;
    }

    menu.addEventListener('click', (ev) => {
        const alvo = ev.target.closest('[data-a]');
        if (!alvo) return;
        const [acao, valor] = alvo.dataset.a.split(':');
        if (acao === 'visual') {                                // Aurora x painéis (3D): troca e recarrega a tela (a conversa no servidor continua)
            try { localStorage.setItem('jarvis_visual', valor === 'aurora' ? 'aurora' : '3d'); } catch (_) {}
            if (valor !== 'aurora') UI.definirEstilo(valor === 'matrix' ? 'matrix' : 'moderno');
            location.reload(); return;
        }
        if (acao === 'estilo') UI.definirEstilo(valor);
        else if (acao === 'preset') UI.comando({ comando: 'ui_layout', acao: 'preset', nome: valor });
        else if (acao === 'painel') UI.comando({ comando: 'ui_painel', painel: valor, acao: 'alternar' });
        else if (acao === 'resetar') { try { localStorage.removeItem('jarvis_painel_pos'); } catch (_) {} location.reload(); return; }
        desenhar();
    });

    function alternarMenu(mostrar) {
        const abrir = mostrar === undefined ? menu.hidden : mostrar;
        if (abrir) desenhar();
        menu.hidden = !abrir;
    }
    $('btn-layout').addEventListener('click', (e) => { e.stopPropagation(); alternarMenu(); });
    document.addEventListener('click', (e) => { if (!menu.hidden && !menu.contains(e.target) && e.target !== $('btn-layout')) alternarMenu(false); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !menu.hidden) alternarMenu(false); });

    $('btn-restaurar').addEventListener('click', () => UI.alternarFoco());
    montarAtalhos();
})();
