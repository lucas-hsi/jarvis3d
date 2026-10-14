/*
 * Jarvis como software do Windows (casca Electron).
 *
 * O que ela faz: liga o servidor Python do Jarvis (ou se pendura num que já está rodando), abre a interface numa janela
 * própria (sem Chrome, sem barra de endereço), fica na bandeja do sistema, tem atalho global e pode iniciar com o Windows.
 * Toda a mecânica (voz, ferramentas, memória, controle do Windows) continua no servidor Python, sem mudança.
 *
 * Modos: desenvolvimento (npm start, usa C:\Jarvis e os dados de lá) e empacotado (servidor em resources\server,
 * dados em %APPDATA%\Jarvis via JARVIS_HOME). Teste automático: `electron . --teste`.
 */
const { app, BrowserWindow, Tray, Menu, globalShortcut, session, shell, nativeImage, ipcMain , Notification } = require('electron');
const path = require('path');
const fs = require('fs');
const http = require('http');
const { spawn, spawnSync } = require('child_process');

const EMPACOTADO = app.isPackaged;
const MODO_TESTE_VOZ = process.argv.includes('--teste-voz');
const ARG_CAPTURA = (() => { const i = process.argv.indexOf('--captura'); return i >= 0 ? process.argv[i + 1] : null; })();
const ARG_CLIQUES = process.argv.includes('--teste-cliques');
const ARG_GESTOS = process.argv.includes('--teste-gestos');
if (ARG_GESTOS) { app.commandLine.appendSwitch('use-fake-device-for-media-stream'); app.commandLine.appendSwitch('use-fake-ui-for-media-stream'); }
const ARG_STREAM = (() => { const i = process.argv.indexOf('--teste-stream'); return i >= 0 ? process.argv[i + 1] : null; })();
const MODO_TESTE = process.argv.includes('--teste') || MODO_TESTE_VOZ || !!ARG_CAPTURA || !!ARG_STREAM || ARG_GESTOS || ARG_CLIQUES;
const COMECAR_OCULTO = process.argv.includes('--oculto');
const PORTA = Number(process.env.JARVIS_PORTA || 8340);
const URL_BASE = `http://127.0.0.1:${PORTA}`;
const REPO = process.env.JARVIS_REPO || path.resolve(__dirname, '..');           // desenvolvimento: C:\Jarvis
const ATALHO = 'Control+Alt+J';

app.setName('Jarvis');
// Só nos testes: o 'microfone' é um arquivo de áudio (JARVIS_TESTE_AUDIO), tocado uma vez, sem pedir permissão.
if (process.env.JARVIS_TESTE_AUDIO) {
    app.commandLine.appendSwitch('use-fake-device-for-media-stream');
    app.commandLine.appendSwitch('use-fake-ui-for-media-stream');
    app.commandLine.appendSwitch('use-file-for-fake-audio-capture', process.env.JARVIS_TESTE_AUDIO + '%noloop');
}
// A interface (WebGL) não precisa da NVIDIA: usa a placa integrada (poupa bateria e deixa a GTX 1650 para o Whisper).
// JARVIS_GPU=alto força a placa dedicada se a animação engasgar.
if ((process.env.JARVIS_GPU || 'baixo') !== 'alto') app.commandLine.appendSwitch('force_low_power_gpu');
if (!app.requestSingleInstanceLock()) { app.quit(); process.exit(0); }          // só uma casca por usuário

let montarMenuBandeja = () => Menu.buildFromTemplate([]);
let janela = null, bandeja = null, servidor = null, saindo = false, servidorProprio = false;
let flutuante = null, ultimoEstado = 'espera', arrasto = null;

// ------------------------------------------------------------------ pastas e log
function pastaDados() { return EMPACOTADO ? app.getPath('userData') : REPO; }
function log(...a) {
    const linha = `[${new Date().toISOString()}] ${a.join(' ')}\n`;
    try {
        const pasta = path.join(EMPACOTADO ? app.getPath('userData') : REPO, 'logs');
        fs.mkdirSync(pasta, { recursive: true });
        fs.appendFileSync(path.join(pasta, 'casca.log'), linha);
    } catch (_) { /* log nunca derruba o app */ }
    if (MODO_TESTE || !EMPACOTADO) process.stdout.write(linha);
}

// ------------------------------------------------------------------ servidor Python
function saude(tempoMs = 1200) {
    return new Promise((resolve) => {
        const req = http.get(`${URL_BASE}/api/saude`, { timeout: tempoMs }, (res) => {
            let corpo = '';
            res.on('data', (c) => { corpo += c; });
            res.on('end', () => { try { resolve(JSON.parse(corpo)); } catch (_) { resolve(null); } });
        });
        req.on('error', () => resolve(null));
        req.on('timeout', () => { req.destroy(); resolve(null); });
    });
}

function comandoDoServidor() {
    if (EMPACOTADO) {
        const exe = path.join(process.resourcesPath, 'server', 'jarvis-server.exe');
        return { exe, args: [], cwd: path.dirname(exe), env: { JARVIS_HOME: app.getPath('userData'), JARVIS_STT: 'local' } };
    }
    const py = path.join(REPO, '.venv', 'Scripts', 'python.exe');
    return { exe: fs.existsSync(py) ? py : 'python', args: [path.join(REPO, 'server.py')], cwd: REPO, env: { JARVIS_STT: 'local' } };
}

