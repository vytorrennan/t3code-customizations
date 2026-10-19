"""Exercise real update preparation and the launcher's incompatible-update path."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch as mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
import patch
import launchers


class StartupTest(unittest.TestCase):
    def test_package_changes_are_detected_even_with_identical_size_and_timestamp(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            (source / 'resources').mkdir()
            archive = source / 'resources/app.asar'
            archive.write_bytes(b'old version')
            before = archive.stat()
            original = patch.signature(source)
            archive.write_bytes(b'new version')
            __import__('os').utime(archive, ns=(before.st_atime_ns, before.st_mtime_ns))
            self.assertNotEqual(patch.signature(source), original)

    def test_update_keeps_a_complete_customized_app_when_new_package_is_incompatible(self):
        with tempfile.TemporaryDirectory(prefix='t3-update-regression-') as temporary:
            directory = Path(temporary)
            source = directory / 'official'
            source.mkdir()
            subprocess.run(['cp', '-aL', '--reflink=auto', '/opt/t3code-nightly-bin/.', str(source)], check=True)
            cache = directory / 'cache'
            first, failure = patch.select_build(source, cache)
            self.assertIsNone(failure)
            self.assertNotEqual(first.parent, source)
            archive_before = (first.parent / 'resources/app.asar').stat().st_size
            # Replace the package just like a package-manager update. The old
            # implementation either started this uncustomized app or retained
            # symlinks into its replaced Electron libraries and native modules.
            import shutil
            shutil.rmtree(source)
            source.mkdir()
            (source / 't3code').write_text('#!/bin/sh\necho UNCUSTOMIZED\n')
            (source / 'resources').mkdir()
            (source / 'resources/app.asar').write_bytes(b'unsupported next nightly')
            fallback, failure = patch.select_build(source, cache)
            self.assertEqual(fallback, first)
            self.assertIsNotNone(failure)
            self.assertEqual((fallback.parent / 'resources/app.asar').stat().st_size, archive_before)
            links = [p for p in fallback.parent.rglob('*') if p.is_symlink() and str(p.resolve()).startswith(str(source))]
            self.assertEqual(links, [])
            environment = __import__('os').environ.copy()
            environment['ELECTRON_RUN_AS_NODE'] = '1'
            probe = subprocess.run([str(fallback), '-e', "const fs=require('node:fs');const p=process.argv[1];console.log(JSON.parse(fs.readFileSync(p+'/package.json')).version);require(p+'/apps/desktop/dist-electron/compileCache.cjs')", str(fallback.parent / 'resources/app.asar')], env=environment, capture_output=True, text=True)
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertIn('nightly', probe.stdout)

    def test_no_retained_build_never_launches_the_official_app(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.object(patch, 'select_build', side_effect=patch.UnsupportedBuild('future sidebar')):
                with mock.object(patch, 'report_failure'), mock.object(patch.os, 'execv') as execute:
                    with mock.object(sys, 'argv', ['patch.py', '--destination', temporary]):
                        self.assertEqual(patch.main(), 1)
                    execute.assert_not_called()

    def test_desktop_registration_is_repaired_and_repair_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            desktop = home / '.local/share/applications/com.t3tools.T3Code.desktop'
            desktop.parent.mkdir(parents=True)
            original = '[Desktop Entry]\nName=T3\nExec="/opt/t3code-nightly-bin/t3code" %U\n'
            desktop.write_text(original)
            launchers.repair(home, backup=True)
            expected = desktop.read_text()
            self.assertIn(str(home / '.local/bin/t3code-nightly'), expected)
            before = desktop.stat().st_mtime_ns
            launchers.repair(home)
            self.assertEqual(desktop.stat().st_mtime_ns, before)
            desktop.write_text(original)
            launchers.repair(home)
            self.assertEqual(desktop.read_text(), expected)
            self.assertEqual((home / '.local/share/t3code-persisted/backups/com.t3tools.T3Code.desktop').read_text(), original)


if __name__ == '__main__':
    unittest.main()
