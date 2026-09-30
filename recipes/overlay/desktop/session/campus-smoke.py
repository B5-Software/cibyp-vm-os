#!/usr/bin/env python3
"""Isolated installed-desktop smoke test; cleanup only the processes it owns."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import cairo

parser = argparse.ArgumentParser()
parser.add_argument('--geometry', default='1280x800')
parser.add_argument('--out-png', type=Path, default=Path('/tmp/cibyp-desktop.png'))
args = parser.parse_args()
width, height = map(int, args.geometry.split('x'))
if width < 800 or height < 600:
    raise SystemExit('Desktop smoke requires a work area of at least 800x600')
root = Path(os.environ.get('CIBYP_DESKTOP_ROOT', '/usr/local/lib/cibyp-desktop'))
result = Path(tempfile.gettempdir())/'cibyp-desktop-smoke.result'
log_path = Path(tempfile.gettempdir())/f'cibyp-desktop-smoke-{os.getuid()}.log'
children = []


def wait(check, message, seconds=25):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(.1)
    raise RuntimeError(message)


def end(child):
    if child.poll() is None:
        os.killpg(child.pid, signal.SIGTERM)
        try:
            child.wait(timeout=12)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=3)


def nodes(node):
    yield node
    for item in node.get('nodes', []) + node.get('floating_nodes', []):
        yield from nodes(item)


try:
    with tempfile.TemporaryDirectory(prefix='cibyp-installed-smoke-') as temporary, log_path.open('w') as log:
        home = Path(temporary)/'home'
        runtime = Path(temporary)/'runtime'
        home.mkdir()
        runtime.mkdir(mode=0o700)
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home/'.config'), XDG_DATA_HOME=str(home/'.local/share'), XDG_RUNTIME_DIR=str(runtime), CIBYP_DESKTOP_ROOT=str(root), CIBYP_GEOMETRY=args.geometry, WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1', WLR_RENDERER='pixman', GSK_RENDERER='cairo', GTK_A11Y='none', GDK_BACKEND='wayland')
        for key in ('LD_PRELOAD', 'SWAYSOCK', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS'):
            env.pop(key, None)
        session = subprocess.Popen([sys.executable, '-u', str(root/'session/campus-session.py')], env=env, stdout=log, stderr=log, start_new_session=True)
        children.append(session)
        try:
            environment_file = runtime/'campus-environment.json'
            wait(environment_file.is_file, 'Wayland session did not start')
            env.update(json.loads(environment_file.read_text()))
            wait((runtime/'cibyp-shell.sock').is_socket, 'Taskbar socket did not appear')
            time.sleep(1)
            args.out_png.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['grim', str(args.out_png)], env=env, check=True)
            screenshot = cairo.ImageSurface.create_from_png(str(args.out_png))
            assert (screenshot.get_width(), screenshot.get_height()) == (width, height), 'Incorrect output resolution'
            data = bytes(screenshot.get_data())
            stride = screenshot.get_stride()
            assert data[(height-20)*stride+width*2:(height-20)*stride+width*2+3] != data[(height//2)*stride+width*2:(height//2)*stride+width*2+3], 'Taskbar did not render'
            print('PASS native Wayland, illustrated desktop and bottom taskbar', flush=True)
            with socket.socket(socket.AF_UNIX) as control:
                control.connect(str(runtime/'cibyp-shell.sock'))
                control.sendall(b'menu\n')
            time.sleep(.7)
            menu_png = Path(temporary)/'menu.png'
            subprocess.run(['grim', str(menu_png)], env=env, check=True)
            assert bytes(cairo.ImageSurface.create_from_png(str(menu_png)).get_data()) != data, 'Launcher did not open'
            print('PASS launcher responds and changes the displayed frame', flush=True)
            expected = {'files', 'editor', 'calc', 'viewer', 'terminal', 'settings', 'about'}
            for kind in expected:
                children.append(subprocess.Popen([sys.executable, '-u', str(root/'bin'/('cibyp-'+kind))], env=env, stdout=log, stderr=log, start_new_session=True))
            def applications():
                tree = json.loads(subprocess.check_output(['swaymsg', '-r', '-t', 'get_tree'], env=env))
                return {node.get('app_id', '').split('.')[-1] for node in nodes(tree) if node.get('app_id')}
            wait(lambda: expected <= applications(), 'A built-in native application failed to open')
            time.sleep(.3)
            assert 'Traceback' not in log_path.read_text(), log_path.read_text()
            print('PASS seven native applications open without exceptions', flush=True)
        finally:
            for child in reversed(children):
                end(child)
    result.write_text('PASS\n')
    print('结果：全部通过', flush=True)
except Exception as error:
    result.write_text('FAIL\n')
    print(f'FAIL {error}\nSee {log_path}', file=sys.stderr)
    raise SystemExit(1)
