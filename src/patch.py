#!/usr/bin/env python3
"""Generate an overlay from the installed nightly. Never modify /opt or thread data."""
import argparse
import hashlib
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
ADAPTER_VERSION = 4


class UnsupportedBuild(RuntimeError):
    pass


def replace_once(text, old, new, description):
    if text.count(old) != 1:
        raise UnsupportedBuild(f'{description}: expected one integration point, found {text.count(old)}')
    return text.replace(old, new, 1)


def match_one(pattern, text, description, flags=0):
    matches = list(re.finditer(pattern, text, flags))
    if len(matches) != 1:
        raise UnsupportedBuild(f'{description}: expected one integration point, found {len(matches)}')
    return matches[0]


def patch_sidebar(source):
    # Locate the sidebar through semantic field names; hashed filenames and local
    # minifier identifiers are discovered from the installed build each time.
    marker = source.find('snoozed-shelf-header')
    if marker < 0:
        raise UnsupportedBuild('The native sidebar shelf renderer was not found.')
    start = source.rfind('function ', 0, marker)
    end = source.find('function ', marker)
    if start < 0 or end < 0:
        raise UnsupportedBuild('The sidebar function boundaries changed.')
    sidebar = source[start:end]
    header = match_one(r'^function ([\w$]+)\(\)\{', sidebar, 'sidebar function')
    groups = match_one(r'\{pinnedThreads:([\w$]+),draggableThreadKeys:([\w$]+),activeReorderableThreadKeys:([\w$]+),activeThreads:([\w$]+),workingThreads:([\w$]+),snoozedThreads:([\w$]+),settledThreads:([\w$]+),snoozeNow:([\w$]+)\}=\(0,([\w$]+)\.useMemo\)', sidebar, 'thread classifier')
    pinned, draggable, _, active, working, snoozed, settled, _, react = groups.groups()
    sidebar = replace_once(sidebar, header[0], header[0] + f'let __t3PersistedState=__t3PersistedRuntime.use({react});', 'Persisted subscription')
    sidebar = replace_once(sidebar, groups[0], groups[0].replace('{pinnedThreads:', '{persistedThreads:__t3PersistedRows,pinnedThreads:', 1), 'Persisted rows binding')
    classifier = match_one(r'\(0,' + re.escape(react) + r'\.useMemo\)\(\(\)=>\{let ([\w$]+)=new Date\(\)\.toISOString\(\),', sidebar, 'classification initialization')
    sidebar = replace_once(sidebar, classifier[0], classifier[0].replace('()=>{', '()=>{let __t3PersistedMembers=[];', 1), 'classification storage')
    loop = match_one(r'for\(let ([\w$]+) of ([\w$]+)\)\{let ([\w$]+)=([\w$]+)\.get\(\1.environmentId\)\?\.environment.capabilities', sidebar, 'classification loop')
    thread = loop[1]
    sidebar = replace_once(sidebar, loop[0], loop[0].replace('{let ', '{if(__t3PersistedState.has(' + thread + ')){if(' + thread + '.settledOverride===`settled`)__t3PersistedRuntime.prune?.(' + thread + ');else{__t3PersistedMembers.push(' + thread + ');continue}}let ', 1), 'membership grouping')
    classifier_return = match_one(r'return\{pinnedThreads:', sidebar, 'classification result')
    sidebar = replace_once(sidebar, classifier_return[0], 'return{persistedThreads:__t3PersistedState.sort(__t3PersistedMembers),pinnedThreads:', 'classification result')
    dependencies = match_one(r'snoozeNow:[\w$]+\}\},\[([^\]]+)\]\)', sidebar, 'classification dependencies')
    sidebar = replace_once(sidebar, dependencies[0], dependencies[0].replace('},[', '},[__t3PersistedState,', 1), 'membership invalidation')

    # Search sees every Persisted member even while its shelf is collapsed.
    all_rows = match_one(r'\(\)=>\[\.\.\.' + re.escape(pinned) + r',\.\.\.' + re.escape(active) + r',\.\.\.' + re.escape(working) + r',\.\.\.' + re.escape(snoozed) + r',\.\.\.' + re.escape(settled) + r'\],\[([^\]]+)\]', sidebar, 'all searchable rows')
    sidebar = replace_once(sidebar, all_rows[0], all_rows[0].replace('()=>[', '()=>[...__t3PersistedRows,', 1).replace('],[', '],[__t3PersistedRows,', 1), 'Persisted search')
    visible = match_one(r'\(\)=>\[\.\.\.' + re.escape(pinned) + r',\.\.\.' + re.escape(active) + r',\.\.\.([\w$]+),\.\.\.([\w$]+),\.\.\.([\w$]+)\],\[([^\]]+)\]', sidebar, 'visible navigation rows')
    sidebar = replace_once(sidebar, visible[0], visible[0].replace('()=>[', '()=>[...(__t3PersistedState.collapsed?[]:__t3PersistedRows),', 1).replace('],[', '],[__t3PersistedRows,__t3PersistedState.collapsed,', 1), 'Persisted keyboard navigation')

    # The native shelf animator snapshots direct list children in a layout
    # effect. Persisted changes must trigger that effect, including when it is
    # the only nonempty group. Reuse native timing and reduced-motion handling.
    animation = match_one(r'([\w$]+)=([\w$]+)\.length\+([\w$]+)>0;\(0,' + re.escape(react) + r'\.useLayoutEffect\)\(\(\)=>\{([\w$]+)\.current\?\.update\(!([\w$]+)&&\1\)\},\[([^\]]+)\]\)', sidebar, 'native shelf animation effect')
    animated = animation[0].replace('>0;', '+__t3PersistedRows.length>0;', 1).replace('},[', '},[__t3PersistedState.collapsed,__t3PersistedState.enabled,__t3PersistedRows,', 1)
    sidebar = replace_once(sidebar, animation[0], animated, 'Persisted native animation invalidation')

    variant = match_one(r'([\w$]+)===`active`\|\|\1===`pinned`\|\|\1===`working`\?`card`:`slim`', sidebar, 'full native card variant')
    sidebar = replace_once(sidebar, variant[0], variant[1] + '===`persisted`||' + variant[0], 'full Persisted cards')
    renderer = match_one(r'let ([\w$]+)=\(([\w$]+),([\w$]+),([\w$]+)\)=>\{let [\w$]+=[\w$]+\([\w$]+\(\2.environmentId,\2.id\)\),[\w$]+=\3===`persisted`', sidebar, 'native row factory')[1]
    toggle = match_one(r'\(0,([\w$]+)\.jsx\)\(([\w$]+),\{onClick:[\w$]+\.toggle.onToggle,expanded:[\w$]+\.toggle.expanded', source, 'native shelf toggle')
    jsx, toggle_component = toggle.groups()
    output = match_one(r'([\w$]+)=\[\(0,' + re.escape(jsx) + r'\.jsx\)\([\w$]+,\{projectByKey:.*?`draft-sessions`\)\];for\(let', sidebar, 'sidebar output', re.S)
    accumulator = output[1]
    persisted_header = (
        f'(0,{jsx}.jsx)(`li`,{{className:`mx-0.5 h-8 list-none`,"data-testid":`sidebar-persisted-header`,children:'
        f'(0,{jsx}.jsx)({toggle_component},{{onClick:__t3PersistedState.toggleCollapsed,expanded:!__t3PersistedState.collapsed,tone:`muted`,'
        f'"data-testid":`sidebar-persisted-shelf-toggle`,children:`Persisted (${{__t3PersistedRows.length}})`}})}},`persisted-header`)'
    )
    empty = f'(0,{jsx}.jsx)(`li`,{{className:`list-none px-2 py-2 text-xs text-sidebar-muted-foreground`,children:`Right-click a thread to move it here.`}},`persisted-empty`)'
    sortable = match_one(r'([\w$]+)=\(([\w$]+),([\w$]+)\)=>\{let ([\w$]+)=[\w$]+\([\w$]+\(\2.environmentId,\2.id\)\);return\(0,' + re.escape(jsx) + r'\.jsx\)\(([\w$]+),\{id:\4,contextDrag:', sidebar, 'native sortable row factory')
    sortable_factory, _, section, sortable_key, _ = sortable.groups()
    disabled = f'||!{draggable}.has({sortable_key})'
    sidebar = replace_once(sidebar, disabled, f'||{section}!==`persisted`&&!{draggable}.has({sortable_key})', 'Persisted native dragging')
    marker_component = match_one(r'function ([\w$]+)\(([\w$]+)\)\{(?:(?!function ).)*?\2.marker.endsWith\(`-placeholder`\)', source, 'native sortable marker', re.S)[1]
    empty = empty.replace('(`li`,{', f'({marker_component},{{marker:`persisted-placeholder`,', 1)
    persisted_header = persisted_header.replace('(`li`,{', f'({marker_component},{{marker:`persisted-header`,', 1)
    # Keep the separator spacing inside its measured sortable rectangle.
    divider = f'(0,{jsx}.jsx)({marker_component},{{marker:`persisted-divider`,"data-testid":`sidebar-persisted-end`,className:`mx-2.5 h-4 shrink-0 list-none flex items-center`,children:(0,{jsx}.jsx)(`div`,{{className:`h-px w-full bg-sidebar-foreground/25`}})}},`persisted-end`)'
    insertion = f'];if(__t3PersistedState.enabled){{{accumulator}.unshift({persisted_header},...(__t3PersistedState.collapsed?[]:[...(__t3PersistedRows.length?__t3PersistedRows.map(thread=>{sortable_factory}(thread,`persisted`)):[{empty}]),{divider}]))}}for(let'
    sidebar = replace_once(sidebar, output[0], output[0].replace('];for(let', insertion, 1), 'Persisted shelf at top')
    sidebar, source = patch_native_drag(sidebar, source, react, pinned)

    menu = match_one(r'([\w$]+)=await ([\w$]+)\(\(\)=>([\w$]+)\.contextMenu.show\((([\w$]+)\(\{canOperate:.*?branch:([\w$]+)\.branch.*?snoozePresets:[\w$]+\}\)),([\w$]+)\)\);', sidebar, 'single-thread native menu', re.S)
    result, attempt, platform, items, builder, menu_thread, position = menu.groups()
    replaced_menu = menu[0].replace(f'.show({items},', f'.show(__t3PersistedRuntime.menu({items},{menu_thread}),', 1)
    replaced_menu += f'if({result}._tag!==`Failure`&&__t3PersistedRuntime.isAction({result}.value)){{await __t3PersistedRuntime.handle({result}.value,{menu_thread});return}}'
    sidebar = replace_once(sidebar, menu[0], replaced_menu, 'Persisted native menu action')
    selection = match_one(r'if\(([\w$]+)\.hasSelection\(\)&&\1.selectedThreadKeys.has\(([\w$]+)\)\)\{await ([\w$]+)\(([\w$]+)\);return\}', sidebar, 'single selected thread menu')
    sidebar = replace_once(sidebar, selection[0], selection[0].replace('.hasSelection()', '.selectedThreadKeys.size>1', 1), 'single selected thread support')
    empty_guard = f'{pinned}.length+{active}.length+{working}.length+{snoozed}.length+{settled}.length===0?'
    if empty_guard in sidebar:
        sidebar = replace_once(sidebar, empty_guard, '__t3PersistedRows.length+' + empty_guard, 'empty sidebar message')
    # Mark the native list item without changing its structure or animation keys.
    native_row = match_one(r'let [\w$]+=\([\w$]+,[\w$]+,[\w$]+\)=>.*?return\(0,[\w$]+\.jsx\)\(([\w$]+),\{thread:([\w$]+),variant:([\w$]+),', sidebar, 'native row props', re.S)
    sidebar = replace_once(sidebar, native_row[0], native_row[0] + f'persistedRef:{native_row[3]}===`card`&&__t3PersistedState.has({native_row[2]})?JSON.stringify([{native_row[2]}.environmentId,{native_row[2]}.id]):void 0,', 'Persisted row marker prop')
    start = source.index('function ' + header[1] + '(){')
    end = source.find('function ', source.index('snoozed-shelf-header', start))
    source = source[:start] + sidebar + source[end:]
    row_props = match_one(re.escape(native_row[1]) + r'=\(0,[\w$]+\.memo\)\(function\(([\w$]+)\)', source, 'native row component props')[1]
    markers = list(re.finditer(r'"data-thread-item":([\w$]+),\.\.\.', source))
    if len(markers) != 2:
        raise UnsupportedBuild('Native card list item markers changed.')
    source = re.sub(r'"data-thread-item":([\w$]+),\.\.\.', r'"data-thread-item":\1,"data-persisted-ref":' + row_props + '.persistedRef,...', source)
    fallback = ('const __t3PersistedDisabled={enabled:false,collapsed:false,members:[],has:()=>false,sort:rows=>rows};'
                'const __t3PersistedRuntime=globalThis.__t3Persisted??{use:()=>__t3PersistedDisabled,menu:items=>items,isAction:()=>false,target:(native,items,active,over)=>native(items,active,over)};\n')
    return fallback + source


