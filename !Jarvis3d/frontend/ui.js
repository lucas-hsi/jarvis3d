// Estado da interface: tema, painéis visíveis, layouts (preset e salvos), estilo do reator e efeitos.
// O Jarvis muda isso por voz (mensagens "ui" do servidor) e a escolha fica guardada no navegador.
(function () {
    'use strict';

    const TEMAS = {
        ciano:    { rgb: [0, 229, 255],   claro: [125, 249, 255] },
        vermelho: { rgb: [255, 70, 70],   claro: [255, 170, 160] },
        ambar:    { rgb: [255, 183, 3],   claro: [255, 226, 140] },
        verde:    { rgb: [40, 230, 120],  claro: [170, 255, 200] },
        roxo:     { rgb: [170, 110, 255], claro: [215, 185, 255] },
        gelo:     { rgb: [190, 225, 255], claro: [235, 245, 255] },
        rosa:     { rgb: [255, 90, 170],  claro: [255, 190, 225] },
    };
    const PAINEIS = ['clima', 'atalhos', 'sistema', 'rede', 'processos', 'nucleo', 'fluxo', 'memoria', 'agenda', 'atividade', 'manchetes', 'osciloscopio'];
    const ESQUERDA = ['clima', 'atalhos', 'sistema', 'rede', 'processos'];
    const DIREITA = ['memoria', 'agenda', 'atividade', 'nucleo', 'fluxo'];
    const tudo = (v) => Object.fromEntries(PAINEIS.map((p) => [p, v]));
    const PRESETS = {
        completo: { paineis: tudo(true), cinema: false },
        moderno: { paineis: { ...tudo(false), clima: true, atalhos: true, sistema: true, agenda: true, atividade: true, memoria: true }, cinema: false },
        foco: { paineis: tudo(false), cinema: false },
        minimo: { paineis: { ...tudo(false), sistema: true, memoria: true }, cinema: false },
        cinema: { paineis: tudo(false), cinema: true },
    };

    const VERSAO_UI = 2;                                  // 2 = visual moderno (padrão): quem tinha o layout antigo salvo recebe o novo uma vez
    let estado = { versao: VERSAO_UI, estilo: 'moderno', tema: 'ciano', paineis: { ...PRESETS.moderno.paineis }, cinema: false, reator: { estilo: 'classico', brilho: 1 } };
    try {
        const guardado = JSON.parse(localStorage.getItem('jarvis_ui') || 'null');
        if (guardado && guardado.versao === VERSAO_UI) estado = { ...estado, ...guardado, paineis: { ...estado.paineis, ...(guardado.paineis || {}) } };
        else if (guardado) estado = { ...estado, tema: guardado.tema || estado.tema, reator: guardado.reator || estado.reator };
    } catch (_) { /* usa o padrão */ }

    const salvar = () => { try { localStorage.setItem('jarvis_ui', JSON.stringify(estado)); } catch (_) {} };
    const layouts = () => { try { return JSON.parse(localStorage.getItem('jarvis_ui_layouts') || '{}'); } catch (_) { return {}; } };

    function aplicar() {
        const b = document.body;
        const tema = TEMAS[estado.tema] ? estado.tema : 'ciano';
        b.dataset.tema = tema;
        if (window.Reator && Reator.definirTema) Reator.definirTema(TEMAS[tema].rgb, TEMAS[tema].claro);
        for (const id of PAINEIS) {
            document.querySelectorAll(`[data-painel="${id}"]`).forEach((el) => el.classList.toggle('oculto-ui', !estado.paineis[id]));
        }
        b.classList.toggle('cinema', !!estado.cinema);
        b.classList.toggle('moderno', estado.estilo !== 'matrix');
        b.classList.toggle('laterais-off', !Object.values(estado.paineis).some(Boolean) || !!estado.cinema);       // sem painéis: aparece um botão fixo para trazê-los de volta
        if (window.Cena3D && Cena3D.ambiente) Cena3D.ambiente(estado.estilo !== 'matrix' ? 0.3 : 1);
        b.classList.toggle('sem-esq', !ESQUERDA.some((p) => estado.paineis[p]));
        b.classList.toggle('sem-dir', !DIREITA.some((p) => estado.paineis[p]));
    }

    function efeito(nome) {
        if (nome === 'chuva_de_dados') {
            document.querySelectorAll('.painel[data-painel]').forEach((p) => window.Fluxos && Fluxos.ativar(p.dataset.painel, 4));
            return;
        }
        const classe = 'fx-' + nome;
        document.body.classList.remove(classe);
        void document.body.offsetWidth;            // reinicia a animação se repetir
        document.body.classList.add(classe);
        setTimeout(() => document.body.classList.remove(classe), 1400);
    }

    function comando(m) {
        switch (m.comando) {
            case 'ui_tema':
                if (TEMAS[m.tema]) estado.tema = m.tema;
                break;
            case 'ui_painel': {
                const alvos = m.painel === 'todos' ? PAINEIS : [m.painel];
                for (const id of alvos) {
                    if (!PAINEIS.includes(id)) continue;
                    estado.paineis[id] = m.acao === 'alternar' ? !estado.paineis[id] : m.acao === 'mostrar';
                }
                if (Object.values(estado.paineis).some(Boolean)) estado.cinema = false;
                break;
            }
            case 'ui_layout':
                if (m.acao === 'preset' && PRESETS[m.nome]) {
                    estado.paineis = { ...PRESETS[m.nome].paineis };
                    estado.cinema = PRESETS[m.nome].cinema;
                } else if (m.acao === 'salvar') {
                    const l = layouts();
                    l[m.nome] = { paineis: { ...estado.paineis }, cinema: estado.cinema, tema: estado.tema, reator: { ...estado.reator } };
                    localStorage.setItem('jarvis_ui_layouts', JSON.stringify(l));
                } else if (m.acao === 'carregar') {
                    const l = layouts()[m.nome] || PRESETS[m.nome];
                    if (l) {
                        estado.paineis = { ...tudo(false), ...l.paineis };
                        estado.cinema = !!l.cinema;
                        if (l.tema) estado.tema = l.tema;
                        if (l.reator) estado.reator = { ...l.reator };
                    }
                }
                break;
            case 'ui_reator':
                if (m.estilo) estado.reator.estilo = m.estilo;
                if (m.brilho != null) estado.reator.brilho = m.brilho;
                break;
            case 'ui_efeito':
                efeito(m.nome);
                if (window.Sfx) Sfx.tocar('ui');
                return;
        }
        salvar();
        aplicar();
        if (window.Sfx) Sfx.tocar('ui');
    }

    function definirEstilo(e) { estado.estilo = e === 'matrix' ? 'matrix' : 'moderno'; salvar(); aplicar(); }
    function alternarFoco() {                              // tecla B: só o centro <-> o que estava antes
        const todosOff = !Object.values(estado.paineis).some(Boolean) || !!estado.cinema;
        if (todosOff) { estado.paineis = { ...(estado.antesDoFoco || PRESETS.moderno.paineis) }; estado.cinema = false; }
        else { estado.antesDoFoco = { ...estado.paineis }; estado.paineis = tudo(false); }
        salvar(); aplicar(); if (window.Sfx) Sfx.tocar('ui');
    }
    window.UI = {
        iniciar: aplicar,
        comando, definirEstilo, alternarFoco, estado: () => JSON.parse(JSON.stringify(estado)), painelIds: PAINEIS,
        estilo: () => estado.reator.estilo,
        brilho: () => estado.reator.brilho,
        temas: TEMAS,
    };
})();
