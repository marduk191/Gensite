"""Keep uv's project pythonw launcher genuinely windowless on Windows.

Some uv releases create a console-subsystem pythonw trampoline. Use CPython's
own GUI venv redirector instead; it honors pyvenv.cfg and loads base pythonw.
Only the adjacent project .venv is touched, never an installed Python runtime.
"""
from pathlib import Path
import os
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]  # repository root; data folders live here


def _subsystem(path):
    try:
        data = path.read_bytes()
        offset = struct.unpack_from('<I',data,60)[0]
        return struct.unpack_from('<H',data,offset+24+68)[0]
    except (OSError,struct.error):
        return None


def ensure_gui_launcher():
    target = ROOT/'.venv/Scripts/pythonw.exe'
    if os.name != 'nt':
        return target
    if _subsystem(target) == 2:
        return target
    if Path(sys.prefix).resolve() != (ROOT/'.venv').resolve():
        raise RuntimeError('Run this helper with the Gensite .venv Python, not another environment.')
    source = Path(sys.base_prefix)/'Lib/venv/scripts/nt/pythonw.exe'
    if _subsystem(source) != 2:
        raise RuntimeError('CPython GUI venv redirector is missing. Recreate .venv using Python 3.12.')
    try:
        shutil.copyfile(source,target)
    except OSError as exc:
        raise RuntimeError('Close Gensite and retry; its local GUI launcher could not be prepared: '+str(exc)) from exc
    if _subsystem(target) != 2:
        raise RuntimeError('Could not verify the native GUI launcher.')
    return target


if __name__ == '__main__':
    try:
        print(ensure_gui_launcher())
    except RuntimeError as exc:
        print(str(exc),file=sys.stderr)
        raise SystemExit(1)