async function garantirServidor() {
    if (await saude()) { log('servidor já estava no ar: me penduro nele'); return true; }
    const c = comandoDoServidor();
    if (!fs.existsSync(c.exe) && c.exe !== 'python') { log('servidor não encontrado:', c.exe); return false; }
    const pastaLog = path.join(pastaDados(), 'logs');
    fs.mkdirSync(pastaLog, { recursive: true });
    const saida = fs.openSync(path.join(pastaLog, 'servidor.log'), 'a');
    servidor = spawn(c.exe, c.args, {
        cwd: c.cwd, windowsHide: true, stdio: ['ignore', saida, saida],
        env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8', JARVIS_PORTA: String(PORTA), ...c.env },
    });
    servidorProprio = true;
    servidor.on('exit', (codigo) => {
        log('servidor encerrou, código', codigo); servidor = null;
        if (saindo) return;
        if (codigo === 75) { servidorProprio = false; garantirServidor().then((ok) => { if (ok && janela) janela.loadURL(`${URL_BASE}/?auto=1&shell=electron`); }); return; }      // reinício pedido pela página de configuração
        falhaDoServidor(codigo);
    });
    for (let i = 0; i < 160; i++) {                                              // até ~40 s (a 1ª vez carrega modelos)
        if (await saude()) { log('servidor pronto'); return true; }
        if (!servidor) return false;
        await new Promise((r) => setTimeout(r, 250));
    }
    return false;
}

function falhaDoServidor(codigo) {
    if (janela && !janela.isDestroyed()) {
        janela.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(
            `<body style="background:#05080c;color:#7fe9ff;font:16px Segoe UI;padding:40px"><h2>O servidor do Jarvis parou (código ${codigo}).</h2>` +
            `<p>Veja o arquivo <b>logs\\servidor.log</b> na pasta de dados. Feche e abra o Jarvis para tentar de novo.</p></body>`));
    }
}

function pararServidor() {
    if (servidor && servidorProprio) {
        try { spawnSync('taskkill', ['/pid', String(servidor.pid), '/T', '/F'], { windowsHide: true }); } catch (_) { /* já saiu */ }
        servidor = null;
    }
}

// ------------------------------------------------------------------ janela, bandeja, atalho
function icone() {
    const candidatos = [path.join(process.resourcesPath || '', 'icone.ico'), path.join(REPO, 'icone.ico'), path.join(__dirname, 'icone.ico')];
    const achado = candidatos.find((p) => p && fs.existsSync(p));
    return achado ? nativeImage.createFromPath(achado) : undefined;
}

async function criarJanela() {
    janela = new BrowserWindow({
        width: 1280, height: 800, minWidth: 900, minHeight: 600, show: false, backgroundColor: '#05080c',
        title: 'J.A.R.V.I.S.', icon: icone(), autoHideMenuBar: true,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true,
            backgroundThrottling: false,                                        // áudio e microfone seguem vivos com a janela escondida
        },
    });
    janela.setMenuBarVisibility(false);
    const sInicial = EMPACOTADO && !MODO_TESTE ? await saude() : null;
    if (sInicial && sInicial.configurado === false) janela.loadURL(`${URL_BASE}/configurar`);          // instalação nova: 1º passo é o assistente
    else janela.loadURL(`${URL_BASE}/?${MODO_TESTE ? 'mudo=1&' : 'auto=1&'}shell=electron`);       // no teste NÃO ativa: sem saudação, sem gasto
    janela.once('ready-to-show', () => { if ((!COMECAR_OCULTO && !MODO_TESTE) || ARG_CAPTURA) janela.show(); });
    janela.on('close', (e) => { if (!saindo) { e.preventDefault(); janela.hide(); } });      // fechar = ir para a bandeja
    janela.on('show', () => atualizarFlutuante());
    janela.on('hide', () => atualizarFlutuante());
    janela.on('minimize', () => atualizarFlutuante());
    janela.on('restore', () => atualizarFlutuante());
    // só a própria interface do Jarvis dentro da janela; links externos abrem no navegador padrão
    janela.webContents.on('will-navigate', (e, url) => { if (!url.startsWith(URL_BASE) && !url.startsWith('data:')) { e.preventDefault(); abrirExterno(url); } });
    janela.webContents.setWindowOpenHandler(({ url }) => { abrirExterno(url); return { action: 'deny' }; });
}

