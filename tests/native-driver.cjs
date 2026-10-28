const { app, Menu } = require('electron');
const fs = require('node:fs');
const path = require('node:path');

let choice = null;
let lastMenu = [];
Menu.prototype.popup = function(options = {}) {
  lastMenu = this.items.map(item => item.label);
  const item = this.items.find(item => item.label === choice);
  choice = null;
  if (item) item.click(item, options.window, {});
  if (options.callback) options.callback();
};

let done = false;
app.on('browser-window-created', (_event, window) => {
  window.webContents.on('did-finish-load', async () => {
    if (!window.webContents.getURL().startsWith('t3code://app/') || done) return;
    done = true;
    const result = {};
    const evaluate = code => window.webContents.executeJavaScript(code);
    const animateToggle = () => evaluate(`new Promise(resolve => {
      const start=performance.now();
      document.querySelector('[data-testid=sidebar-persisted-shelf-toggle]').click();
      const list=document.querySelector('[data-testid=sidebar-persisted-header]')?.closest('ul');
      const check=()=>{
        const animations=document.getAnimations().filter(animation=>{
          const target=animation.effect?.target;
          return target && list && target.closest('ul')===list && target.closest('[data-testid=sidebar-persisted-header]')===null && animation.playState==='running';
        });
        if(animations.length)resolve(animations.map(animation=>({duration:animation.effect.getTiming().duration,easing:animation.effect.getTiming().easing})));
        else if(performance.now()-start>600)resolve([]);
        else setTimeout(check,5);
      };check();
    })`);
    const mouseDrag = async (selector, cancel = false) => {
      await wait(`(() => {
        const rows=[...document.querySelectorAll(${JSON.stringify(selector)})];
        return rows.length>=2 && rows.every(row=>{
          const card=row.querySelector('[data-testid=sidebar-row-card]');
          let fiber=card?.[Object.keys(card).find(key=>key.startsWith('__reactFiber'))];
          for(;fiber;fiber=fiber.return)if(fiber.memoizedProps?.sortable?.listeners?.onPointerDown)return true;
          return false;
        });
      })()`);
      const points = await evaluate(`(() => {
        const rows=[...document.querySelectorAll(${JSON.stringify(selector)})];
        const source=rows[1].querySelector('[data-testid=sidebar-row-card]').getBoundingClientRect();
        const target=rows[0].getBoundingClientRect();
        return {x:Math.round(source.left+source.width/2),y:Math.round(source.top+source.height/2),targetX:Math.round(target.left+target.width/2),targetY:Math.round(target.top+target.height/2)};
      })()`);
      window.webContents.sendInputEvent({type:'mouseMove',x:points.x,y:points.y});
      window.webContents.sendInputEvent({type:'mouseDown',x:points.x,y:points.y,button:'left',clickCount:1});
      await new Promise(resolve=>setTimeout(resolve,60));
      window.webContents.sendInputEvent({type:'mouseMove',x:points.targetX,y:points.targetY,modifiers:['leftButtonDown']});
      await new Promise(resolve=>setTimeout(resolve,180));
      result.dragPreview = await evaluate('[...document.querySelectorAll("li[data-thread-item]")].map(row=>({style:row.style.cssText,active:row.querySelector("[data-testid=sidebar-row-card]")?.className}))');
      if(cancel){
        window.webContents.sendInputEvent({type:'keyDown',keyCode:'Escape'});
        window.webContents.sendInputEvent({type:'keyUp',keyCode:'Escape'});
      }
      window.webContents.sendInputEvent({type:'mouseUp',x:points.targetX,y:points.targetY,button:'left',clickCount:1});
      await new Promise(resolve=>setTimeout(resolve,250));
    };
    const wait = async code => {
      for (let count = 0; count < 100; count++) {
        if (await evaluate(code)) return;
        await new Promise(resolve => setTimeout(resolve, 150));
      }
      throw new Error('Timed out: ' + code);
    };
    try {
      result.phase = process.env.T3_PERSISTED_TEST_PHASE;
      if (result.phase === 'corrupt') {
        await wait('!!document.querySelector("li[data-thread-item*=persisted-test-thread-1] [data-testid=sidebar-row-card]")');
        result.disabled = await evaluate('!globalThis.__t3Persisted.getSnapshot().enabled');
        result.nativeCards = await evaluate('document.querySelectorAll("[data-testid=sidebar-row-card]").length');
        result.headerAbsent = await evaluate('!document.querySelector("[data-testid=sidebar-persisted-header]")');
        result.ok = result.disabled && result.nativeCards === 2 && result.headerAbsent;
        fs.writeFileSync(path.join(process.env.T3_PERSISTED_TEST_OUTPUT, result.phase + '.json'), JSON.stringify(result, null, 2));
        app.quit();
        return;
      }
      await wait('!!document.querySelector("[data-testid=sidebar-persisted-shelf-toggle]")');
      result.header = await evaluate('document.querySelector("[data-testid=sidebar-persisted-shelf-toggle]").textContent');
      result.body = await evaluate('document.body.innerText.slice(0,1500)');
      if (result.phase === 'native') {
        await wait('document.querySelectorAll("li[data-thread-item] [data-testid=sidebar-row-card]").length===2');
        await new Promise(resolve=>setTimeout(resolve,250));
        const before = await evaluate('[...document.querySelectorAll("li[data-thread-item]")].map(row=>row.dataset.threadItem)');
        await mouseDrag('li[data-thread-item]');
        await wait(`document.querySelector('li[data-thread-item]')?.dataset.threadItem===${JSON.stringify(before[1])}`);
        const after = await evaluate('[...document.querySelectorAll("li[data-thread-item]")].map(row=>row.dataset.threadItem)');
        result.beforeOrder = before;
        result.afterOrder = after;
        result.nativeReordered = before[0]===after[1] && before[1]===after[0];
        result.membershipUnchanged = await evaluate('globalThis.__t3Persisted.getSnapshot().members.length===0');
        if(!result.nativeReordered || !result.membershipUnchanged) throw new Error('Native thread ordering regressed.');
      } else if (result.phase === 'add') {
        await wait('!!document.querySelector("li[data-thread-item*=persisted-test-thread-1] [data-testid=sidebar-row-card]") || !!document.querySelector("li[data-thread-item*=persisted-test-thread-1] [data-testid=sidebar-row-slim]")');
        result.nativeBefore = await evaluate('document.querySelector("li[data-thread-item*=persisted-test-thread-1] [data-testid=sidebar-row-card]").outerHTML');
        await evaluate('document.querySelector("li[data-thread-item*=persisted-test-thread-1] [data-testid=sidebar-row-card]").dispatchEvent(new MouseEvent("click",{bubbles:true,cancelable:true,ctrlKey:true}))');
        choice = 'Move to Persisted';
        await evaluate('document.querySelector("li[data-thread-item*=persisted-test-thread-1] [data-testid=sidebar-row-card]").dispatchEvent(new MouseEvent("contextmenu",{bubbles:true,cancelable:true,clientX:80,clientY:160}))');
        await wait('globalThis.__t3Persisted.getSnapshot().members.length===1');
        result.menu = lastMenu;
        result.headerAfter = await evaluate('document.querySelector("[data-testid=sidebar-persisted-shelf-toggle]").textContent');
        result.persistedCard = await evaluate('document.querySelector("li[data-thread-item*=persisted-test-thread-1] [data-testid=sidebar-row-card]").outerHTML');
        choice = 'Move to Persisted';
        await evaluate('document.querySelector("li[data-thread-item*=persisted-test-thread-2] [data-testid=sidebar-row-card]").dispatchEvent(new MouseEvent("contextmenu",{bubbles:true,cancelable:true,clientX:80,clientY:260}))');
        await wait('document.querySelectorAll("li[data-persisted-ref][data-thread-item]").length===2');
        await new Promise(resolve => setTimeout(resolve, 250));
        const coordinates = await evaluate(`(() => {
          const rows=[...document.querySelectorAll('li[data-persisted-ref][data-thread-item]')];
          const source=rows[1].querySelector('[data-testid=sidebar-row-card]').getBoundingClientRect();
          const target=rows[0].getBoundingClientRect();
          return {x:Math.round(source.left+source.width/2),y:Math.round(source.top+source.height/2),targetX:Math.round(target.left+target.width/2),targetY:Math.round(target.top+target.height/2)};
        })()`);
        window.webContents.sendInputEvent({type:'mouseMove',x:coordinates.x,y:coordinates.y});
        window.webContents.sendInputEvent({type:'mouseDown',x:coordinates.x,y:coordinates.y,button:'left',clickCount:1});
        await new Promise(resolve => setTimeout(resolve, 60));
        window.webContents.sendInputEvent({type:'mouseMove',x:coordinates.targetX,y:coordinates.targetY,modifiers:['leftButtonDown']});
        await new Promise(resolve => setTimeout(resolve, 180));
        result.nativePreview = await evaluate('[...document.querySelectorAll("li[data-persisted-ref][data-thread-item]")].some(row=>row.style.transform.includes("translate"))');
        result.notSavedUntilDrop = await evaluate('globalThis.__t3Persisted.getSnapshot().members[0].threadId==="persisted-test-thread-1"');
        if (!result.nativePreview || !result.notSavedUntilDrop) throw new Error('Native drag preview did not move cards before committing the drop.');
        window.webContents.sendInputEvent({type:'mouseUp',x:coordinates.targetX,y:coordinates.targetY,button:'left',clickCount:1});
        await wait('globalThis.__t3Persisted.getSnapshot().members[0].threadId==="persisted-test-thread-2"');
        result.dragReordered = await evaluate('JSON.parse(document.querySelector("li[data-persisted-ref][data-thread-item]").dataset.persistedRef)[1]==="persisted-test-thread-2"');
        if (!result.dragReordered) throw new Error('Drag saved order but did not reorder native cards.');
        result.collapseAnimations = await animateToggle();
        if (!result.collapseAnimations.length) throw new Error('Persisted collapse did not use the native row animator.');
        await wait('globalThis.__t3Persisted.getSnapshot().collapsed');
        result.collapsedHidesCard = await evaluate('!document.querySelector("li[data-thread-item*=persisted-test-thread-1] [data-testid=sidebar-row-card]")');
      } else if (result.phase === 'restart') {
        result.membershipSurvived = await evaluate('globalThis.__t3Persisted.getSnapshot().members.length===2');
        result.collapseSurvived = await evaluate('globalThis.__t3Persisted.getSnapshot().collapsed');
        result.expandAnimations = await animateToggle();
        if (!result.expandAnimations.length) throw new Error('Persisted expansion did not use the native row animator.');
        await wait('!!document.querySelector("li[data-thread-item*=persisted-test-thread-1] [data-testid=sidebar-row-card]")');
        result.rowCount = await evaluate('document.querySelectorAll("li[data-thread-item*=persisted-test-thread-1] [data-testid=sidebar-row-card]").length');
        result.top = await evaluate('document.querySelector("[data-testid=sidebar-persisted-header]").parentElement.firstElementChild.dataset.testid');
        result.orderSurvived = await evaluate('JSON.parse(document.querySelector("li[data-persisted-ref][data-thread-item]").dataset.persistedRef)[1]==="persisted-test-thread-2"');
        if (!result.membershipSurvived || !result.orderSurvived) throw new Error('Manual order did not survive restart.');
        result.noCustomGrip = await evaluate('!document.querySelector("[data-persisted-drag-handle]")');
        if (!result.noCustomGrip) throw new Error('Custom drag grip remained.');
        await new Promise(resolve=>setTimeout(resolve,250));
        await mouseDrag('li[data-persisted-ref][data-thread-item]', true);
        result.cancelPreservedOrder = await evaluate('globalThis.__t3Persisted.getSnapshot().members[0].threadId==="persisted-test-thread-2" && JSON.parse(document.querySelector("li[data-persisted-ref][data-thread-item]").dataset.persistedRef)[1]==="persisted-test-thread-2"');
        if (!result.cancelPreservedOrder) throw new Error('Escape changed the saved order.');
        const image = await window.webContents.capturePage();
        fs.writeFileSync(path.join(process.env.T3_PERSISTED_TEST_OUTPUT, 'persisted.png'), image.toPNG());
        choice = 'Remove from Persisted';
        await evaluate('document.querySelector("li[data-thread-item*=persisted-test-thread-1] [data-testid=sidebar-row-card]").dispatchEvent(new MouseEvent("contextmenu",{bubbles:true,cancelable:true,clientX:80,clientY:160}))');
        await wait('globalThis.__t3Persisted.getSnapshot().members.length===1');
        result.removeMenu = lastMenu;
        result.restoredNativeCard = await evaluate('!!document.querySelector("li[data-thread-item*=persisted-test-thread-1] [data-testid=sidebar-row-card]")');
      }
      result.ok = true;
    } catch (error) {
      result.error = String(error);
      result.body = await evaluate('document.body.innerText.slice(0,2000)').catch(() => 'unavailable');
      result.testIds = await evaluate('Array.from(document.querySelectorAll("[data-testid]")).map(e=>e.dataset.testid)').catch(() => []);
    }
    fs.writeFileSync(path.join(process.env.T3_PERSISTED_TEST_OUTPUT, result.phase + '.json'), JSON.stringify(result, null, 2));
    app.quit();
  });
});