def patch_native_drag(sidebar, source, react, pinned):
    section_map = match_one(r'([\w$]+)=\(0,' + re.escape(react) + r'\.useMemo\)\(\(\)=>\{let ([\w$]+)=new Map,([\w$]+)=\([\w$]+,[\w$]+\)=>.*?return \3\(' + re.escape(pinned) + r',`pinned`\).*?\},\[([^\]]+)\]\)', sidebar, 'native drag section map', re.S)
    map_name, _, add, _ = section_map.groups()
    replacement = section_map[0].replace('return ', f'return {add}(__t3PersistedRows,`persisted`),', 1).replace('},[', '},[__t3PersistedRows,', 1)
    sidebar = replace_once(sidebar, section_map[0], replacement, 'Persisted drag section')
    items = match_one(r'([\w$]+)=\(0,' + re.escape(react) + r'\.useMemo\)\(\(\)=>\{let ([\w$]+)=\([\w$]+,[\w$]+\)=>[\w$]+.map\([\w$]+=>\(\{kind:`thread`,key:.*?\},\[([^\]]+)\]\)', sidebar, 'native sortable items', re.S)
    item_name, make_items, _ = items.groups()
    replacement = items[0].replace(f'if({pinned}.length+', f'if(__t3PersistedRows.length+{pinned}.length+', 1)
    replacement = replacement.replace('let t=[{kind:`marker`,marker:`pinned-header`}]', f'let t=[...(__t3PersistedState.enabled?[{{kind:`marker`,marker:`persisted-header`}},...(__t3PersistedState.collapsed?[]:[...(__t3PersistedRows.length?{make_items}(__t3PersistedRows,`persisted`):[{{kind:`marker`,marker:`persisted-placeholder`}}]),{{kind:`marker`,marker:`persisted-divider`}}])]:[]),{{kind:`marker`,marker:`pinned-header`}}]')
    if replacement == items[0] or 'marker:`persisted-header`' not in replacement:
        raise UnsupportedBuild('Native sortable item list changed.')
    replacement = replacement.replace('},[', '},[__t3PersistedRows,__t3PersistedState.collapsed,__t3PersistedState.enabled,', 1)
    sidebar = replace_once(sidebar, items[0], replacement, 'Persisted sortable items')
    row_loop = f'for(let e of {item_name}){{if(e.kind===`thread`){{'
    sidebar = replace_once(sidebar, row_loop, row_loop + 'if(e.section===`persisted`)continue;', 'Persisted rows rendered once')
    # The sensor otherwise clamps cards below the Pinned heading.
    clamp = match_one(r'if\(([\w$]+)&&([\w$]+)\)\{let [\w$]+=[\w$]+.getBoundingClientRect\(\).*?else ([\w$]+).current=0;', sidebar, 'native drag upper boundary', re.S)
    section = match_one(r'let ([\w$]+)=' + re.escape(map_name) + r'\.get\([\w$]+\);if\(\1===void 0\)return;', sidebar, 'native drag source section')[1]
    sidebar = replace_once(sidebar, clamp[0], f'if({section}===`persisted`){clamp[3]}.current=0;else ' + clamp[0], 'Persisted drag bounds')
    collision = match_one(r'return ([\w$]+)===void 0\?([\w$]+)\(\(\)=>!1\):\2\([\w$]+=>\{let ([\w$]+)=([\w$]+)\(' + re.escape(item_name) + r',([\w$]+),[\w$]+\);', sidebar, 'native collision policy')
    thread, collision_factory, target, resolver, active_key = collision.groups()
    source_section = match_one(r'if\([\w$]+===void 0\|\|([\w$]+)===void 0\)return ' + re.escape(collision_factory), sidebar, 'native collision source section')[1]
    allowed = f'if({source_section}===`persisted`)return {collision_factory}(id=>__t3PersistedRuntime.target({resolver},{item_name},{active_key},id)!==null,{{items:{item_name}}});'
    sidebar = replace_once(sidebar, collision[0], allowed + collision[0], 'Persisted collision policy')
    drag_end = match_one(r'let ([\w$]+)=String\([\w$]+.active.id\),([\w$]+)=' + re.escape(map_name) + r'\.get\(\1\),([\w$]+)=[\w$]+.over===null\?null:' + resolver + r'\(' + re.escape(item_name) + r',\1,String\([\w$]+.over.id\)\),([\w$]+)=([\w$]+)\.get\(\1\);if\(\2===void 0\|\|\3===null\|\|\4===void 0\)return;', sidebar, 'native drop handler')
    active_id, section, _, _, thread_map = drag_end.groups()
    event = match_one(r'let [\w$]+=String\(([\w$]+).active.id\),' + re.escape(section) + '=' + re.escape(map_name), drag_end[0], 'native drop event')[1]
    sidebar = replace_once(sidebar, drag_end[0], drag_end[0] + f'if({section}===`persisted`){{__t3PersistedRuntime.drop({event},{item_name},{thread_map});return}}', 'Persisted drop persistence')
    # All target lookups use the native resolver outside the custom shelf.
    calls = list(re.finditer(re.escape(resolver) + r'\(' + re.escape(item_name) + r',([^,]+),(String\([\w$]+.over.id\)|[\w$]+)\)', sidebar))
    if len(calls) != 3:
        raise UnsupportedBuild('Native sidebar target lookups changed.')
    sidebar = re.sub(re.escape(resolver) + r'\(' + re.escape(item_name) + r',([^,]+),(String\([\w$]+.over.id\)|[\w$]+)\)', lambda m: f'__t3PersistedRuntime.target({resolver},{item_name},{m[1]},{m[2]})', sidebar)

    strategy = match_one(r'\(\)=>(([\w$]+)\(\{items:' + re.escape(item_name) + r',enabled:)', sidebar, 'native sort strategy')[2]
    strategy_start = source.index('function ' + strategy + '(')
    strategy_end = source.index('}function ', strategy_start) + 1
    body = source[strategy_start:strategy_end]
    lookup = match_one(re.escape(resolver) + r'\(([\w$]+),([\w$]+).key,([\w$]+)\(([\w$]+)\)\)', body, 'native strategy target')
    body = replace_once(body, lookup[0], f'__t3PersistedRuntime.target({resolver},{lookup[1]},{lookup[2]}.key,{lookup[3]}({lookup[4]}))', 'Persisted strategy target')
    body = replace_once(body, '={pinned:[],active:[],working:[],snoozed:[],settled:[]}', '={persisted:[],pinned:[],active:[],working:[],snoozed:[],settled:[]}', 'Persisted layout group')
    cards = list(re.finditer(r'([\w$]+).section===`pinned`\|\|\1.section===`active`\|\|\1.section===`working`', body))
    if len(cards) != 2:
        raise UnsupportedBuild('Native card height classifications changed.')
    body = re.sub(r'([\w$]+).section===`pinned`\|\|\1.section===`active`\|\|\1.section===`working`', lambda m: m[1] + '.section===`persisted`||' + m[0], body)
    order = match_one(r'([\w$]+).section===`pinned`\?\1.pinnedOrder:', body, 'native layout order')
    body = replace_once(body, order[0], f'{order[1]}.section===`persisted`?{order[1]}.persistedOrder:' + order[0], 'Persisted preview order')
    output = match_one(r'([\w$]+)\(`pinned-header`\),([\w$]+).push\(\.\.\.([\w$]+).pinned\)', body, 'native preview layout output')
    append_marker, result, layout = output.groups()
    items_variable = lookup[1]
    prefix = f'{items_variable}.some(e=>e.marker===`persisted-header`)&&{append_marker}(`persisted-header`),{items_variable}.some(e=>e.marker===`persisted-placeholder`)&&{append_marker}(`persisted-placeholder`),{result}.push(...{layout}.persisted),{items_variable}.some(e=>e.marker===`persisted-divider`)&&{append_marker}(`persisted-divider`),'
    body = replace_once(body, output[0], prefix + output[0], 'Persisted preview placement')
    marker_height = match_one(r'return ([\w$]+).kind===`marker`&&\(\1.marker===`pinned-header`', body, 'native marker heights')
    marker = marker_height[1]
    original_rect = match_one(r'([\w$]+)=[\w$]+===void 0\?void 0:[\w$]+\[[\w$]+\],[\w$]+=[\w$]+.kind===`thread`', body, 'native marker rectangle')[1]
    body = replace_once(body, marker_height[0], f'return {marker}.kind===`marker`&&{marker}.marker.startsWith(`persisted-`)?{original_rect}?.height??0:' + marker_height[0][7:], 'Persisted measured marker heights')
    source = source[:strategy_start] + body + source[strategy_end:]
    # Skip the native Pinned/Active boundary preference for custom shelf drags.
    boundary = match_one(r'if\(([\w$]+)&&([\w$]+)&&([\w$]+)\?\.kind===`thread`&&([\w$]+)\)\{', source, 'native collision boundary preference')
    source = replace_once(source, boundary[0], boundary[0].replace('){', f'&&{boundary[3]}.section!==`persisted`){{'), 'Persisted collision boundary isolation')
    cached_target = match_one(re.escape(resolver) + r'\(([\w$]+),String\(([\w$]+).active.id\),([\w$]+)\)\?\.section', source, 'native cached collision section')
    source = replace_once(source, cached_target[0], f'__t3PersistedRuntime.target({resolver},{cached_target[1]},String({cached_target[2]}.active.id),{cached_target[3]})?.section', 'Persisted cached collision isolation')
    return sidebar, source