function abrirExterno(url) { if (/^https?:\/\//i.test(url)) shell.openExternal(url); }

function mostrarOuEsconder() {
    if (!janela) return;
    if (janela.isVisible() && janela.isFocused()) janela.hide(); else { janela.show(); janela.focus(); }
}

function iniciaComWindows() { return app.getLoginItemSettings().openAtLogin; }

// ------------------------------------------------------------------ atualização automática (só instalado, e só com repositório em atualizacao.json)
// Fluxo: checa ao abrir (30 s depois) e a cada 6 h; baixa em segundo plano; instala quando você fecha o Jarvis ou pelo menu da bandeja.
// Seus dados (config, memória, chaves, modelos) ficam em %APPDATA%\Jarvis e NUNCA são tocados pela atualização.
let atualizador = null, atualizacao = { estado: 'ocioso', versao: '' };
function avisarSistema(titulo, corpo) { try { if (Notification.isSupported()) new Notification({ title: titulo, body: corpo }).show(); } catch (_) { /* aviso é enfeite */ } }
function configurarAtualizacao() {
    if (!EMPACOTADO || MODO_TESTE) return;
    let cfg = {};
    try { cfg = JSON.parse(fs.readFileSync(path.join(process.resourcesPath, 'atualizacao.json'), 'utf8')); } catch (_) { /* sem arquivo = desligado */ }
    // %APPDATA%\Jarvis\atualizacao.json (do usuário, fora do repositório) pode trazer um "token" do GitHub (só leitura) se o repositório for PRIVADO
    try { cfg = { ...cfg, ...JSON.parse(fs.readFileSync(path.join(app.getPath('userData'), 'atualizacao.json'), 'utf8')) }; } catch (_) { /* opcional */ }
    if (!cfg.owner || !cfg.repo) { log('atualização automática desligada (preencha owner e repo em atualizacao.json)'); return; }
    try {
        const { autoUpdater } = require('electron-updater');
        atualizador = autoUpdater;
        autoUpdater.setFeedURL(cfg.token ? { provider: 'github', owner: cfg.owner, repo: cfg.repo, private: true, token: cfg.token } : { provider: 'github', owner: cfg.owner, repo: cfg.repo });
        autoUpdater.autoDownload = true;
        autoUpdater.autoInstallOnAppQuit = true;
        autoUpdater.logger = { info: (m) => log('atualizador:', m), warn: (m) => log('atualizador (aviso):', m), error: (m) => log('atualizador (erro):', m), debug: () => {} };
        autoUpdater.on('update-available', (i) => { atualizacao = { estado: 'baixando', versao: i.version }; log('atualização encontrada', i.version); });
        autoUpdater.on('update-not-available', () => { atualizacao = { estado: 'ocioso', versao: '' }; });
        autoUpdater.on('update-downloaded', (i) => {
            atualizacao = { estado: 'pronta', versao: i.version };
            avisarSistema('Jarvis ' + i.version + ' pronto', 'A atualização já foi baixada. Ela é instalada quando você fechar o Jarvis, ou use "Reiniciar para atualizar" na bandeja.');
            if (bandeja) bandeja.setContextMenu(montarMenuBandeja());
        });
        autoUpdater.on('error', (e) => { log('atualização: erro', e && e.message); });
        setTimeout(verificarAtualizacao, 30000);
        setInterval(verificarAtualizacao, 6 * 3600 * 1000);
    } catch (e) { log('atualização indisponível:', e.message); }
}
function verificarAtualizacao() { if (atualizador) atualizador.checkForUpdates().catch((e) => log('atualização: falha ao checar', e && e.message)); }

function montarBandeja() {
    bandeja = new Tray(icone() || nativeImage.createEmpty());
    bandeja.setToolTip('J.A.R.V.I.S.');
    const menu = montarMenuBandeja = () => Menu.buildFromTemplate([
        { label: 'Abrir o Jarvis', click: () => { janela.show(); janela.focus(); } },
        { label: 'Diagnóstico (microfone, câmera, placas)', click: () => { janela.show(); janela.loadURL(`${URL_BASE}/diagnostico`); } },
        { label: 'Voltar para a tela principal', click: () => { janela.show(); janela.loadURL(`${URL_BASE}/?auto=1&shell=electron`); } },
        { type: 'separator' },
        { label: 'Ícone flutuante na tela', type: 'checkbox', checked: lerCasca().flutuante_ligado !== false, click: (item) => { gravarCasca({ flutuante_ligado: item.checked }); atualizarFlutuante(); } },
        { label: 'Iniciar com o Windows', type: 'checkbox', checked: iniciaComWindows(),
          click: (item) => { app.setLoginItemSettings({ openAtLogin: item.checked, args: ['--oculto'] }); } },
        { label: 'Abrir a pasta de dados', click: () => shell.openPath(pastaDados()) },
        { type: 'separator' },
        { label: `Versão ${app.getVersion()}`, enabled: false },
        ...(atualizacao.estado === 'pronta' ? [{ label: `Reiniciar para atualizar (${atualizacao.versao})`, click: () => { saindo = true; atualizador.quitAndInstall(); } }]
            : atualizador ? [{ label: atualizacao.estado === 'baixando' ? `Baixando a atualização ${atualizacao.versao}...` : 'Verificar atualizações', enabled: atualizacao.estado !== 'baixando', click: verificarAtualizacao }] : []),
        { type: 'separator' },
        { label: `Atalho global: ${ATALHO.replace('Control', 'Ctrl')}`, enabled: false },
        { label: 'Sair do Jarvis', click: () => { saindo = true; app.quit(); } },
    ]);
    bandeja.setContextMenu(menu());
    bandeja.on('click', mostrarOuEsconder);
    bandeja.on('right-click', () => bandeja.setContextMenu(menu()));            // atualiza o "Iniciar com o Windows"
}

function configurarPermissoes() {
    const nossaOrigem = (url) => typeof url === 'string' && url.startsWith(URL_BASE);
    const liberadas = new Set(['media', 'audioCapture', 'videoCapture', 'fullscreen', 'clipboard-sanitized-write']);
    session.defaultSession.setPermissionRequestHandler((wc, permissao, ok, detalhes) => ok(liberadas.has(permissao) && nossaOrigem(detalhes && detalhes.requestingUrl || wc.getURL())));
    session.defaultSession.setPermissionCheckHandler((wc, permissao, origem) => liberadas.has(permissao) && nossaOrigem(origem || (wc && wc.getURL())));
}

ipcMain.handle('jarvis:info', () => ({ empacotado: EMPACOTADO, versao: app.getVersion(), dados: pastaDados(), porta: PORTA, atalho: ATALHO }));
ipcMain.on('jarvis:esconder', () => { if (janela) janela.hide(); });
ipcMain.on('jarvis:estado', (_e, estado) => { ultimoEstado = String(estado || 'espera'); if (flutuante && !flutuante.isDestroyed()) flutuante.webContents.send('estado', ultimoEstado); });

// ------------------------------------------------------------------ ícone flutuante (clique abre o Jarvis; arrastar muda de lugar)
const ARQ_CASCA = () => path.join(pastaDados(), 'casca.json');
function lerCasca() { try { return JSON.parse(fs.readFileSync(ARQ_CASCA(), 'utf8')); } catch (_) { return {}; } }
function gravarCasca(extra) { try { fs.writeFileSync(ARQ_CASCA(), JSON.stringify({ ...lerCasca(), ...extra }, null, 2)); } catch (_) { /* sem permissão: segue sem lembrar */ } }
const TAM_ICONE = 84;

function posicaoInicial() {
    const { screen } = require('electron');
    const salva = lerCasca().flutuante;
    if (salva && Number.isFinite(salva.x) && Number.isFinite(salva.y)) {
        const d = screen.getDisplayNearestPoint({ x: salva.x, y: salva.y }).workArea;
        return { x: Math.min(Math.max(salva.x, d.x), d.x + d.width - TAM_ICONE), y: Math.min(Math.max(salva.y, d.y), d.y + d.height - TAM_ICONE) };
    }
    const d = screen.getPrimaryDisplay().workArea;
    return { x: d.x + d.width - TAM_ICONE - 24, y: d.y + d.height - TAM_ICONE - 24 };
}

function criarFlutuante() {
    if (flutuante && !flutuante.isDestroyed()) return;
    const pos = posicaoInicial();
    flutuante = new BrowserWindow({
        width: TAM_ICONE, height: TAM_ICONE, x: pos.x, y: pos.y, show: false, frame: false, transparent: true, resizable: false, maximizable: false,
        minimizable: false, fullscreenable: false, skipTaskbar: true, hasShadow: false, focusable: false, alwaysOnTop: true, backgroundColor: '#00000000',
        title: 'Jarvis (ícone)',
        webPreferences: { preload: path.join(__dirname, 'preload-flutuante.js'), contextIsolation: true, nodeIntegration: false, sandbox: true, backgroundThrottling: false },
    });
    flutuante.setAlwaysOnTop(true, 'screen-saver');
    flutuante.loadFile(path.join(__dirname, 'flutuante.html'));
    flutuante.webContents.once('did-finish-load', () => { flutuante.webContents.send('estado', ultimoEstado); atualizarFlutuante(); });
    flutuante.on('closed', () => { flutuante = null; });
}

function flutuanteLigado() { return lerCasca().flutuante_ligado !== false && !ARG_CAPTURA && !ARG_STREAM && !ARG_GESTOS && !ARG_CLIQUES; }

// o ícone só aparece quando a tela principal NÃO está à vista (escondida na bandeja ou minimizada)
function atualizarFlutuante() {
    if (!flutuanteLigado()) { if (flutuante && !flutuante.isDestroyed()) flutuante.hide(); return; }
    if (!flutuante || flutuante.isDestroyed()) { criarFlutuante(); return; }
    const principalVisivel = janela && janela.isVisible() && !janela.isMinimized();
    if (principalVisivel) flutuante.hide(); else flutuante.showInactive();
}

function abrirPrincipal() { if (janela) { if (janela.isMinimized()) janela.restore(); janela.show(); janela.focus(); } }

ipcMain.on('flutuante:clique', abrirPrincipal);
ipcMain.on('flutuante:menu', () => {
    Menu.buildFromTemplate([
        { label: 'Abrir o Jarvis', click: abrirPrincipal },
        { label: 'Esconder o ícone flutuante', click: () => { gravarCasca({ flutuante_ligado: false }); atualizarFlutuante(); } },
        { type: 'separator' },
        { label: 'Sair do Jarvis', click: () => { saindo = true; app.quit(); } },
    ]).popup({ window: flutuante });
});
ipcMain.on('flutuante:arrastar-inicio', () => { if (flutuante) { const [x, y] = flutuante.getPosition(); arrasto = { x, y }; } });
ipcMain.on('flutuante:arrastar', (_e, dx, dy) => { if (flutuante && arrasto) flutuante.setPosition(Math.round(arrasto.x + dx), Math.round(arrasto.y + dy)); });
ipcMain.on('flutuante:arrastar-fim', () => {
    if (flutuante && arrasto) { const [x, y] = flutuante.getPosition(); gravarCasca({ flutuante: { x, y } }); }
    arrasto = null;
});

// ------------------------------------------------------------------ ciclo de vida
app.on('second-instance', () => { if (janela) { janela.show(); janela.focus(); } });
app.on('before-quit', () => { saindo = true; });
app.on('will-quit', () => { globalShortcut.unregisterAll(); pararServidor(); });
app.on('window-all-closed', () => { /* continua na bandeja */ });

app.whenReady().then(async () => {
    configurarPermissoes();
    configurarAtualizacao();
    const ok = await garantirServidor();
    if (!ok && !MODO_TESTE) {
        const { dialog } = require('electron');
        dialog.showErrorBox('Jarvis', 'Não consegui iniciar o servidor do Jarvis. Veja logs\\servidor.log na pasta de dados.');
        saindo = true; pararServidor(); app.quit(); return;
    }
    criarJanela();
    montarBandeja();
    atualizarFlutuante();
    if (!globalShortcut.register(ATALHO, mostrarOuEsconder)) log('atalho global em uso por outro programa:', ATALHO);
    if (ARG_CLIQUES) rodarTesteCliques(); else if (ARG_GESTOS) rodarTesteGestos(); else if (ARG_STREAM) rodarTesteStream(ARG_STREAM); else if (ARG_CAPTURA) rodarCaptura(ARG_CAPTURA); else if (MODO_TESTE_VOZ) rodarTesteVoz(ok); else if (MODO_TESTE) rodarTeste(ok);
});

// ------------------------------------------------------------------ teste automático (electron . --teste)
async function rodarTeste(servidorOk) {
    const r = { servidor: servidorOk, itens: [] };
    const marca = (nome, ok, extra = '') => r.itens.push({ nome, ok: !!ok, extra });
    try {
        await new Promise((res) => (janela.webContents.isLoading() ? janela.webContents.once('did-finish-load', res) : res()));
        await new Promise((res) => setTimeout(res, 1500));
        const dados = await janela.webContents.executeJavaScript(`({
            titulo: document.title, ua: navigator.userAgent, gancho: typeof window.__jarvis,
            shell: window.jarvisShell ? window.jarvisShell.empacotado : null,
            sr: typeof (window.SpeechRecognition || window.webkitSpeechRecognition),
            estado: document.body.dataset.estado || null, conexao: (document.getElementById('i-conexao') || {}).textContent || null,
            midia: !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
            webgl: (() => { try { const g = document.createElement('canvas').getContext('webgl'); const e = g.getExtension('WEBGL_debug_renderer_info'); return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : 'sem info'; } catch (_) { return 'sem webgl'; } })(),
        })`);
        r.dados = dados;
        r.fala = await janela.webContents.executeJavaScript(`new Promise((res) => {
            const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SR) return res({ existe: false });
            const rec = new SR(); rec.lang = 'pt-BR'; const t = setTimeout(() => { try { rec.abort(); } catch (_) {} res({ existe: true, evento: 'nenhum em 6 s' }); }, 6000);
            rec.onerror = (e) => { clearTimeout(t); res({ existe: true, evento: 'erro', erro: e.error }); };
            rec.onstart = () => { /* iniciou: espera erro ou resultado */ };
            rec.onresult = () => { clearTimeout(t); res({ existe: true, evento: 'resultado' }); };
            try { rec.start(); } catch (e) { clearTimeout(t); res({ existe: true, evento: 'exceção', erro: String(e) }); }
        })`);
        marca('o servidor respondeu à casca', servidorOk);
        marca('a interface carregou (gancho __jarvis presente)', dados.gancho === 'object');
        marca('roda dentro do Electron (sem Chrome)', /Electron/.test(dados.ua));
        marca('o preload expôs jarvisShell', dados.shell !== null);
        marca('a interface conectou ao servidor por WebSocket', /LOCAL/.test(dados.conexao || ''), String(dados.conexao));
        marca('microfone/câmera disponíveis (getUserMedia)', dados.midia);
        marca('WebGL disponível', !/sem webgl/.test(String(dados.webgl)), String(dados.webgl));
        marca('atalho global registrado', globalShortcut.isRegistered(ATALHO));
        const dorme = (ms) => new Promise((r) => setTimeout(r, ms));
        const f = flutuante;
        marca('o ícone flutuante existe', !!f && !f.isDestroyed());
        if (f && !f.isDestroyed()) {
            const { screen } = require('electron');
            const b = f.getBounds(), wa = screen.getDisplayMatching(b).workArea;
            marca('o ícone fica sempre por cima', f.isAlwaysOnTop());
            marca('o ícone está dentro da área útil da tela', b.x >= wa.x && b.y >= wa.y && b.x + b.width <= wa.x + wa.width && b.y + b.height <= wa.y + wa.height, JSON.stringify(b));
            marca('o ícone aparece com a tela principal escondida', f.isVisible());
            await janela.webContents.executeJavaScript("window.__jarvis.setEstado('pensando')");
            await dorme(500);
            const est = await f.webContents.executeJavaScript('document.body.dataset.estado');
            marca('o ícone espelha o estado da interface (pensando)', est === 'pensando', String(est));
            f.webContents.sendInputEvent({ type: 'mouseDown', x: 42, y: 42, button: 'left', clickCount: 1 });
            f.webContents.sendInputEvent({ type: 'mouseUp', x: 42, y: 42, button: 'left', clickCount: 1 });
            await dorme(700);
            marca('clicar no ícone abre a tela principal', janela.isVisible());
            marca('o ícone some enquanto a tela principal está aberta', !f.isVisible());
            janela.hide();
            await dorme(400);
            marca('e volta quando a tela principal é escondida', f.isVisible());
        }
    } catch (e) { marca('teste sem exceção', false, String(e)); }
    process.stdout.write('RESULTADO_CASCA ' + JSON.stringify(r) + '\n');
    saindo = true;
    pararServidor(); app.exit(r.itens.every((i) => i.ok) ? 0 : 1);
}

// ------------------------------------------------------------------ teste da VOZ (electron . --teste-voz): microfone falso -> servidor -> texto -> interface
async function rodarTesteVoz(servidorOk) {
    const r = { servidor: servidorOk };
    janela.webContents.on('console-message', (e) => { if (process.env.JARVIS_DEBUG_PAGINA) process.stdout.write('[pagina] ' + String(e.message || '').slice(0, 220) + String.fromCharCode(10)); });
    try {
        await new Promise((res) => (janela.webContents.isLoading() ? janela.webContents.once('did-finish-load', res) : res()));
        await new Promise((res) => setTimeout(res, 1500));
        for (let i = 0; i < 120; i++) { if (await janela.webContents.executeJavaScript("fetch('/api/saude').then((x) => x.json()).then((x) => x.stt === 'pronto')")) break; await new Promise((res) => setTimeout(res, 500)); }      // o 'microfone' falso é tocado UMA vez ao abrir: só abre com o Whisper pronto
        await janela.webContents.executeJavaScript(`(() => {
            window.__capturadas = [];
            const original = WebSocket.prototype.send;
            WebSocket.prototype.send = function (d) {            // grava as falas que iriam ao modelo e NÃO as envia (sem gastar API); o áudio binário segue
                if (typeof d === 'string') { try { const m = JSON.parse(d); if (m.tipo === 'fala' || m.tipo === 'ativar') { window.__capturadas.push({ ...m, em: performance.now() }); return; } } catch (_) {} }
                return original.call(this, d);
            };
            window.__t0 = performance.now();
            window.__jarvis.estenderConversa();
            window.__jarvis.setEstado('ouvindo');
            window.__jarvis.iniciarReconhecimento();
        })()`);
        const limite = Date.now() + 45000;
        let capturadas = [];
        while (Date.now() < limite) {
            capturadas = await janela.webContents.executeJavaScript('window.__capturadas');
            if (capturadas.length) break;
            await new Promise((res) => setTimeout(res, 300));
        }
        r.motor = await janela.webContents.executeJavaScript('window.__jarvis.motorVoz()');
        r.sttPronto = await janela.webContents.executeJavaScript('window.__jarvis.sttPronto()');
        r.quadros = await janela.webContents.executeJavaScript('window.SttLocal.quadrosEnviados()');
        r.capturadas = capturadas;
        try { r.recentes = await janela.webContents.executeJavaScript("fetch('/api/voz-recente').then(x => x.json())"); } catch (_) {}
        r.apos_ms = capturadas.length ? Math.round(capturadas[0].em - (await janela.webContents.executeJavaScript('window.__t0'))) : null;
    } catch (e) { r.erro = String(e); }
    process.stdout.write('RESULTADO_VOZ ' + JSON.stringify(r) + '\n');
    saindo = true;
    pararServidor(); app.exit(r.capturadas && r.capturadas.length ? 0 : 1);
}

// ------------------------------------------------------------------ capturas de tela da interface (electron . --captura <pasta>): a janela aparece por ~15 s
async function rodarCaptura(pasta) {
    fs.mkdirSync(pasta, { recursive: true });
    const erros = [];
    janela.webContents.on('console-message', (e) => { const nivel = e.level !== undefined ? e.level : 0; if (nivel === 'error' || nivel === 'warning' || nivel >= 2) erros.push(String(e.message || '').slice(0, 220)); });
    janela.setSize(1440, 860); janela.center();
    const dorme = (ms) => new Promise((r) => setTimeout(r, ms));
    const js = (c) => janela.webContents.executeJavaScript(c);
    await new Promise((res) => (janela.webContents.isLoading() ? janela.webContents.once('did-finish-load', res) : res()));
    await js(`document.getElementById('inicio').classList.add('oculto'); window.__jarvis.setEstado('espera');`);
    const tira = async (nome) => { const img = await janela.webContents.capturePage(); fs.writeFileSync(path.join(pasta, nome + '.png'), img.toPNG()); log('captura', nome); };
    for (let i = 0; i < 80; i++) { if (await js(`document.body.classList.contains('ui3d-ok')`)) break; await dorme(250); }       // a abertura conta a partir daqui
    await dorme(700); await tira('1-entrada-0.7s');
    await dorme(1000); await tira('2-entrada-1.7s');
    await dorme(1100); await tira('2b-entrada-2.8s');
    await dorme(2200); await js(`window.__jarvis.setEstado('ouvindo')`); await dorme(600); await tira('3-ouvindo');
    await js(`window.__jarvis.setEstado('pensando')`); await dorme(900); await tira('4-pensando');
    await js(`window.__jarvis.setEstado('falando')`); await dorme(700); await tira('5-falando');
    // animações das ações: abrir/fechar programa, mira de controle, câmera, foco e arrastar painel
    await js(`window.__jarvis.setEstado('espera')`);
    await js(`Acoes.evento({ id: 'a1', estado: 'inicio', rotulo: 'PROGRAMA', detalhe: 'Calculadora' }); Acoes.evento({ id: 'a2', estado: 'inicio', rotulo: 'PESQUISA', detalhe: 'melhores notebooks 2026' });`);
    await dorme(750); await tira('6-abrir-programa');
    await dorme(900); await js(`Acoes.evento({ id: 'a1', estado: 'fim', rotulo: 'PROGRAMA' }); Acoes.evento({ id: 'a3', estado: 'inicio', rotulo: 'WINDOWS', detalhe: 'fechar Calculadora' });`);
    await dorme(800); await tira('7-fechar-programa');
    await dorme(1500); await js(`Acoes.evento({ id: 'a4', estado: 'inicio', rotulo: 'CONTROLE', detalhe: 'clicar em Enviar' });`);
    await dorme(450); await tira('8-controle');
    await dorme(1600);
    await js(`document.getElementById('camera-pip').hidden = false; Acoes.cameraAbrir();`);
    await dorme(1100); await tira('9-camera-mira');
    await js(`(() => { const c = document.createElement('canvas'); c.width = 320; c.height = 180; const g = c.getContext('2d'); g.fillStyle = '#356'; g.fillRect(0, 0, 320, 180); Acoes.cameraDisparo(c); })()`);
    await dorme(500); await tira('10-camera-foto');
    await dorme(1500); await js(`document.getElementById('camera-pip').hidden = true;`);
    const caixa = await js(`(() => { const r = document.querySelector('#p-clima h2').getBoundingClientRect(); return [Math.round(r.left + 40), Math.round(r.top + r.height / 2)]; })()`);
    const wc = janela.webContents;
    wc.debugger.attach('1.3');
    const mouse = (type, x, y, extra = {}) => wc.debugger.sendCommand('Input.dispatchMouseEvent', { type, x, y, button: 'left', ...extra });
    await mouse('mouseMoved', caixa[0], caixa[1], { button: 'none' });
    await dorme(600);                                       // o painel sobe ao passar o mouse: espera assentar e pega o cabeçalho onde ele está agora
    const cx = await js(`(() => { const r = document.querySelector('#p-clima h2').getBoundingClientRect(); return [Math.round(r.left + 40), Math.round(r.top + r.height / 2)]; })()`); caixa[0] = cx[0]; caixa[1] = cx[1];
    await mouse('mousePressed', caixa[0], caixa[1], { buttons: 1, clickCount: 1 });
    for (let i = 1; i <= 12; i++) { await mouse('mouseMoved', caixa[0] + i * 25, caixa[1] + i * 12, { buttons: 1 }); await dorme(16); }
    await dorme(60); await tira('11-arrastando');
    await mouse('mouseReleased', caixa[0] + 300, caixa[1] + 144, { buttons: 0, clickCount: 1 }); wc.debugger.detach();
    await dorme(900);
    const arrasto = await js(`(() => { const e = document.getElementById('p-clima'); return { dx: e.style.getPropertyValue('--dx'), dy: e.style.getPropertyValue('--dy'), salvo: localStorage.getItem('jarvis_painel_pos') }; })()`);
    await tira('12-painel-movido');
    await js(`document.querySelector('#p-clima h2').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))`);
    await dorme(900);
    const volta = await js(`document.getElementById('p-clima').style.getPropertyValue('--dx')`);
    await js(`Acoes.foco(['rede'], 4)`); await dorme(800); await tira('13-foco-rede');
    await js(`document.getElementById('btn-layout').click()`); await dorme(500); await tira('14-menu-layout');
    await js(`document.getElementById('btn-layout').click(); UI.comando({ comando: 'ui_layout', acao: 'preset', nome: 'foco' })`); await dorme(900); await tira('15-foco');
    await js(`UI.comando({ comando: 'ui_layout', acao: 'preset', nome: 'moderno' }); Acoes.evento({ id: 'z1', estado: 'inicio', rotulo: 'PROGRAMA', detalhe: 'Calculadora' })`); await dorme(1200); await tira('16-moderno-acao');
    criarFlutuante(); await dorme(1300); flutuante.showInactive();
    for (const e of ['ouvindo', 'pensando', 'falando']) { flutuante.webContents.send('estado', e); await dorme(1000); const im = await flutuante.webContents.capturePage(); fs.writeFileSync(path.join(pasta, 'icone-' + e + '.png'), im.toPNG()); }
    const info = await js(`window.Cena3D ? window.Cena3D.info() : null`);
    const corpo = await js(`document.body.className`);
    process.stdout.write('RESULTADO_CAPTURA ' + JSON.stringify({ info, corpo, arrasto, volta, erros: erros.slice(0, 12) }) + '\n');
    saindo = true; pararServidor(); app.exit(0);
}

// ------------------------------------------------------------------ teste da voz em STREAMING (electron . --teste-stream <arquivo.mp3>): janela MUDA
async function rodarTesteStream(mp3) {
    const r = { servidor: true };
    janela.webContents.on('console-message', (e) => { if (process.env.JARVIS_DEBUG_PAGINA) process.stdout.write('[pagina] ' + String(e.message || '').slice(0, 200) + '\n'); });
    try {
        await new Promise((res) => (janela.webContents.isLoading() ? janela.webContents.once('did-finish-load', res) : res()));
        await new Promise((res) => setTimeout(res, 1500));
        const b64 = fs.readFileSync(mp3).toString('base64');
        r.dados = await janela.webContents.executeJavaScript(`(async () => {
            const J = window.__jarvis, dorme = (ms) => new Promise((x) => setTimeout(x, ms));
            const bin = Uint8Array.from(atob(${JSON.stringify(b64)}), (c) => c.charCodeAt(0));
            const partes = (n) => { const t = Math.ceil(bin.length / n), out = []; for (let i = 0; i < bin.length; i += t) { let s = ''; const f = bin.subarray(i, i + t); for (let k = 0; k < f.length; k++) s += String.fromCharCode(f[k]); out.push(btoa(s)); } return out; };
            window.__streamLog = [];
            const esperar = async (cond, ms) => { const lim = performance.now() + ms; while (performance.now() < lim) { if (cond()) return true; await dorme(50); } return false; };
            const R = { suporta: !!(window.MediaSource && MediaSource.isTypeSupported('audio/mpeg')), erros: [] };
            window.addEventListener('error', (e) => R.erros.push(String(e.message)));

            // 1) uma frase chegando devagar (8 pedaços, 150 ms entre eles): o som deve começar bem antes do último pedaço
            const p1 = partes(8);
            const t0 = performance.now();
            J.tratar({ tipo: 'fala_ini', id: 1, texto: 'Primeira frase em streaming.', emocao: null });
            for (let i = 0; i < p1.length; i++) { J.tratar({ tipo: 'fala_chunk', id: 1, audio: p1[i] }); if (i === 0) R.t_primeiro_pedaco = performance.now() - t0; await dorme(150); }
            R.t_ultimo_pedaco = performance.now() - t0;
            J.tratar({ tipo: 'fala_fim', id: 1 });
            // 2) uma segunda frase que chega INTEIRA enquanto a primeira ainda toca (pré-carregada): deve tocar logo depois
            const p2 = partes(4);
            J.tratar({ tipo: 'fala_ini', id: 2, texto: 'Segunda frase.', emocao: 'animado' });
            for (const c of p2) J.tratar({ tipo: 'fala_chunk', id: 2, audio: c });
            J.tratar({ tipo: 'fala_fim', id: 2 });
            R.estado_durante = J.interno().estado;
            R.streams_abertos_durante = J.streams();
            await esperar(() => window.__streamLog.filter((l) => l[0] === 'ended').length >= 2, 20000);
            await dorme(400);
            const log = window.__streamLog;
            const quando = (nome, id) => { const l = log.find((x) => x[0] === nome && x[3] === id); return l ? Math.round(l[1] - t0) : null; };
            R.playing1_ms = quando('playing', 1); R.ended1_ms = quando('ended', 1); R.playing2_ms = quando('playing', 2); R.ended2_ms = quando('ended', 2);
            R.duracao1_s = (log.find((x) => x[0] === 'ended' && x[3] === 1) || [0, 0, 0])[2]; R.duracao2_s = (log.find((x) => x[0] === 'ended' && x[3] === 2) || [0, 0, 0])[2];
            R.estado_depois = J.interno().estado; R.streams_depois = J.streams();

            // 3) interromper no meio: tudo é liberado e o estado sai de 'falando'
            window.__streamLog = [];
            const p3 = partes(6);
            J.tratar({ tipo: 'fala_ini', id: 3, texto: 'Frase que vai ser cortada.', emocao: null });
            for (let i = 0; i < 3; i++) J.tratar({ tipo: 'fala_chunk', id: 3, audio: p3[i] });
            await esperar(() => window.__streamLog.some((l) => l[0] === 'playing'), 5000);
            R.cortada_tocou = window.__streamLog.some((l) => l[0] === 'playing');
            J.interromper();
            for (let i = 3; i < p3.length; i++) J.tratar({ tipo: 'fala_chunk', id: 3, audio: p3[i] });   // pedaços atrasados depois do corte: devem ser ignorados
            J.tratar({ tipo: 'fala_fim', id: 3 });
            await dorme(500);
            R.estado_apos_corte = J.interno().estado; R.streams_apos_corte = J.streams(); R.tocando_apos_corte = J.interno().tocando;
            return R;
        })()`);
    } catch (e) { r.erro = String(e); }
    process.stdout.write('RESULTADO_STREAM ' + JSON.stringify(r) + '\n');
    saindo = true;
    pararServidor(); app.exit(r.dados ? 0 : 1);
}

// ------------------------------------------------------------------ teste dos GESTOS dentro do Electron (electron . --teste-gestos): câmera FALSA, janela muda, nada é enviado ao servidor
async function rodarTesteGestos() {
    const r = { servidor: true };
    try {
        await new Promise((res) => (janela.webContents.isLoading() ? janela.webContents.once('did-finish-load', res) : res()));
        await new Promise((res) => setTimeout(res, 1500));
        r.dados = await janela.webContents.executeJavaScript(`(async () => {
            const dorme = (ms) => new Promise((x) => setTimeout(x, ms));
            const R = { erros: [], enviados: [] };
            window.addEventListener('error', (e) => R.erros.push(String(e.message)));
            const original = WebSocket.prototype.send;
            WebSocket.prototype.send = function (d) { if (typeof d === 'string') { try { const m = JSON.parse(d); if (m.tipo === 'gesto' || m.tipo === 'fala') { R.enviados.push(m); return; } } catch (_) {} } return original.call(this, d); };
            window.__gestosCPU = ${process.env.JARVIS_GESTOS_CPU === '1'}; R.disponivel = Gestos.disponivel();
            const t0 = performance.now();
            const e = await Gestos.ligar();
            R.carga_ms = Math.round(performance.now() - t0);
            R.ligou = e.ligado; R.erro = e.erro; R.delegate = e.delegate;
            await dorme(4000);
            const e2 = Gestos.estado();
            R.fps = e2.fps; R.ms_mao = e2.ms_mao; R.ms_rosto = e2.ms_rosto; R.erro_depois = e2.erro; R.pill_on = document.getElementById('pill-gestos').classList.contains('on'); R.corpo_on = document.body.classList.contains('gestos-on');
            // encanamento: sem armar, deslizar NÃO envia; depois da palma, envia (e o envio é capturado, nada chega ao servidor)
            const J = window.__jarvis;
            J.tratarGesto({ tipo: 'deslizar_direita' });
            R.sem_armar = R.enviados.length;
            J.tratarGesto({ tipo: 'palma' });
            J.tratarGesto({ tipo: 'deslizar_direita' });
            J.tratarGesto({ tipo: 'pinca' });
            R.apos_armar = R.enviados.filter((m) => m.tipo === 'gesto').map((m) => m.nome);
            R.armado_visual = document.body.classList.contains('gestos-armado');
            J.tratarGesto({ tipo: 'cabeca_sim' });                  // sem pergunta do Jarvis: não deve responder nada
            R.fala_sem_pergunta = R.enviados.filter((m) => m.tipo === 'fala').length;
            Gestos.desligar();
            await dorme(300);
            R.desligou = !Gestos.estado().ligado && !document.getElementById('pill-gestos').classList.contains('on');
            return R;
        })()`);
    } catch (e) { r.erro = String(e); }
    process.stdout.write('RESULTADO_GESTOS ' + JSON.stringify(r) + '\n');
    saindo = true; pararServidor(); app.exit(r.dados ? 0 : 1);
}

// ------------------------------------------------------------------ teste de CLIQUES REAIS nos painéis (electron . --teste-cliques): janela escondida, entrada de mouse pelo DevTools
async function rodarTesteCliques() {
    const r = { servidor: true, variantes: {} };
    try {
        await new Promise((res) => (janela.webContents.isLoading() ? janela.webContents.once('did-finish-load', res) : res()));
        const js = (c) => janela.webContents.executeJavaScript(c);
        const dorme = (ms) => new Promise((x) => setTimeout(x, ms));
        janela.setSize(1440, 860);
        for (let i = 0; i < 80; i++) { if (await js(`document.body.classList.contains('ui3d-ok')`)) break; await dorme(250); }
        await dorme(4500);                                              // termina a entrada dos painéis
        await js(`document.getElementById('inicio').classList.add('oculto')`);
        await js(`window.__alvos = []; addEventListener('pointerdown', (e) => window.__alvos.push(e.target.tagName + '.' + (e.target.className || '') + '#' + e.target.id + ' <' + ((e.target.closest && e.target.closest('.painel')) || {}).id + '>'), true);`);
        const wc = janela.webContents;
        wc.debugger.attach('1.3');
        const mouse = (type, x, y, extra = {}) => wc.debugger.sendCommand('Input.dispatchMouseEvent', { type, x, y, button: 'left', ...extra });
        const alvos = ['#p-clima h2', '#p-sistema h2', '#mem-ver', '#p-agenda h2', '#p-nucleo h2'];
        const variantes = {
            atual: '',
            hud_plano: `#hud{transform-style:flat !important}`,
            colunas_planas: `.coluna{transform-style:flat !important}`,
            tudo_plano: `#hud,.coluna,.rodape{transform-style:flat !important}`,
            sem_translateZ: `.painel{transform:none !important;translate:none !important}`,
            sem_hover3d: `.painel:hover{transform:none !important}`,
        };
        for (const [nome, css] of Object.entries(variantes)) {
            await js(`(() => { let e = document.getElementById('__var'); if (!e) { e = document.createElement('style'); e.id = '__var'; document.head.appendChild(e); } e.textContent = ${JSON.stringify(css)}; })()`);
            await dorme(700);
            const res = [];
            for (const sel of alvos) {
                const ponto = await js(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return null; const r = e.getBoundingClientRect(); return [Math.round(r.left + Math.min(40, r.width / 2)), Math.round(r.top + r.height / 2)]; })()`);
                if (!ponto) { res.push(sel + ': (não achei)'); continue; }
                await js(`window.__alvos.length = 0`);
                await mouse('mouseMoved', ponto[0], ponto[1], { button: 'none' }); await dorme(450);
                await mouse('mousePressed', ponto[0], ponto[1], { buttons: 1, clickCount: 1 });
                await mouse('mouseReleased', ponto[0], ponto[1], { buttons: 0, clickCount: 1 });
                const t = await js(`window.__alvos.slice(0, 1)`);
                res.push(sel + ' -> ' + (t[0] || 'nada'));
            }
            r.variantes[nome] = res;
        }
        wc.debugger.detach();
    } catch (e) { r.erro = String(e); }
    process.stdout.write('RESULTADO_CLIQUES ' + JSON.stringify(r) + '\n');
    saindo = true; pararServidor(); app.exit(0);
}
