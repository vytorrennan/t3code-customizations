(() => {
  const bridge = globalThis.t3PersistedBridge;
  const listeners = new Set();
  const pruning = new Set();
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

  // Use the native sidebar's array-move target semantics within this shelf.
  // Native groups retain their original target resolver and database operations.
  function target(nativeTarget, items, active, over) {
    const source = items.find(item => item.kind === 'thread' && item.key === active);
    const destination = items.find(item => item.kind === 'thread' && item.key === over);
    if (source?.section === 'persisted') {
      if (destination?.section !== 'persisted') return null;
      const order = items.filter(item => item.kind === 'thread' && item.section === 'persisted').map(item => item.key);
      const from = order.indexOf(active), to = order.indexOf(over);
      order.splice(to, 0, ...order.splice(from, 1));
      return { section: 'persisted', persistedOrder: order };
    }
    if (destination?.section === 'persisted' || items.some(item => item.marker?.startsWith('persisted-') && over === 'sidebar-marker-' + item.marker)) return null;
    return nativeTarget(items.filter(item => item.section !== 'persisted' && !item.marker?.startsWith('persisted-')), active, over);
  }

  function drop(event, items, threads) {
    const active = String(event.active.id), over = event.over && String(event.over.id);
    const source = threads.get(active), destination = threads.get(over);
    const rows = items.filter(item => item.kind === 'thread' && item.section === 'persisted');
    const from = rows.findIndex(item => item.key === active), to = rows.findIndex(item => item.key === over);
    if (!source || !destination || from < 0 || to < 0 || from === to) return;
    const ref = { environmentId: source.environmentId, threadId: source.id };
    const target = { environmentId: destination.environmentId, threadId: destination.id };
    const position = from < to ? 'after' : 'before';
    const previous = snapshot;
    const members = previous.members.filter(member => key(member) !== key(ref));
    const index = members.findIndex(member => key(member) === key(target));
    if (index >= 0) {
      const moved = previous.members.find(member => key(member) === key(ref));
      members.splice(position === 'after' ? index + 1 : index, 0, moved);
      publish({ ...previous, members });
    }
    return update({ type: 'move', ref, target, position }, previous);
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

  async function update(operation, rollback) {
    try {
      // Only change visibility after the membership file was successfully written.
      publish(await bridge.update(operation));
      return true;
    } catch (error) {
      if (rollback) publish(rollback);
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
    classify: (React, native, state, threadKey) => React.useMemo(() => {
      const members = state.sort(native.searchableThreads.filter(thread => {
        if (!state.has(thread)) return false;
        if (thread.settledOverride === 'settled') {
          globalThis.__t3Persisted.prune(thread);
          return false;
        }
        return true;
      }));
      const keys = new Set(members.map(threadKey));
      const result = { ...native, persistedThreads: members };
      for (const field of ['pinnedThreads', 'activeThreads', 'workingThreads', 'snoozedThreads', 'settledThreads', 'renderedSettledThreads', 'visibleSnoozedThreads', 'visibleWorkingThreads']) {
        result[field] = native[field].filter(thread => !keys.has(threadKey(thread)));
      }
      result.threadByKey = new Map(native.threadByKey);
      result.sectionByThreadKey = new Map(native.sectionByThreadKey);
      result.draggableThreadKeys = new Set(native.draggableThreadKeys);
      for (const thread of members) {
        const key = threadKey(thread);
        result.threadByKey.set(key, thread);
        result.sectionByThreadKey.set(key, 'persisted');
        result.draggableThreadKeys.add(key);
      }
      result.orderedThreadKeys = [...(state.collapsed ? [] : members.map(threadKey)), ...native.orderedThreadKeys.filter(key => !keys.has(key))];
      for (const field of ['pinnedKeys', 'activeKeys']) result[field] = native[field].filter(key => !keys.has(key));
      for (const field of ['pinnedKeysById', 'activeKeysById', 'settledThreadKeys', 'snoozedThreadKeys']) {
        result[field] = new native[field].constructor([...native[field]].filter(entry => !keys.has(Array.isArray(entry) ? entry[0] : entry)));
      }
      return result;
    }, [native, state]),
    items: (native, members, state, threadKey) => !state.enabled ? native : [
      { kind: 'marker', marker: 'persisted-header' },
      ...(state.collapsed ? [] : [
        ...(members.length ? members.map(thread => ({ kind: 'thread', key: threadKey(thread), section: 'persisted' })) : [{ kind: 'marker', marker: 'persisted-placeholder' }]),
        { kind: 'marker', marker: 'persisted-divider' },
      ]),
      ...native,
    ],
    use: React => React.useSyncExternalStore(listener => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    }, () => snapshot, () => snapshot),
    target,
    wrap: nativeTarget => (items, active, over) => target(nativeTarget, items, active, over),
    drop,
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
    prune: thread => {
      const ref = { environmentId: thread.environmentId, threadId: thread.id ?? thread.threadId };
      const id = key(ref);
      if (pruning.has(id)) return;
      pruning.add(id);
      queueMicrotask(() => update({ type: 'remove', ref }).finally(() => pruning.delete(id)));
    },
  };
})();
