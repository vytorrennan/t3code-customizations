// Normalize keypad navigation before Ghostty reads the physical key code.
// Browsers report keypad Home as key=Home, code=Numpad7 when Num Lock is off.
(() => {
  const navigation = new Map([
    ['Home', 'NumpadHome'], ['End', 'NumpadEnd'],
    ['ArrowUp', 'NumpadArrowUp'], ['ArrowDown', 'NumpadArrowDown'],
    ['ArrowLeft', 'NumpadArrowLeft'], ['ArrowRight', 'NumpadArrowRight'],
    ['PageUp', 'NumpadPageUp'], ['PageDown', 'NumpadPageDown'],
    ['Insert', 'NumpadInsert'], ['Delete', 'NumpadDelete'],
    ['Clear', 'NumpadBegin'],
  ]);
  const normalize = event => {
    if (!event.target?.matches?.('textarea.t3-ghostty-input')) return;
    if (!event.code.startsWith('Numpad')) return;
    const code = navigation.get(event.key);
    if (code) Object.defineProperty(event, 'code', { value: code, configurable: true });
  };
  document.addEventListener('keydown', normalize, true);
  document.addEventListener('keyup', normalize, true);
})();
