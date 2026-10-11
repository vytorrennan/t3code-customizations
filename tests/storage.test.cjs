const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { Store } = require('../src/storage.cjs');

function temporary(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'persisted-store-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

test('membership is durable, isolated by environment, and removal restores normal membership', t => {
  const directory = temporary(t);
  const store = new Store(directory);
  const ref = { environmentId: 'machine-a', threadId: 'thread-1' };
  store.update({ type: 'add', ref });
  store.update({ type: 'add', ref });
  store.update({ type: 'add', ref: { ...ref, environmentId: 'machine-b' } });
  store.update({ type: 'collapse', collapsed: true });
  const restarted = new Store(directory);
  assert.equal(restarted.read().members.length, 2);
  assert.equal(restarted.read().collapsed, true);
  assert.equal(restarted.update({ type: 'remove', ref }).members[0].environmentId, 'machine-b');
  assert.equal(fs.statSync(store.file).mode & 0o777, 0o600);
  assert.equal(JSON.parse(fs.readFileSync(store.file + '.bak')).members.length, 2);
});

test('corrupt storage disables grouping and never overwrites the damaged file', t => {
  const directory = temporary(t);
  const store = new Store(directory);
  fs.writeFileSync(store.file, '{broken');
  assert.equal(store.read().enabled, false);
  assert.throws(() => store.update({ type: 'add', ref: { environmentId: 'a', threadId: 'b' } }));
  assert.equal(fs.readFileSync(store.file, 'utf8'), '{broken');
});

test('invalid actions do not create or alter membership', t => {
  const store = new Store(temporary(t));
  assert.throws(() => store.update({ type: 'add', ref: { environmentId: 'a' } }));
  assert.throws(() => store.update({ type: 'delete' }));
  assert.equal(fs.existsSync(store.file), false);
});
