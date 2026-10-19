"""Adapter for the extracted sidebar model and React Compiler builds."""
import re


def patch(source, match_one, replace_once):
    marker = source.index('snoozed-shelf-header')
    start = source.rfind('function ', 0, marker)
    end = source.find('function ', marker)
    sidebar = source[start:end]
    react = match_one(r'\(0,([\w$]+)\.useLayoutEffect\)\([\w$]+,[\w$]+\)', sidebar, 'sidebar React namespace')[1]
    header = match_one(r'^function ([\w$]+)\(\)\{let ([\w$]+)=\(0,([\w$]+)\.c\)\((\d+)\),', sidebar, 'compiled sidebar cache')
    cache = header[2]
    replacement = (f'function {header[1]}(){{let __t3PersistedState=__t3PersistedRuntime.use({react});'
                   f'let {cache}=(0,{header[3]}.c)({header[4]}),')
    sidebar = replace_once(sidebar, header[0], replacement, 'Persisted subscription')
    model = match_one(r'let\{threads:.*?sectionByThreadKey:([\w$]+),pinnedKeys:.*?\}=([\w$]+)\(([\w$]+)\)', sidebar, 'sidebar model')
    section_map, hook, argument = model.groups()
    key = match_one(r'let ([\w$]+)=([\w$]+)\(([\w$]+)\(([\w$]+).environmentId,\4.id\)\),[\w$]+=[\w$]+===`active`', sidebar, 'thread key factory')
    key_expression = f'thread=>{key[2]}({key[3]}(thread.environmentId,thread.id))'
    bound = model[0].replace('let{threads:', 'let{persistedThreads:__t3PersistedRows,threads:', 1)
    bound = bound.replace(f'{hook}({argument})', f'__t3PersistedRuntime.classify({react},{hook}({argument}),__t3PersistedState,{key_expression})')
    sidebar = replace_once(sidebar, model[0], bound, 'Persisted sidebar model')
    # Wrap the native item list before its identity/order state is initialized.
    items = match_one(r'let ([\w$]+)=([\w$]+),([\w$]+);' + re.escape(cache) + r'\[\d+\]===\1\?\3=' + re.escape(cache) + r'\[\d+\]:\(\3=\1.map\([\w$]+\)', sidebar, 'native sortable item list')
    sidebar = replace_once(sidebar, items[0], items[0].replace(f'={items[2]},', f'=__t3PersistedRuntime.items({items[2]},__t3PersistedRows,__t3PersistedState,{key_expression}),', 1), 'Persisted sortable items')
    variant = match_one(r'([\w$]+)===`active`\|\|\1===`pinned`\|\|\1===`working`\?`card`:`slim`', sidebar, 'native card variant')
    sidebar = replace_once(sidebar, variant[0], variant[1] + '===`persisted`||' + variant[0], 'Persisted full cards')
    props = match_one(r'thread:([\w$]+),variant:([\w$]+),variantAction:', sidebar, 'native row props')
    sidebar = replace_once(sidebar, props[0], props[0].replace('variantAction:', f'persistedRef:__t3PersistedState.has({props[1]})?JSON.stringify([{props[1]}.environmentId,{props[1]}.id]):void 0,variantAction:'), 'Persisted row marker')
    jsx, toggle_component = match_one(r'\(0,([\w$]+)\.jsx\)\(([\w$]+),\{onClick:[\w$]+\.toggle.onToggle,expanded:', source, 'native shelf toggle').groups()
    native_marker = match_one(r'function ([\w$]+)\(([\w$]+)\)\{(?:(?!function ).)*?\2.marker.endsWith\(`-placeholder`\)', source, 'native sortable marker', re.S)[1]
    output = match_one(r'for\(let ([\w$]+) of ([\w$]+)\)\{if\(\1.kind===`thread`\)\{([\w$]+).push\(([\w$]+)\(([\w$]+).get\(\1.key\),\1.section\)\);continue\}', sidebar, 'native row output')
    item, item_list, accumulator, row, thread_map = output.groups()
    custom = (
        f'if({item}.marker===`persisted-header`){{{accumulator}.push((0,{jsx}.jsx)({native_marker},{{marker:`persisted-header`,"data-testid":`sidebar-persisted-header`,className:`mx-0.5 h-8`,children:'
        f'(0,{jsx}.jsx)({toggle_component},{{onClick:__t3PersistedState.toggleCollapsed,expanded:!__t3PersistedState.collapsed,tone:`muted`,"data-testid":`sidebar-persisted-shelf-toggle`,children:`Persisted (${{__t3PersistedRows.length}})`}})}},`persisted-header`));continue}}'
        f'if({item}.marker===`persisted-divider`){{{accumulator}.push((0,{jsx}.jsx)({native_marker},{{marker:`persisted-divider`,"data-testid":`sidebar-persisted-end`,className:`mx-2.5 h-4 shrink-0 flex items-center`,children:(0,{jsx}.jsx)(`div`,{{className:`h-px w-full bg-sidebar-foreground/25`}})}},`persisted-divider`));continue}}'
        f'if({item}.marker===`persisted-placeholder`){{{accumulator}.push((0,{jsx}.jsx)({native_marker},{{marker:`persisted-placeholder`,className:`px-2 py-2 text-xs text-sidebar-muted-foreground`,children:`Right-click a thread to move it here.`}},`persisted-placeholder`));continue}}'
    )
    sidebar = replace_once(sidebar, output[0], output[0] + custom, 'Persisted native markers')
    menu = match_one(r'([\w$]+)=await ([\w$]+)\(\(\)=>([\w$]+)\.contextMenu.show\((([\w$]+)\(\{canOperate:.*?branch:([\w$]+)\.branch.*?snoozePresets:[\w$]+\}\)),([\w$]+)\)\);', sidebar, 'native thread menu', re.S)
    result, _, _, menu_items, _, thread, _ = menu.groups()
    replacement = menu[0].replace(f'.show({menu_items},', f'.show(__t3PersistedRuntime.menu({menu_items},{thread}),', 1)
    replacement += f'if({result}._tag!==`Failure`&&__t3PersistedRuntime.isAction({result}.value)){{await __t3PersistedRuntime.handle({result}.value,{thread});return}}'
    sidebar = replace_once(sidebar, menu[0], replacement, 'Persisted thread menu')
    selected = match_one(r'([\w$]+)\.hasSelection\(\)&&\1.selectedThreadKeys.has', sidebar, 'single selected thread menu')
    sidebar = replace_once(sidebar, selected[0], selected[0].replace('.hasSelection()', '.selectedThreadKeys.size>1'), 'single selected thread support')
    # Resolve custom targets before T3 applies its native lifecycle operations.
    drag_end = match_one(r'let ([\w$]+)=String\(([\w$]+).active.id\),([\w$]+)=' + re.escape(section_map) + r'\.get\(\1\),([\w$]+)=\2.over===null\?null:([\w$]+)\(' + re.escape(item_list) + r',\1,String\(\2.over.id\)\),([\w$]+)=' + re.escape(thread_map) + r'\.get\(\1\);if\(\3===void 0\|\|\4===null\|\|\6===void 0\)return;', sidebar, 'native drop handler')
    active, event, section, _, resolver, _ = drag_end.groups()
    sidebar = replace_once(sidebar, drag_end[0], drag_end[0] + f'if({section}===`persisted`){{__t3PersistedRuntime.drop({event},{item_list},{thread_map});return}}', 'Persisted drop persistence')
    collision = match_one(r'([\w$]+)=([\w$]+)\(([\w$]+)=>\{let ([\w$]+)=' + re.escape(resolver) + r'\(' + re.escape(item_list) + r',([\w$]+),\3\);return', sidebar, 'native collision policy')
    _, collision_factory, over, _, active_key = collision.groups()
    replacement = collision[0].replace(f'{collision_factory}(', f'{section_map}.get({active_key})===`persisted`?{collision_factory}(id=>__t3PersistedRuntime.target({resolver},{item_list},{active_key},id)!==null,{{items:{item_list}}}):{collision_factory}(', 1)
    sidebar = replace_once(sidebar, collision[0], replacement, 'Persisted collision policy')
    clamp = match_one(r'if\(([\w$]+)&&([\w$]+)\)\{let [\w$]+=[\w$]+.getBoundingClientRect\(\).*?else ([\w$]+).current=0;', sidebar, 'native drag bounds', re.S)
    drag_section = match_one(r'let ([\w$]+)=' + re.escape(section_map) + r'\.get\([\w$]+\);if\(\1===void 0\)return;', sidebar, 'native source section')[1]
    sidebar = replace_once(sidebar, clamp[0], f'if({drag_section}===`persisted`){clamp[3]}.current=0;else ' + clamp[0], 'Persisted drag bounds')
    sidebar = re.sub(re.escape(resolver) + r'\(' + re.escape(item_list) + r',([^,]+),(String\([\w$]+.over.id\)|[\w$]+)\)', lambda m: f'__t3PersistedRuntime.target({resolver},{item_list},{m[1]},{m[2]})', sidebar)
    # A custom shelf alone still counts as a populated sidebar.
    sidebar = re.sub(r'([\w$]+\.length\+[\w$]+\.length\+[\w$]+\.length\+[\w$]+\.length\+[\w$]+\.length===0)', r'__t3PersistedRows.length+\1', sidebar)
    source = source[:start] + sidebar + source[end:]
    markers = list(re.finditer(r'"data-thread-item":([\w$]+),\.\.\.', source))
    if len(markers) != 2:
        raise RuntimeError('Native thread row markers changed.')
    # Discover each memoized component's props parameter independently.
    for marker in reversed(markers):
        components = list(re.finditer(r'\(0,[\w$]+\.memo\)\(function\(([\w$]+)\)', source[:marker.start()]))
        props_name = components[-1][1]
        source = source[:marker.start()] + marker[0].replace(',...', f',"data-persisted-ref":{props_name}.persistedRef,...') + source[marker.end():]
    strategy = match_one(r'([\w$]+)\(\{items:' + re.escape(item_list) + r',enabled:', sidebar, 'native sort strategy')[1]
    a = source.index('function ' + strategy + '(')
    b = source.index('}function ', a) + 1
    body = source[a:b]
    lookup = match_one(re.escape(resolver) + r'\(([\w$]+),([\w$]+).key,([\w$]+)\(([\w$]+)\)\)', body, 'native strategy target')
    body = replace_once(body, lookup[0], f'__t3PersistedRuntime.target({resolver},{lookup[1]},{lookup[2]}.key,{lookup[3]}({lookup[4]}))', 'Persisted preview target')
    body = replace_once(body, '={pinned:[],active:[],working:[],snoozed:[],settled:[]}', '={persisted:[],pinned:[],active:[],working:[],snoozed:[],settled:[]}', 'Persisted layout group')
    body = re.sub(r'([\w$]+).section===`pinned`\|\|\1.section===`active`\|\|\1.section===`working`', lambda m: m[1] + '.section===`persisted`||' + m[0], body)
    order = match_one(r'([\w$]+).section===`pinned`\?\1.pinnedOrder:', body, 'native layout order')
    body = replace_once(body, order[0], f'{order[1]}.section===`persisted`?{order[1]}.persistedOrder:' + order[0], 'Persisted preview order')
    output = match_one(r'([\w$]+)\(`pinned-header`\),([\w$]+).push\(\.\.\.([\w$]+).pinned\)', body, 'preview layout output')
    append, result, layout = output.groups()
    items_variable = lookup[1]
    prefix = f'{items_variable}.some(e=>e.marker===`persisted-header`)&&{append}(`persisted-header`),{items_variable}.some(e=>e.marker===`persisted-placeholder`)&&{append}(`persisted-placeholder`),{result}.push(...{layout}.persisted),{items_variable}.some(e=>e.marker===`persisted-divider`)&&{append}(`persisted-divider`),'
    body = replace_once(body, output[0], prefix + output[0], 'Persisted preview placement')
    height = match_one(r'return ([\w$]+).kind===`marker`&&\(\1.marker===`pinned-header`', body, 'native marker heights')
    rect = match_one(r'([\w$]+)=[\w$]+===void 0\?void 0:[\w$]+\[[\w$]+\],[\w$]+=[\w$]+.kind===`thread`', body, 'native marker rectangle')[1]
    body = replace_once(body, height[0], f'return {height[1]}.kind===`marker`&&{height[1]}.marker.startsWith(`persisted-`)?{rect}?.height??0:' + height[0][7:], 'Persisted marker heights')
    source = source[:a] + body + source[b:]
    boundary = match_one(r'if\(([\w$]+)&&([\w$]+)&&([\w$]+)\?\.kind===`thread`&&([\w$]+)\)\{', source, 'native collision boundary')
    source = replace_once(source, boundary[0], boundary[0].replace('){', f'&&{boundary[3]}.section!==`persisted`){{'), 'Persisted boundary isolation')
    return 'const __t3PersistedRuntime=globalThis.__t3Persisted;\n' + source
