// Escolhe entre o reator 3D (cena3d.js, Three.js) e o clássico (reator.js, canvas 2D), sem o main.js precisar saber.
// ?ui=classica força o antigo (fica salvo); ?ui=3d volta ao novo. Se o WebGL não existir ou falhar, cai sozinho para o clássico.
(function () {
    'use strict';
    const params = new URLSearchParams(location.search);
    if (params.get('ui')) { try { localStorage.setItem('jarvis_ui', params.get('ui')); } catch (_) {} }
    let ui = params.get('ui');
    if (!ui) { try { ui = localStorage.getItem('jarvis_ui'); } catch (_) {} }
    ui = ui || '3d';

    const Reator2D = window.Reator;
    const webgl2 = () => { try { return !!document.createElement('canvas').getContext('webgl2'); } catch (_) { return false; } };
    const quer3d = ui === '3d' && webgl2();
    let cena = null, tema = null;

    window.Reator = {
        iniciar(canvas, api) {
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
            if (cena) cena.definirTema(base, claro);
        },
    };
})();
