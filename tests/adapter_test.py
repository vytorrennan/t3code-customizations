import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
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

    def test_unknown_layout_is_rejected_without_guessing(self):
        with self.assertRaises(patch.UnsupportedBuild):
            patch.patch_sidebar('function unknown(){return null}')


if __name__ == '__main__':
    unittest.main()
