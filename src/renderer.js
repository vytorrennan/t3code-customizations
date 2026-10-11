(() => {
  const bridge = globalThis.t3PersistedBridge;
  const listeners = new Set();
  const disabled = { enabled: false, version: 1, collapsed: false, members: [] };
  let snapshot;
  const key = ref => JSON.stringify([ref.environmentId, ref.threadId ?? ref.id]);

  function publish(value) {
    const keys = new Set(value.members.map(key));
    const ranks = new Map(value.members.map((member, index) => [key(member), index]));
    snapshot = {
      ...value,
      has: thread => value.enabled && keys.has(key(thread)),
      sort: threads => [...threads].sort((a, b) => ranks.get(key(a)) - ranks.get(key(b))),
      toggleCollapsed: () => update({ type: 'collapse', collapsed: !snapshot.collapsed }),
    };
    for (const listener of listeners) listener();
  }

  const refFromKey = value => {
    const [environmentId, threadId] = JSON.parse(value);
    return { environmentId, threadId };
  };

  function drag(event, row) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    const source = row.dataset.persistedRef;
    const startY = event.clientY;
    let target, position, moved = false;
    const indicator = document.createElement('div');
    Object.assign(indicator.style, { position: 'fixed', height: '2px', background: 'var(--primary)', pointerEvents: 'none', zIndex: '99999' });
    const move = event => {
      if (Math.abs(event.clientY - startY) > 4) moved = true;
      target = undefined;
      indicator.remove();
      if (!moved || !row.isConnected) return;
      const rows = [...document.querySelectorAll('li[data-persisted-ref]')];
      const hovered = rows.find(candidate => {
        const box = candidate.getBoundingClientRect();
        return event.clientX >= box.left && event.clientX <= box.right && event.clientY >= box.top && event.clientY <= box.bottom;
      });
      if (!hovered || hovered.dataset.persistedRef === source) return;
      target = hovered.dataset.persistedRef;
      const box = hovered.getBoundingClientRect();
      position = event.clientY < box.top + box.height / 2 ? 'before' : 'after';
      Object.assign(indicator.style, { left: box.left + 'px', width: box.width + 'px', top: (position === 'before' ? box.top : box.bottom) + 'px' });
      document.body.appendChild(indicator);
    };
    const finish = event => {
      if (event.type === 'pointerup') move(event);
      document.removeEventListener('pointermove', move, true);
      document.removeEventListener('pointerup', finish, true);
      document.removeEventListener('pointercancel', finish, true);
      window.removeEventListener('blur', cancel);
      document.removeEventListener('keydown', escape, true);
      indicator.remove();
      if (event.type === 'pointerup' && target && snapshot.has(refFromKey(source)) && snapshot.has(refFromKey(target))) {
        update({ type: 'move', ref: refFromKey(source), target: refFromKey(target), position });
      }
    };
    const cancel = () => finish({ type: 'cancel' });
    const escape = event => { if (event.key === 'Escape') { event.preventDefault(); cancel(); } };
    document.addEventListener('pointermove', move, true);
    document.addEventListener('pointerup', finish, true);
    document.addEventListener('pointercancel', finish, true);
    document.addEventListener('keydown', escape, true);
    window.addEventListener('blur', cancel);
  }

  function attachHandles() {
    for (const handle of document.querySelectorAll('[data-persisted-drag-handle]')) {
      if (!handle.parentElement.hasAttribute('data-persisted-ref')) {
        handle.parentElement.style.paddingRight = '';
        handle.parentElement.style.position = '';
        handle.remove();
      }
    }
    for (const row of document.querySelectorAll('li[data-persisted-ref]')) {
      if (row.querySelector('[data-persisted-drag-handle]')) continue;
      const handle = document.createElement('button');
      handle.type = 'button';
      handle.dataset.persistedDragHandle = '';
      handle.textContent = '⠿';
      handle.title = 'Drag to reorder. Alt + Up or Down also moves this thread.';
      handle.setAttribute('aria-label', 'Reorder Persisted thread');
      Object.assign(row.style, { position: 'relative', paddingRight: '20px' });
      Object.assign(handle.style, { position: 'absolute', right: '0', top: '30px', width: '20px', height: '22px', cursor: 'grab', touchAction: 'none', color: 'var(--sidebar-muted-foreground)', background: 'transparent', border: 'none', fontSize: '18px' });
      handle.addEventListener('pointerdown', event => drag(event, row));
      handle.addEventListener('click', event => { event.preventDefault(); event.stopPropagation(); });
      handle.addEventListener('contextmenu', event => event.stopPropagation());
      handle.addEventListener('keydown', event => {
        if (!event.altKey || !['ArrowUp', 'ArrowDown'].includes(event.key)) return;
        event.preventDefault();
        event.stopPropagation();
        const rows = [...document.querySelectorAll('li[data-persisted-ref]')];
        const target = rows[rows.indexOf(row) + (event.key === 'ArrowUp' ? -1 : 1)];
        if (target) update({ type: 'move', ref: refFromKey(row.dataset.persistedRef), target: refFromKey(target.dataset.persistedRef), position: event.key === 'ArrowUp' ? 'before' : 'after' });
      });
      row.appendChild(handle);
    }
  }

  function notify(message) {
    console.error('[T3 Persisted]', message);
    let notice = document.getElementById('t3-persisted-error');
    if (!notice) {
      notice = document.createElement('div');
      notice.id = 't3-persisted-error';
      notice.setAttribute('role', 'alert');
      Object.assign(notice.style, { position: 'fixed', bottom: '20px', right: '20px', maxWidth: '360px', padding: '12px', borderRadius: '8px', background: 'var(--background)', color: 'var(--foreground)', border: '1px solid var(--border)', zIndex: '99999', fontSize: '13px' });
      document.body.appendChild(notice);
    }
    notice.textContent = 'Persisted: ' + message;
    setTimeout(() => notice.remove(), 12000);
  }

  async function update(operation) {
    try {
      // Only change visibility after the membership file was successfully written.
      publish(await bridge.update(operation));
      return true;
    } catch (error) {
      notify(error.message || String(error));
      return false;
    }
  }

  try {
    publish(disabled);
    if (bridge) {
      bridge.subscribe(publish);
      Promise.resolve(bridge.read()).then(publish).catch(error => {
        console.error('[T3 Persisted] Storage unavailable; native thread grouping retained.', error);
      });
    }
  } catch (error) {
    publish(disabled);
    console.error('[T3 Persisted] Disabled; native thread grouping retained.', error);
  }

  globalThis.__t3Persisted = {
    use: React => {
      React.useLayoutEffect(attachHandles);
      return React.useSyncExternalStore(listener => {
      listeners.add(listener);
      return () => listeners.delete(listener);
      }, () => snapshot, () => snapshot);
    },
    menu: (items, thread) => {
      if (!snapshot.enabled) return items;
      const entry = snapshot.has(thread)
        ? { id: 'persisted:remove', label: 'Remove from Persisted', icon: 'pin-off' }
        : { id: 'persisted:add', label: 'Move to Persisted', icon: 'pin' };
      const index = items.findIndex(item => item.id === 'snooze' || item.id === 'unsnooze');
      const result = [...items];
      result.splice(index < 0 ? 0 : index + 1, 0, entry);
      return result;
    },
    isAction: action => action === 'persisted:add' || action === 'persisted:remove',
    handle: (action, thread) => update({
      type: action === 'persisted:add' ? 'add' : 'remove',
      ref: { environmentId: thread.environmentId, threadId: thread.id ?? thread.threadId },
    }),
    getSnapshot: () => snapshot,
  };
})();
