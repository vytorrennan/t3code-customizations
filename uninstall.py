#!/usr/bin/env python3
from pathlib import Path
import json
import shutil
import subprocess

root = Path.home() / '.local/share/t3code-persisted'
entries = Path.home()/'.local/share/applications'
manifest = json.loads((root/'backups/desktop-entries.json').read_text())
for name, details in manifest.items():
    target = entries/name
    if target.exists() and 't3code-nightly %U' in target.read_text() and str(Path.home()/'.local/bin') in target.read_text():
        if details['existed']:
            shutil.copy2(root/'backups'/name,target)
        else:
            target.unlink()
launcher = Path.home()/'.local/bin/t3code-nightly'
if launcher.exists() and 't3code-persisted' in launcher.read_text():
    launcher.unlink()
if shutil.which('update-desktop-database'):
    subprocess.run(['update-desktop-database',str(entries)],check=True)
print('Previous launchers restored. Source and Persisted membership retained.')
