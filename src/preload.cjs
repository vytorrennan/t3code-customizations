(() => {
  const { contextBridge, ipcRenderer } = require('electron');
  contextBridge.exposeInMainWorld('t3PersistedBridge', {
    read: () => ipcRenderer.invoke('t3-persisted:read'),
    update: operation => ipcRenderer.invoke('t3-persisted:update', operation),
    subscribe: listener => {
      const handler = (_event, snapshot) => listener(snapshot);
      ipcRenderer.on('t3-persisted:changed', handler);
      return () => ipcRenderer.removeListener('t3-persisted:changed', handler);
    },
  });
})();
