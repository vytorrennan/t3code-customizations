#!/usr/bin/env python3
from pathlib import Path
import shutil
import subprocess

SOURCE_ROOT = Path(__file__).resolve().parent
HOME_DIRECTORY = Path.home()
ROOT = HOME_DIRECTORY / '.local/share/t3code-persisted'
if SOURCE_ROOT != ROOT:
    ROOT.mkdir(parents=True, exist_ok=True)
    for directory in ['src', 'tests']:
        shutil.copytree(SOURCE_ROOT / directory, ROOT / directory, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for filename in ['README.md', 'install.py', 'uninstall.py']:
        shutil.copy2(SOURCE_ROOT / filename, ROOT / filename)
launcher = HOME_DIRECTORY/'.local/bin/t3code-nightly'
official = HOME_DIRECTORY/'.local/bin/t3code-official-nightly'
launcher.parent.mkdir(parents=True, exist_ok=True)
if launcher.exists() and 't3code-persisted' not in launcher.read_text():
    raise SystemExit('An existing user launcher would be overwritten. Installation stopped.')
launcher.write_text('#!/bin/sh\nexec /usr/bin/python3 ' + "'" + str(ROOT/'src/patch.py').replace("'", "'\\''") + "'" + ' "$@"\n')
launcher.chmod(0o755)
official.write_text('#!/bin/sh\nunset ELECTRON_RUN_AS_NODE\nexec /usr/bin/t3code-nightly "$@"\n')
official.chmod(0o755)
import sys
sys.path.insert(0, str(ROOT / 'src'))
from launchers import repair, install_guard
repair(backup=True)
# Cover both names supplied by the official package.
alias = HOME_DIRECTORY / '.local/bin/t3-code-nightly-desktop'
if (alias.exists() or alias.is_symlink()) and (not alias.is_symlink() or alias.readlink() != launcher):
    raise SystemExit('An existing t3-code-nightly-desktop launcher would be overwritten.')
if not alias.is_symlink():
    alias.symlink_to(launcher)
# Prepare now, so installation cannot report success with a broken adapter.
subprocess.run(['/usr/bin/python3', str(ROOT / 'src/patch.py'), '--prepare-only'], check=True)
install_guard(ROOT)
print('Installed and prepared. Quit and reopen T3 Code to activate customizations.')
