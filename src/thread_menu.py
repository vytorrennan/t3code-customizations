"""Apply sidebar edits by JavaScript syntax, rather than generated spellings."""
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent


def analyze(source, mode):
    # Electron is already a required part of the supported T3 installation.
    electron = Path('/opt/t3code-nightly-bin/t3code')
    runtime = str(electron) if electron.is_file() else shutil.which('node')
    if runtime is None:
        raise ValueError('Cannot analyze sidebar syntax: no JavaScript runtime is available')
    environment = os.environ.copy()
    environment['ELECTRON_RUN_AS_NODE'] = '1'
    result = subprocess.run([runtime, str(ROOT / 'sidebar-syntax.mjs')],
                            input=json.dumps({'source': source, 'mode': mode}),
                            capture_output=True, text=True, env=environment, timeout=30)
    try:
        document = json.loads(result.stdout)
    except ValueError:
        raise ValueError('Cannot analyze sidebar syntax: parser process did not return a result') from None
    if result.returncode or 'error' in document:
        raise ValueError(document.get('error', 'Cannot analyze sidebar syntax'))
    return document['output']


def patch_thread_menu(source):
    return analyze(source, 'thread-menu')


def inspect_thread_menu(source):
    return analyze(source, 'inspect-menu')


def patch_empty_sidebar(source):
    return analyze(source, 'empty-sidebar')
