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
  const second = { environmentId: 'a', id: 'c' };
  await addon.handle('persisted:add', second);
  assert.deepEqual(Array.from(addon.getSnapshot().sort([second, thread]), row => row.id), ['b', 'c']);
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

test('native drag targets keep shelves separate and use native array-move order', () => {
  const context = vm.createContext({ console });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../src/renderer.js'), 'utf8'), context);
  const addon = context.__t3Persisted;
  const persisted = ['p1', 'p2', 'p3'].map(key => ({ kind: 'thread', key, section: 'persisted' }));
  const native = ['n1', 'n2'].map(key => ({ kind: 'thread', key, section: 'active' }));
  const items = [{ kind: 'marker', marker: 'persisted-header' }, ...persisted,
    { kind: 'marker', marker: 'persisted-divider' }, ...native];
  let nativeCalls = 0;
  const resolver = (rows, active, over) => {
    nativeCalls++;
    assert.deepEqual(Array.from(rows, row => row.key), ['n1', 'n2']);
    assert.equal(active, 'n2');
    assert.equal(over, 'n1');
    return 'native-result';
  };
  assert.deepEqual(Array.from(addon.target(resolver, items, 'p1', 'p3').persistedOrder), ['p2', 'p3', 'p1']);
  assert.deepEqual(Array.from(addon.target(resolver, items, 'p3', 'p1').persistedOrder), ['p3', 'p1', 'p2']);
  assert.equal(addon.target(resolver, items, 'p1', 'n1'), null);
  assert.equal(addon.target(resolver, items, 'n1', 'p1'), null);
  assert.equal(addon.target(resolver, items, 'n1', 'sidebar-marker-persisted-divider'), null);
  assert.equal(nativeCalls, 0);
  assert.equal(addon.target(resolver, items, 'n2', 'n1'), 'native-result');
  assert.equal(nativeCalls, 1);
});
