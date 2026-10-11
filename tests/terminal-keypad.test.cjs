const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const handlers = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../src/terminal-keypad.js'), 'utf8'), {
  document: { addEventListener: (type, callback) => { handlers[type] = callback; } },
});
function event(code, key, terminal = true) {
  return { code, key, target: { matches: () => terminal } };
}
test('keypad Home and End normalize on press and release', () => {
  for (const type of ['keydown', 'keyup']) {
    for (const [code, key, expected] of [['Numpad7', 'Home', 'NumpadHome'], ['Numpad1', 'End', 'NumpadEnd']]) {
      const value = event(code, key); handlers[type](value); assert.equal(value.code, expected);
    }
  }
});
test('keypad arrows and paging normalize', () => {
  for (const [code, key, expected] of [['Numpad4', 'ArrowLeft', 'NumpadArrowLeft'], ['Numpad8', 'ArrowUp', 'NumpadArrowUp'], ['Numpad9', 'PageUp', 'NumpadPageUp'], ['Numpad0', 'Insert', 'NumpadInsert'], ['NumpadDecimal', 'Delete', 'NumpadDelete']]) {
    const value = event(code, key); handlers.keydown(value); assert.equal(value.code, expected);
  }
});
test('numeric keypad input, ordinary Home, and nonterminal inputs stay unchanged', () => {
  for (const value of [event('Numpad7', '7'), event('Home', 'Home'), event('Numpad7', 'Home', false)]) {
    const original = value.code; handlers.keydown(value); assert.equal(value.code, original);
  }
});
