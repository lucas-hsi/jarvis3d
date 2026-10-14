// Ponte mínima e segura entre a interface (que roda em sandbox) e a casca. Nada de Node na página.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('jarvisShell', {
    empacotado: false,                       // sobrescrito logo abaixo com o valor real
    info: () => ipcRenderer.invoke('jarvis:info'),
    esconder: () => ipcRenderer.send('jarvis:esconder'),
    estado: (e) => ipcRenderer.send('jarvis:estado', e),
});

ipcRenderer.invoke('jarvis:info').then((i) => {
    try { window.__jarvisShellInfo = i; } catch (_) { /* contextIsolation: ignorado */ }
});
