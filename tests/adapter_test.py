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

    def test_namespace_identifiers_may_contain_dollar_signs(self):
        archive = patch.Archive('/opt/t3code-nightly-bin/resources/app.asar')
        main = next(name for name in archive.entries if name.startswith('apps/server/dist/client/assets/main-') and name.endswith('.js'))
        source = archive.read(main).decode()
        react = re.search(r'\(0,([\w$]+)\.useLayoutEffect\)', source)[1]
        jsx = re.search(r'\(0,([\w$]+)\.jsx\)\([\w$]+,\{onClick:[\w$]+\.toggle.onToggle', source)[1]
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
