"""Behavior checks for equivalent empty-sidebar conditions across compiler layouts."""
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from thread_menu import patch_empty_sidebar


class EmptySidebarTest(unittest.TestCase):
    def test_native_conditions_and_settled_filter_are_preserved(self):
        conditions = [
            'a.length+b.length+c.length+d.length+settled===0',
            'a.length+b.length+c.length===0 && settled===0',
            'b.length+a.length===0 && settled===0',
            '((a.length + b.length) + (c.length + d.length)) === 0 && (settled===0 || filtered)',
            '!searching && a.length+b.length+c.length+d.length===0&&(settled===0||filtered)',
        ]
        for condition in conditions:
            with self.subTest(condition=condition):
                source = 'function visible(){return ' + condition + '?render("No threads yet"):null}'
                transformed = patch_empty_sidebar(source)
                script = '''
const assert=require('node:assert/strict');
const a=[],b=[],c=[],d=[];
let settled=0,filtered=false,searching=false;
const render=text=>text;
const __t3PersistedRows=[];
TRANSFORMED
assert.equal(visible(),'No threads yet');
__t3PersistedRows.push({});
assert.equal(visible(),null,'A populated Persisted shelf must suppress the empty message');
__t3PersistedRows.length=0;settled=2;
assert.equal(visible(),null,'Keep native settled-thread handling');
'''.replace('TRANSFORMED', transformed)
                result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_unrecognized_and_ambiguous_empty_messages_are_rejected(self):
        source = 'function visible(){return a.length+b.length+c.length+d.length===0?render("No threads yet"):null}'
        for changed in [source.replace('===0', '>0'), source + source.replace('visible', 'other')]:
            with self.assertRaisesRegex(ValueError, 'empty sidebar message'):
                patch_empty_sidebar(changed)


if __name__ == '__main__':
    unittest.main()
