#!/usr/bin/env python3
"""Isolated native Wayland preview. No installed settings or other sessions are touched."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

parser = argparse.ArgumentParser()
parser.add_argument('--duration', type=int, default=600)
parser.add_argument('--output', default='/tmp/cibyp-campus-preview')
parser.add_argument('--port', type=int, default=5909)
parser.add_argument('--home')
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent / 'recipes/overlay/desktop'
output = Path(args.output)
output.mkdir(parents=True, exist_ok=True)
runtime = Path(tempfile.mkdtemp(prefix='cibyp-campus-'))
config = runtime / 'config'
config.mkdir()
environment = dict(os.environ, CIBYP_DESKTOP_ROOT=str(root), XDG_RUNTIME_DIR=str(runtime), XDG_CONFIG_HOME=str(config), WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1', WLR_RENDERER='pixman', WLR_LIBINPUT_NO_DEVICES='1', CIBYP_GEOMETRY='1280x800', PATH=str(root/'bin')+':'+os.environ['PATH'])
environment.pop('WAYLAND_DISPLAY', None)
environment.pop('SWAYSOCK', None)
environment.pop('DBUS_SESSION_BUS_ADDRESS', None)
environment['CIBYP_PREVIEW_PORT'] = str(args.port)
if args.home:
    environment['HOME'] = str(Path(args.home).resolve())
log = (output / 'session.log').open('w')
session = subprocess.Popen(['python3', '-u', str(root/'session/campus-session.py')], env=environment, stdout=log, stderr=log, start_new_session=True)
children = [session]
running = True
def stop(*_):
    global running
    running = False
signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)
try:
    deadline = time.monotonic()+30
    state = runtime/'campus-environment.json'
    while not state.is_file():
        if session.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError((output/'session.log').read_text())
        time.sleep(.2)
    environment.update(json.loads(state.read_text()))
    (output/'environment.json').write_text(json.dumps(environment))
    vnc = subprocess.Popen(['wayvnc', '127.0.0.1', str(args.port)], env=environment, stdout=log, stderr=log, start_new_session=True)
    children.append(vnc)
    print(json.dumps({'runtime': str(runtime), 'session': session.pid, 'output': str(output), 'port': args.port}), flush=True)
    deadline = time.monotonic()+args.duration
    while running and time.monotonic() < deadline and session.poll() is None:
        time.sleep(.5)
finally:
    for child in reversed(children):
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
    for child in children:
        try:
            child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
    log.close()
