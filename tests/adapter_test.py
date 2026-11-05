import importlib.util
from pathlib import Path
import unittest
import re
import sys
import subprocess

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
spec = importlib.util.spec_from_file_location('patch', ROOT/'src/patch.py')
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)


class AdapterTest(unittest.TestCase):
    def test_current_installed_build_has_exact_integration_points(self):
        archive = patch.Archive('/opt/t3code-nightly-bin/resources/app.asar')
        main = next(name for name in archive.entries if name.startswith('apps/server/dist/client/assets/main-') and name.endswith('.js'))
        result = patch.patch_sidebar(archive.read(main).decode())
        self.assertIn('__t3PersistedRuntime.menu(', result)
        self.assertIn('sidebar-persisted-shelf-toggle', result)

    def test_compiled_sidebar_preserves_props_and_marks_switch(self):
        archive = patch.Archive('/opt/t3code-nightly-bin/resources/app.asar')
        main = next(name for name in archive.entries if name.startswith('apps/server/dist/client/assets/main-') and name.endswith('.js'))
        source = archive.read(main).decode()
        marker = source.index('snoozed-shelf-header')
        start = source.rfind('function ', 0, marker)
        header = re.match(r'function ([\w$]+)\(([\w$]+)\)\{let ([\w$]+)=\(0,([\w$]+)\.c\)\((\d+)\),', source[start:])
        self.assertIsNotNone(header)
        result = patch.patch_sidebar(source)
        self.assertIn(f'function {header[1]}({header[2]}){{let __t3PersistedState=', result)
        self.assertIn(f'let {header[3]}=(0,{header[4]}.c)({header[5]}),', result)
        self.assertIn('case`persisted-header`', result)
        self.assertIn('persistedRef:__t3PersistedState.has(', result)
        self.assertIn('"data-persisted-ref":', result)

    def test_namespace_identifiers_may_contain_dollar_signs(self):
        archive = patch.Archive('/opt/t3code-nightly-bin/resources/app.asar')
        main = next(name for name in archive.entries if name.startswith('apps/server/dist/client/assets/main-') and name.endswith('.js'))
        source = archive.read(main).decode()
        react = re.search(r'\(0,([\w$]+)\.useLayoutEffect\)', source)[1]
        jsx = re.search(r'\(0,([\w$]+)\.jsx\)\([\w$]+,\{marker:`pinned-header`', source)[1]
        # Exercise the full adapter with valid minifier namespace spellings.
        source = re.sub(re.escape(react) + r'(?=\.(?:useMemo|useLayoutEffect|useRef))', lambda _: '$react', source)
        source = re.sub(re.escape(jsx) + r'(?=\.jsx)', lambda _: '$jsx', source)
        result = patch.patch_sidebar(source)
        self.assertIn('__t3PersistedRuntime.use($react)', result)
        self.assertIn('(0,$jsx.jsx)', result)

    def test_sorting_helpers_can_be_renamed_between_builds(self):
        archive = patch.Archive('/opt/t3code-nightly-bin/resources/app.asar')
        main = next(name for name in archive.entries if name.startswith('apps/server/dist/client/assets/main-') and name.endswith('.js'))
        source = archive.read(main).decode()
        marker = source.index('={pinned:[],active:[],working:[],snoozed:[],settled:[]}')
        start = source.rfind('function ', 0, marker)
        end = source.index('}function ', marker) + 1
        body = source[start:end]
        strategy = re.match(r'function ([\w$]+)\(', body)[1]
        resolver = re.search(r'([\w$]+)\(([\w$]+),([\w$]+).key,([\w$]+)\(([\w$]+)\)\)', body)[1]
        for name, renamed in [(strategy, '$futureSort'), (resolver, '$futureTarget')]:
            source = re.sub(r'(?<![\w$])' + re.escape(name) + r'(?=\()', lambda _: renamed, source)
        result = patch.patch_sidebar(source)
        self.assertIn('__t3PersistedRuntime.wrap($futureTarget)', result)
        self.assertIn('function $futureSort(', result)
        checked = subprocess.run(['node', '--check', '--input-type=module'],
                                 input=result, capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_private_toggle_implementation_is_not_an_integration_point(self):
        archive = patch.Archive('/opt/t3code-nightly-bin/resources/app.asar')
        main = next(name for name in archive.entries if name.startswith('apps/server/dist/client/assets/main-') and name.endswith('.js'))
        source = archive.read(main).decode()
        toggle = re.search(r'\(0,[\w$]+\.jsx\)\(([\w$]+),\{[^{}]*onClick:[\w$]+\.toggle.onToggle', source)[1]
        start = source.index('function ' + toggle + '(')
        end = source.index('}function ', start) + 1
        changed = source[:start] + f'function {toggle}(props){{return null}}' + source[end:]
        result = patch.patch_sidebar(changed)
        self.assertIn('__t3PersistedRuntime.ShelfToggle', result)
        checked = subprocess.run(['node', '--check', '--input-type=module'],
                                 input=result, capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_unknown_layout_is_rejected_without_guessing(self):
        with self.assertRaises(patch.UnsupportedBuild):
            patch.patch_sidebar('function unknown(){return null}')


if __name__ == '__main__':
    unittest.main()
