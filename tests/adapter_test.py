import importlib.util
from pathlib import Path
import unittest
import re
import sys

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

    def test_compiled_sidebar_preserves_props_and_accepts_braced_loop(self):
        archive = patch.Archive('/opt/t3code-nightly-bin/resources/app.asar')
        main = next(name for name in archive.entries if name.startswith('apps/server/dist/client/assets/main-') and name.endswith('.js'))
        source = archive.read(main).decode()
        marker = source.index('snoozed-shelf-header')
        start = source.rfind('function ', 0, marker)
        header = re.match(r'function ([\w$]+)\(([\w$]+)\)\{', source[start:])
        self.assertIsNotNone(header)
        result = patch.patch_sidebar(source)
        self.assertIn(header[0] + 'let __t3PersistedState=', result)
        compact = re.search(r'for\(let ([\w$]+) of ([\w$]+)\)if\(\1.kind===`thread`\)([\w$]+).push\(([\w$]+)\(([\w$]+).get\(\1.key\),\1.section\)\);else ([\w$]+):switch', source)
        self.assertIsNotNone(compact)
        item, items, output, row, threads, label = compact.groups()
        source = source.replace(compact[0], f'for(let {item} of {items}){{if({item}.kind===`thread`){{{output}.push({row}({threads}.get({item}.key),{item}.section));continue}}{label}:switch', 1)
        source = source.replace(f'}}return {output}}})()', f'}}}}return {output}}})()', 1)
        # The previous compiler emitted a zero-argument sidebar and braced loop.
        source = source.replace(header[0], f'function {header[1]}(){{', 1)
        self.assertIn('sidebar-persisted-shelf-toggle', patch.patch_sidebar(source))

    def test_namespace_identifiers_may_contain_dollar_signs(self):
        archive = patch.Archive('/opt/t3code-nightly-bin/resources/app.asar')
        main = next(name for name in archive.entries if name.startswith('apps/server/dist/client/assets/main-') and name.endswith('.js'))
        source = archive.read(main).decode()
        react = re.search(r'\(0,([\w$]+)\.useLayoutEffect\)', source)[1]
        jsx = re.search(r'\(0,([\w$]+)\.jsx(?:s)?\)\([\w$]+,\{onClick:[\w$]+\.toggle.onToggle', source)[1]
        # Exercise the full adapter with valid minifier namespace spellings.
        source = re.sub(re.escape(react) + r'(?=\.(?:useMemo|useLayoutEffect|useRef))', lambda _: '$react', source)
        source = re.sub(re.escape(jsx) + r'(?=\.jsx)', lambda _: '$jsx', source)
        result = patch.patch_sidebar(source)
        self.assertIn('__t3PersistedRuntime.use($react)', result)
        self.assertIn('(0,$jsx.jsx)', result)

    def test_unknown_layout_is_rejected_without_guessing(self):
        with self.assertRaises(patch.UnsupportedBuild):
            patch.patch_sidebar('function unknown(){return null}')


if __name__ == '__main__':
    unittest.main()
