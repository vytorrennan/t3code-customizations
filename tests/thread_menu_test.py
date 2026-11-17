"""Exercise transformed menu calls, including arguments added by newer nightlies."""
from pathlib import Path
import subprocess
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from thread_menu import patch_thread_menu


class ThreadMenuTest(unittest.TestCase):
    def test_menu_arguments_and_native_actions_are_preserved(self):
        option_sets = [
            'canOperate:true,branch:thread.branch,snoozePresets:presets',
            'snoozePresets:presets,extra:{nested:[1,2]},branch:thread.branch??null,canOperate:true,added:true',
            'canOperate:true,pattern:/[(){}]/u,ratio:12/3,branch:thread.branch,snoozePresets:presets',
            'canOperate:true,description:`ignore branch:wrong.branch ${format({nested:`${1}`})}`,branch:thread.branch,snoozePresets:presets',
        ]
        for fields in option_sets:
            for arguments in ['', 'position', 'position,anchor', 'position,anchor,{keyboard:true,values:[1,2]}']:
                for style in ['compact', 'formatted', 'comments', 'bracket-access', 'renamed', 'shorthand', 'block-thunk', 'function-thunk', 'unicode']:
                    with self.subTest(fields=fields, arguments=arguments, style=style):
                        source = ('async function openMenu(){let result=await attempt(()=>platform.contextMenu.show('
                                  'build({' + fields + '})' + (',' + arguments if arguments else '') + '));'
                                  'if(result._tag!==`Failure`)nativeHandled.push(result.value)}')
                        if style == 'formatted':
                            source = source.replace('=await ', ' = await ').replace('()=>', '() => ').replace('.contextMenu.show(', '.contextMenu.show ( ').replace('build({', 'build( { ').replace('}),', '} ), ')
                        elif style == 'comments':
                            source = source.replace('=await ', '= /* binding */ await ').replace('()=>', '() /* thunk */ => ').replace('canOperate:', '/* option */ canOperate:')
                        elif style == 'bracket-access':
                            source = source.replace('.contextMenu.show', '["contextMenu"]["show"]').replace('branch:thread.branch', '"branch":thread["branch"]')
                        elif style == 'renamed':
                            aliases = {'result': '$result', 'attempt': '$attempt', 'platform': '$platform', 'build': '$build'}
                            source = re.sub(r'\b(?:result|attempt|platform|build)\b', lambda match: aliases[match[0]], source)
                        elif style == 'shorthand':
                            source = source.replace('canOperate:true', 'canOperate').replace('snoozePresets:presets', 'snoozePresets')
                        elif style in ['block-thunk', 'function-thunk']:
                            source = source.replace('()=>platform.contextMenu.show', ('()=>{return ' if style == 'block-thunk' else 'function(){return ') + 'platform.contextMenu.show').replace('));if(result', ')});if(result')
                        elif style == 'unicode':
                            source = 'const decoration="🦉";\n' + source
                        transformed = patch_thread_menu(source)
                        script = """
    const assert = require('node:assert/strict');
    const thread = {environmentId:'fixture-env', id:'fixture-thread',branch:'main'};
    const canOperate=true,snoozePresets=[],presets=snoozePresets,position={x:1,y:2},anchor='keyboard-anchor';
    const format = () => 'nested';
    let selected='persisted:add',tag='Success',sent=[],handled=[],nativeHandled=[];
    const build = options => {assert.equal(options.branch,thread.branch);return [{id:'native'}];};
    const platform={contextMenu:{show:async (...args)=>{sent=args;return selected;}}};
    const attempt=async f=>({_tag:tag,value:await f()});
    const __t3PersistedRuntime={
     menu:(items,ref)=>{assert.equal(ref,thread);return [...items,{id:'persisted:add'}];},
     isAction:value=>value==='persisted:add',
     handle:async (value,ref)=>{assert.equal(ref,thread);handled.push(value);},
    };
    const $attempt=attempt,$platform=platform,$build=build;
TRANSFORMED
    (async()=>{
     await openMenu();
     assert.deepEqual(sent.slice(1),[ARGUMENTS]);
     assert.deepEqual(sent[0].map(item=>item.id),['native','persisted:add']);
     assert.deepEqual(handled,['persisted:add']);
     assert.deepEqual(nativeHandled,[]);
     selected='native';await openMenu();
     assert.deepEqual(handled,['persisted:add']);
     assert.deepEqual(nativeHandled,['native']);
 tag='Failure';selected='persisted:add';await openMenu();
 assert.deepEqual(handled,['persisted:add']);
 assert.deepEqual(nativeHandled,['native']);
    })().catch(error=>{console.error(error);process.exitCode=1;});
    """.replace('TRANSFORMED', transformed).replace('ARGUMENTS', arguments)
                        result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unrelated_or_ambiguous_menus_are_rejected(self):
        menu = ('let result=await attempt(()=>platform.contextMenu.show('
                'build({canOperate:true,branch:thread.branch,snoozePresets:presets}),position,anchor));')
        for source in ['nothing here', '// ' + menu, 'const example=' + repr(menu) + ';', menu.replace('branch:thread.branch', 'branch:other'), menu + menu.replace('let result=', 'let otherResult='), menu.replace('.show(', '[show]('), menu.replace('branch:thread.branch', 'branch:thread[key]')]:
            with self.subTest(source=source):
                with self.assertRaisesRegex(ValueError, 'native thread menu'):
                    patch_thread_menu(source)
        # A separate draft menu must stay untouched while the thread menu is patched.
        draft = menu.replace('let result=', 'let draftResult=').replace('canOperate:true,branch:thread.branch,snoozePresets:presets', 'hasBranch:true')
        result = patch_thread_menu(draft + menu)
        self.assertTrue(result.startswith(draft))
        self.assertEqual(result.count('__t3PersistedRuntime.menu('), 1)


if __name__ == '__main__':
    unittest.main()
