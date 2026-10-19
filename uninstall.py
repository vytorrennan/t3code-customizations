#!/usr/bin/env python3
from pathlib import Path
import json
import shutil
import subprocess

root = Path.home() / '.local/share/t3code-persisted'
entries = Path.home()/'.local/share/applications'
manifest = json.loads((root/'backups/desktop-entries.json').read_text())
if shutil.which('systemctl'):
    subprocess.run(['systemctl', '--user', 'disable', '--now', 't3code-customizations.path'], check=False)
    subprocess.run(['systemctl', '--user', 'stop', 't3code-customizations.service'], check=False)
for name in ['t3code-customizations.path', 't3code-customizations.service']:
    (Path.home()/'.config/systemd/user'/name).unlink(missing_ok=True)
if shutil.which('systemctl'):
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=False)
for name, details in manifest.items():
    target = entries/name
    if target.exists() and str(Path.home()/'.local/bin/t3code-nightly') in target.read_text():
        if details['existed']:
            shutil.copy2(root/'backups'/name,target)
        else:
            target.unlink()
launcher = Path.home()/'.local/bin/t3code-nightly'
if launcher.exists() and 't3code-persisted' in launcher.read_text():
    launcher.unlink()
alias = Path.home()/'.local/bin/t3-code-nightly-desktop'
if alias.is_symlink() and alias.readlink() == launcher:
    alias.unlink()
if shutil.which('update-desktop-database'):
    subprocess.run(['update-desktop-database',str(entries)],check=True)
print('Previous launchers restored. Source and Persisted membership retained.')
