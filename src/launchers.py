"""Keep user desktop and command entry points outside package-owned files."""
from pathlib import Path
import json
import shutil
import subprocess


DESKTOP_NAMES = ('t3code.desktop', 'com.t3tools.T3Code.desktop')


def repair(home=None, backup=False):
    home = Path(home) if home else Path.home()
    root = home / '.local/share/t3code-persisted'
    launcher = home / '.local/bin/t3code-nightly'
    entries = home / '.local/share/applications'
    entries.mkdir(parents=True, exist_ok=True)
    backups = root / 'backups'
    backups.mkdir(parents=True, exist_ok=True)
    manifest_path = backups / 'desktop-entries.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    changed = False
    for name in DESKTOP_NAMES:
        target = entries / name
        if backup and name not in manifest:
            manifest[name] = {'existed': target.exists()}
            if target.exists():
                shutil.copy2(target, backups / name)
        template = Path('/usr/share/applications') / name
        if target.exists():
            content = target.read_text()
        elif template.exists():
            content = template.read_text()
        else:
            content = '[Desktop Entry]\nType=Application\nName=T3 Code (Nightly)\nNoDisplay=true\nMimeType=x-scheme-handler/t3code;\nExec=t3code-nightly %U\n'
        lines = [('Exec="' + str(launcher) + '" %U') if line.startswith('Exec=') else ('TryExec=' + str(launcher)) if line.startswith('TryExec=') else line for line in content.splitlines()]
        desired = '\n'.join(lines) + '\n'
        if desired != content:
            temporary = target.with_suffix('.desktop.tmp')
            temporary.write_text(desired)
            temporary.replace(target)
            changed = True
    if backup:
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    if changed and shutil.which('update-desktop-database'):
        subprocess.run(['update-desktop-database', str(entries)], check=True)


def install_guard(root):
    """Prepare after package updates and repair desktop entries rewritten by T3."""
    home = Path.home()
    units = home / '.config/systemd/user'
    units.mkdir(parents=True, exist_ok=True)
    command = '/usr/bin/python3 "' + str(root / 'src/patch.py') + '" --prepare-only'
    (units / 't3code-customizations.service').write_text(
        '[Unit]\nDescription=Prepare T3 Code customizations after updates\nConditionPathExists=!/var/lib/pacman/db.lck\n'
        '[Service]\nType=oneshot\nExecStart=' + command + '\n')
    (units / 't3code-customizations.path').write_text(
        '[Unit]\nDescription=Watch T3 Code updates and launchers\n'
        '[Path]\nPathChanged=/opt/t3code-nightly-bin/resources/app.asar\n'
        'PathChanged=/opt/t3code-nightly-bin/t3code\n'
        'PathChanged=/var/lib/pacman\n'
        'PathChanged=' + str(home / '.local/share/applications/t3code.desktop') + '\n'
        'PathChanged=' + str(home / '.local/share/applications/com.t3tools.T3Code.desktop') + '\n'
        'Unit=t3code-customizations.service\n'
        '[Install]\nWantedBy=default.target\n')
    if not shutil.which('systemctl'):
        print('systemd unavailable; launch-time preparation remains enabled.')
        return
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', '--now', 't3code-customizations.path'], check=True)