class Archive:
    def __init__(self, file):
        self.file = Path(file)
        with self.file.open('rb') as stream:
            _, size, _, length = struct.unpack('<4I', stream.read(16))
            self.header = json.loads(stream.read(length))
        self.base = 8 + size
        self.entries = {}
        def walk(node, prefix=''):
            for name, value in node.get('files', {}).items():
                location = prefix + '/' + name if prefix else name
                if 'files' in value:
                    walk(value, location)
                else:
                    self.entries[location] = value
        walk(self.header)

    def read(self, name):
        value = self.entries[name]
        with self.file.open('rb') as stream:
            stream.seek(self.base + int(value['offset']))
            return stream.read(value['size'])

    def write(self, destination, changes):
        offset = 0
        originals = {}
        for name, value in self.entries.items():
            if 'offset' not in value:
                continue
            originals[name] = (int(value['offset']), value['size'])
            value['offset'] = str(offset)
            if name in changes:
                data = changes[name]
                value['size'] = len(data)
                block_size = value.get('integrity', {}).get('blockSize', 4194304)
                value['integrity'] = {'algorithm': 'SHA256', 'hash': hashlib.sha256(data).hexdigest(), 'blockSize': block_size,
                                      'blocks': [hashlib.sha256(data[i:i+block_size]).hexdigest() for i in range(0, len(data), block_size)]}
            offset += value['size']
        header = json.dumps(self.header, separators=(',', ':')).encode()
        padding = (-len(header)) % 4
        size = len(header) + padding + 8
        with self.file.open('rb') as source, Path(destination).open('wb') as output:
            output.write(struct.pack('<4I', 4, size, size - 4, len(header)))
            output.write(header)
            output.write(b'\0' * padding)
            for name, (old_offset, old_size) in originals.items():
                if name in changes:
                    output.write(changes[name])
                else:
                    source.seek(self.base + old_offset)
                    output.write(source.read(old_size))


