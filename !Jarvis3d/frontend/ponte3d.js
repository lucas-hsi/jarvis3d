// Escolhe o visual do centro sem o main.js precisar saber: AURORA (aurora.js, partículas + cartões + barra; padrão desde 2026-10-19),
// reator 3D (cena3d.js) ou clássico (reator.js). ?ui=aurora | ?ui=3d | ?ui=classica (fica salvo em localStorage 'jarvis_visual').
// Sem WebGL2 o 3D cai sozinho para o clássico. (Antes a escolha ficava em 'jarvis_ui', a mesma chave do ui.js: o JSON dele
// fazia o 3D nunca carregar. Agora a chave é própria.)
(function () {
    'use strict';
    const params = new URLSearchParams(location.search);
    if (params.get('ui')) { try { localStorage.setItem('jarvis_visual', params.get('ui')); } catch (_) {} }
    let ui = params.get('ui');
    if (!ui) { try { ui = localStorage.getItem('jarvis_visual'); } catch (_) {} }
    if (!['aurora', '3d', 'classica'].includes(ui)) ui = 'aurora';
    window.VISUAL = ui === 'aurora' && window.Aurora ? 'aurora' : ui === 'classica' ? 'classica' : '3d';

    const Reator2D = window.Reator;
    const webgl2 = () => { try { return !!document.createElement('canvas').getContext('webgl2'); } catch (_) { return false; } };
    const quer3d = ui === '3d' && webgl2();
    let cena = null, tema = null;

    window.Reator = {
        iniciar(canvas, api) {
            if (window.VISUAL === 'aurora') {
                try { Aurora.iniciar(canvas, api); if (tema) Aurora.definirTema(tema[0], tema[1]); return; }
                catch (e) { console.warn('Aurora indisponível; voltando ao reator clássico:', e); document.body.classList.remove('aurora'); window.VISUAL = 'classica'; return Reator2D.iniciar(canvas, api); }
            }
            if (!quer3d) return Reator2D.iniciar(canvas, api);
            document.body.classList.add('ui3d');
            import('/static/cena3d.js').then((mod) => {
                const ref = document.querySelector('.reator-caixa') || canvas;
                cena = mod.iniciar(document.getElementById('cena3d'), api, { ref });
                window.Cena3D = cena;
                document.body.classList.add('ui3d-ok');
                if (tema) cena.definirTema(tema[0], tema[1]);
                if (window.UI && UI.iniciar) UI.iniciar();                 // reaplica o estilo (a cena 3D chega depois do UI.js)
            }).catch((e) => {
                console.warn('3D indisponível; voltando ao reator clássico:', e);
                document.body.classList.remove('ui3d', 'ui3d-ok');
                Reator2D.iniciar(canvas, api);
            });
        },
        definirTema(base, claro) {
            tema = [base, claro];
            if (Reator2D && Reator2D.definirTema) Reator2D.definirTema(base, claro);
            if (window.VISUAL === 'aurora' && window.Aurora) Aurora.definirTema(base, claro);
            if (cena) cena.definirTema(base, claro);
        },
    };
})();
