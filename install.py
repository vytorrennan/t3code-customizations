#!/usr/bin/env python3
from pathlib import Path
import json
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
backup = ROOT/'backups'
backup.mkdir(exist_ok=True)
manifest_file = backup/'desktop-entries.json'
manifest = json.loads(manifest_file.read_text()) if manifest_file.exists() else {}
entries = HOME_DIRECTORY/'.local/share/applications'
entries.mkdir(parents=True, exist_ok=True)
for name in ['t3code.desktop','com.t3tools.T3Code.desktop']:
    target = entries/name
    if name not in manifest:
        manifest[name] = {'existed': target.exists()}
        if target.exists():
            shutil.copy2(target, backup/name)
    if target.exists():
        content = target.read_text()
    elif name == 't3code.desktop':
        content = Path('/usr/share/applications/t3code.desktop').read_text()
    else:
        content = '[Desktop Entry]\nType=Application\nName=T3 Code (Nightly)\nNoDisplay=true\nMimeType=x-scheme-handler/t3code;\nExec=t3code-nightly %U\n'
    lines = content.splitlines()
    lines = [('Exec=' + str(launcher) + ' %U') if line.startswith('Exec=') else ('TryExec=' + str(launcher)) if line.startswith('TryExec=') else line for line in lines]
    target.write_text('\n'.join(lines)+'\n')
manifest_file.write_text(json.dumps(manifest, indent=2)+'\n')
if shutil.which('update-desktop-database'):
    subprocess.run(['update-desktop-database',str(entries)],check=True)
print('Installed. Quit and reopen T3 Code to activate Persisted.')
