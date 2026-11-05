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

    def test_package_transaction_is_pending_without_adapter_notification_and_recovers(self):
        import json
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            cache = home / '.cache/t3code-persisted'
            retained = cache / 'builds/retained'
            (retained / 'resources').mkdir(parents=True)
            (retained / 't3code').touch()
            (retained / 'resources/app.asar').touch()
            (retained / 'persisted-self-contained').touch()
            (cache / 'last-good').symlink_to(retained)
            source = Path('/opt/t3code-nightly-bin')
            with mock.object(Path, 'home', return_value=home), mock.object(patch, 'repair'), \
                 mock.object(patch.Path, 'exists', autospec=True, side_effect=lambda path: True if str(path) == '/var/lib/pacman/db.lck' else path.is_file() or path.is_dir()), \
                 mock.object(patch, 'signature', side_effect=AssertionError('Must not read changing package')), \
                 mock.object(patch, 'prepare') as prepare, \
                 mock.object(patch, 'report_failure') as report, \
                 mock.object(sys, 'argv', ['patch.py', '--prepare-only']):
                self.assertEqual(patch.main(), 0)
                prepare.assert_not_called()
                report.assert_not_called()
            status = json.loads((cache / 'status.json').read_text())
            self.assertIsNone(status['updateError'])
            self.assertTrue(status['updatePending'])
            self.assertEqual(status['executable'], str(retained / 't3code'))
            # Simulate the completion-triggered preparation after the lock clears.
            def prepare_new(source, destination):
                (destination / 'resources').mkdir(parents=True)
                for name in ['t3code', 'persisted-self-contained', 'resources/app.asar']:
                    (destination / name).touch()
                return destination / 't3code'

            with mock.object(Path, 'home', return_value=home), mock.object(patch, 'repair'), \
                 mock.object(patch, 'signature', return_value={'adapter': 'new'}), \
                 mock.object(patch, 'prepare', side_effect=prepare_new) as prepare, \
                 mock.object(patch, 'report_failure') as report, \
                 mock.object(sys, 'argv', ['patch.py', '--prepare-only']):
                self.assertEqual(patch.main(), 0)
                prepare.assert_called_once()
                report.assert_not_called()
            status = json.loads((cache / 'status.json').read_text())
            self.assertFalse(status['updatePending'])
            self.assertIsNone(status['updateError'])
            self.assertNotEqual(status['executable'], str(retained / 't3code'))
            self.assertEqual((cache / 'last-good').resolve() / 't3code', Path(status['executable']))

    def test_transaction_starting_during_preparation_is_also_pending(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            retained = cache / 'retained'
            (retained / 'resources').mkdir(parents=True)
            for name in ['t3code', 'persisted-self-contained', 'resources/app.asar']:
                (retained / name).touch()
            (cache / 'last-good').symlink_to(retained)
            with mock.object(patch, 'package_update_in_progress', side_effect=[False, True]), \
                 mock.object(patch, 'signature', return_value={}), \
                 mock.object(patch, 'prepare', side_effect=FileNotFoundError('package replaced')):
                executable, failure = patch.select_build(Path('/opt/t3code-nightly-bin'), cache)
            self.assertEqual(executable, retained / 't3code')
            self.assertIsInstance(failure, patch.UpdateInProgress)

    def test_first_launch_during_transaction_stops_without_false_adapter_alert(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.object(Path, 'home', return_value=Path(temporary)), \
                 mock.object(patch, 'repair'), \
                 mock.object(patch, 'package_update_in_progress', return_value=True), \
                 mock.object(patch, 'signature') as signature, \
                 mock.object(patch, 'prepare') as prepare, \
                 mock.object(patch, 'report_failure') as report, \
                 mock.object(patch.os, 'execv') as execute, \
                 mock.object(sys, 'argv', ['patch.py']):
                self.assertEqual(patch.main(), 1)
                signature.assert_not_called()
                prepare.assert_not_called()
                execute.assert_not_called()
                report.assert_not_called()

    def test_same_incompatible_update_is_reported_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            executable = cache / 'retained/t3code'
            failure = 'changed integration point'
            self.assertTrue(patch.record_status(cache, executable, failure, 'package-a'))
            self.assertFalse(patch.record_status(cache, executable, failure, 'package-a'))
            self.assertTrue(patch.record_status(cache, executable, failure, 'package-b'))
            patch.record_status(cache, executable, None)
            self.assertTrue(patch.record_status(cache, executable, failure, 'package-b'))

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
