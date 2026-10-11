(() => {
  const bridge = globalThis.t3PersistedBridge;
  const listeners = new Set();
  const disabled = { enabled: false, version: 1, collapsed: false, members: [] };
  let snapshot;
  const key = ref => JSON.stringify([ref.environmentId, ref.threadId ?? ref.id]);

  function publish(value) {
    const keys = new Set(value.members.map(key));
    snapshot = {
      ...value,
      has: thread => value.enabled && keys.has(key(thread)),
      toggleCollapsed: () => update({ type: 'collapse', collapsed: !snapshot.collapsed }),
    };
    for (const listener of listeners) listener();
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
    use: React => React.useSyncExternalStore(listener => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    }, () => snapshot, () => snapshot),
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
