const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { Store } = require('../src/storage.cjs');
const os = require('node:os');
const path = require('node:path');

test('menu actions commit membership before changing visibility and preserve native actions', async t => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'persisted-renderer-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const store = new Store(directory);
  const context = vm.createContext({ console, t3PersistedBridge: { read: () => store.read(), subscribe: () => {}, update: async operation => store.update(operation) } });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../src/renderer.js'), 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  const addon = context.__t3Persisted;
  const thread = { environmentId: 'a', id: 'b' };
  const original = [{ id: 'snooze', label: 'Snooze' }, { id: 'delete', label: 'Delete' }];
  assert.equal(addon.menu(original, thread)[1].label, 'Move to Persisted');
  const pending = addon.handle('persisted:add', thread);
  assert.equal(addon.getSnapshot().has(thread), false);
  await pending;
  assert.equal(addon.getSnapshot().has(thread), true);
  assert.equal(addon.menu(original, thread)[1].label, 'Remove from Persisted');
  await addon.handle('persisted:remove', thread);
  assert.equal(addon.getSnapshot().has(thread), false);
  assert.equal(original.length, 2);
});

test('missing bridge leaves all native threads visible', () => {
  const context = vm.createContext({ console });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../src/renderer.js'), 'utf8'), context);
  assert.equal(context.__t3Persisted.getSnapshot().enabled, false);
  assert.equal(context.__t3Persisted.getSnapshot().has({ environmentId: 'a', id: 'b' }), false);
});
