const { app, ipcMain, BrowserWindow } = require('electron');
const path = require('node:path');
const { Store } = require('./storage.cjs');

const store = new Store(process.env.T3_PERSISTED_DATA_DIR || path.join(__dirname, '..', 'data'));
const allowed = event => event.senderFrame && event.senderFrame.url.startsWith('t3code://app/');

ipcMain.handle('t3-persisted:read', event => {
  return allowed(event) ? store.read() : { enabled: false, collapsed: false, members: [] };
});

ipcMain.handle('t3-persisted:update', (event, operation) => {
  if (!allowed(event)) throw new Error('Persisted is only available in the main T3 window.');
  const snapshot = store.update(operation);
  for (const window of BrowserWindow.getAllWindows()) {
    if (window.webContents.getURL().startsWith('t3code://app/')) {
      window.webContents.send('t3-persisted:changed', snapshot);
    }
  }
  return snapshot;
});

// Test instrumentation is loaded only in an explicitly isolated test launch.
if (process.env.T3_PERSISTED_TEST_DRIVER && process.env.T3CODE_HOME && process.env.XDG_CONFIG_HOME) {
  require(process.env.T3_PERSISTED_TEST_DRIVER);
}
