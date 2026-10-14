// Ponte mínima do ícone flutuante: recebe o estado do Jarvis e avisa cliques e arrastos. Sem Node na página.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('jarvisFlutuante', {
    onEstado: (cb) => ipcRenderer.on('estado', (_e, estado) => cb(estado)),
    clique: () => ipcRenderer.send('flutuante:clique'),
    menu: () => ipcRenderer.send('flutuante:menu'),
    arrastarInicio: () => ipcRenderer.send('flutuante:arrastar-inicio'),
    arrastar: (dx, dy) => ipcRenderer.send('flutuante:arrastar', dx, dy),
    arrastarFim: () => ipcRenderer.send('flutuante:arrastar-fim'),
});