def signature(source):
    files = [source / 'resources/app.asar', source / 't3code'] + sorted((ROOT / 'src').glob('*'))
    return {'adapter': ADAPTER_VERSION, 'inputs': {str(file): [file.stat().st_mtime_ns, file.stat().st_size] for file in files if file.is_file()}}


def prepare(source, destination):
    source, destination = Path(source).resolve(), Path(destination)
    expected = signature(source)
    marker = destination / 'persisted-build.json'
    if marker.exists() and json.loads(marker.read_text()) == expected:
        return destination / 't3code'
    binary = (source / 't3code').read_bytes()
    sentinel = b'dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX'
    at = binary.find(sentinel)
    if at < 0:
        raise UnsupportedBuild('Cannot verify Electron archive integrity settings.')
    wire = binary[at+len(sentinel):at+len(sentinel)+20]
    if wire[0] != 1 or wire[1] < 6 or wire[2+4:2+5] != b'0':
        raise UnsupportedBuild('This nightly enforces embedded archive integrity; overlay generation is disabled.')

    archive = Archive(source / 'resources/app.asar')
    installed_version = json.loads(archive.read('package.json'))['version']
    main_candidates = [name for name in archive.entries if re.fullmatch(r'apps/server/dist/client/assets/main-[^/]+\.js', name)]
    if len(main_candidates) != 1:
        raise UnsupportedBuild('Cannot identify the main UI bundle.')
    main = main_candidates[0]
    main_source = patch_sidebar(archive.read(main).decode())
    boot = 'apps/desktop/dist-electron/boot.cjs'
    preload = 'apps/desktop/dist-electron/preload.cjs'
    electron_main = 'apps/desktop/dist-electron/main.cjs'
    html = 'apps/server/dist/client/index.html'
    loader_path = json.dumps(str(ROOT / 'src/loader.cjs'))
    boot_source = f'try{{require({loader_path})}}catch(error){{console.error("[T3 Persisted] Loader disabled",error)}}\n' + archive.read(boot).decode()
    preload_source = archive.read(preload).decode() + '\ntry {\n' + (ROOT / 'src/preload.cjs').read_text() + '\n} catch(error) { console.error("[T3 Persisted] Bridge disabled", error); }\n'
    html_source = archive.read(html).decode()
    keypad = (ROOT / 'src/terminal-keypad.js').read_text()
    runtime = (ROOT / 'src/renderer.js').read_text()
    runtime = keypad + '\n' + runtime
    html_source = replace_once(html_source, '<head>', '<head>\n<script>\n' + runtime + '\n</script>', 'early Persisted runtime')
    # T3 registers a URL-handler desktop file at launch. Keep that registration
    # going through the refresher rather than pointing at a stale cached build.
    electron_source = archive.read(electron_main).decode()
    desktop_handler = match_one(r'function renderUrlHandlerDesktopEntry\(([\w$]+)\) \{', electron_source, 'URL handler registration')
    launcher = json.dumps(str(Path.home() / '.local/bin/t3code-nightly'))
    electron_source = replace_once(electron_source, desktop_handler[0], desktop_handler[0] + '\n' + desktop_handler[1] + '={...' + desktop_handler[1] + ',execTarget:' + launcher + '};', 'stable desktop URL handler')
    changes = {main: main_source.encode(), boot: boot_source.encode(), preload: preload_source.encode(), html: html_source.encode(), electron_main: electron_source.encode()}

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='persisted-build-', dir=destination.parent))
    try:
        for entry in source.iterdir():
            if entry.name in {'t3code', 'resources'}:
                continue
            (staging / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
        subprocess.run(['cp', '--reflink=auto', str(source / 't3code'), str(staging / 't3code')], check=True)
        resources = staging / 'resources'
        resources.mkdir()
        for entry in (source / 'resources').iterdir():
            if entry.name != 'app.asar':
                (resources / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
        archive.write(resources / 'app.asar', changes)
        (staging / 'persisted-build.json').write_text(json.dumps(expected, indent=2))
        (staging / 'persisted-version.txt').write_text(installed_version)
        # Check transformed code before it can replace a working overlay.
        check_environment = os.environ.copy()
        check_environment['ELECTRON_RUN_AS_NODE'] = '1'
        for name, content in [('keypad.js', keypad), ('ui.mjs', main_source), ('boot.cjs', boot_source), ('preload.cjs', preload_source), ('electron.cjs', electron_source)]:
            checked = staging / name
            checked.write_text(content)
            subprocess.run([str(source / 't3code'), '--check', str(checked)], check=True, capture_output=True, env=check_environment)
            checked.unlink()
        if destination.exists():
            shutil.rmtree(destination)
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return destination / 't3code'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default='/opt/t3code-nightly-bin')
    parser.add_argument('--destination')
    parser.add_argument('--prepare-only', action='store_true')
    args, forwarded = parser.parse_known_args()
    source = Path(args.source)
    try:
        cache = Path.home() / '.cache/t3code-persisted'
        cache.mkdir(parents=True, exist_ok=True)
        fingerprint = hashlib.sha256(json.dumps(signature(source), sort_keys=True).encode()).hexdigest()[:20]
        destination = Path(args.destination) if args.destination else cache / 'builds' / fingerprint
        with (cache / 'prepare.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            executable = prepare(source, destination)
            cleanup_builds(cache / 'builds', destination)
    except Exception as error:
        print(f'[T3 Persisted] Cannot customize this build: {error}. Launching the official app; memberships are retained.', file=sys.stderr)
        executable = source / 't3code'
    if args.prepare_only:
        print(executable)
        return 0 if executable != source / 't3code' else 1
    os.environ.pop('ELECTRON_RUN_AS_NODE', None)
    os.execv(str(executable), [str(executable), *forwarded])


def cleanup_builds(directory, current):
    """Keep two recent versions and all versions still in use by a process."""
    if not directory.exists():
        return
    active = set()
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            executable = Path(os.readlink(process / 'exe'))
            active.add(executable.parent)
        except OSError:
            pass
    builds = sorted((p for p in directory.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    kept = set(builds[:2]) | active | {current}
    for build in builds:
        if build not in kept:
            shutil.rmtree(build)


if __name__ == '__main__':
    sys.exit(main())
