#!/usr/bin/env python3
"""Session supervisor. Owns only its children; never kills another Wayland session."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(os.environ.get('CIBYP_DESKTOP_ROOT', '/usr/local/lib/cibyp-desktop')).resolve()
runtime = Path(os.environ.get('XDG_RUNTIME_DIR', f'/tmp/cibyp-runtime-{os.getuid()}'))
runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
if runtime.stat().st_uid != os.getuid():
    raise SystemExit('Wayland runtime directory belongs to another user')
os.chmod(runtime, 0o700)
os.environ.update(XDG_RUNTIME_DIR=str(runtime), XDG_SESSION_TYPE='wayland', XDG_CURRENT_DESKTOP='CIBYP', GDK_BACKEND='wayland', QT_QPA_PLATFORM='wayland', MOZ_ENABLE_WAYLAND='1', GTK_A11Y='none', GSK_RENDERER='cairo', LIBGL_ALWAYS_SOFTWARE='1')
os.environ['PATH'] = str(ROOT/'bin') + os.pathsep + os.environ.get('PATH', '/usr/bin:/bin')
lock = (runtime / 'cibyp-session.lock').open('a')
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit('CIBYP desktop is already running in this runtime directory')

children, stopping = [], False


def spawn(argv, **kwargs):
    child = subprocess.Popen(argv, start_new_session=True, **kwargs)
    children.append(child)
    return child


def stop(*_):
    global stopping
    stopping = True


def terminate_owned(child, sig):
    try:
        os.killpg(child.pid, sig)
    except ProcessLookupError:
        pass
    except PermissionError:
        subprocess.run(['sudo', '-n', '/bin/kill', '-' + signal.Signals(sig).name.removeprefix('SIG'), '--', '-' + str(child.pid)], check=False)


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
try:
    if not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        bus = subprocess.run(['dbus-daemon', '--session', '--fork', '--print-address=1', '--print-pid=1'], check=True, capture_output=True, text=True).stdout.splitlines()
        os.environ['DBUS_SESSION_BUS_ADDRESS'] = bus[0]
        bus_pid = int(bus[1])
    else:
        bus_pid = None
    (runtime / 'campus-session.pid').write_text(str(os.getpid()))
    # uinput must exist before libinput enumerates devices. A preview using a
    # pure headless backend relies on wayvnc's virtual input instead.
    if 'libinput' in os.environ.get('WLR_BACKENDS', '') and Path('/dev/uinput').exists():
        spawn(['sudo', '-n', 'env', f'XDG_RUNTIME_DIR={runtime}', 'python3', str(ROOT/'bin/cibyp-input'), 'daemon'])
        time.sleep(.7)
    config = Path(os.environ.get('CIBYP_SWAY_CONFIG', str(ROOT / 'config/sway/config')))
    if not config.is_file():
        config = Path('/etc/cibyp/sway/config')
    compositor = spawn(['sway', '--config', str(config)])
    deadline = time.monotonic() + 120
    ipc = None
    while time.monotonic() < deadline and not stopping:
        if compositor.poll() is not None:
            raise RuntimeError('Sway exited before the desktop was ready')
        ipc = next(iter(runtime.glob(f'sway-ipc.{os.getuid()}.{compositor.pid}.sock')), None)
        displays = [path for path in runtime.glob('wayland-*') if path.is_socket()]
        if ipc and displays:
            os.environ.update(SWAYSOCK=str(ipc), WAYLAND_DISPLAY=displays[0].name)
            break
        time.sleep(.1)
    if not ipc or not os.environ.get('WAYLAND_DISPLAY'):
        raise RuntimeError('Wayland startup timed out')
    geometry = os.environ.get('CIBYP_GEOMETRY', '1280x800')
    width, height = map(int, geometry.split('x'))
    # Socket creation precedes IPC readiness, especially under arm64 TCG.
    # Retry a bounded query instead of treating the first timeout as a crash.
    outputs = None
    while time.monotonic() < deadline and not stopping:
        try:
            response = subprocess.run(['swaymsg', '-r', '-t', 'get_outputs'], capture_output=True, text=True, timeout=8)
            if response.returncode == 0:
                outputs = json.loads(response.stdout)
                break
        except (subprocess.TimeoutExpired, ValueError):
            pass
        if compositor.poll() is not None:
            raise RuntimeError('Sway exited while waiting for IPC')
        time.sleep(.3)
    if outputs is None:
        raise RuntimeError('Wayland IPC startup timed out')
    for output in outputs:
        if output['name'].startswith('HEADLESS-'):
            subprocess.run(['swaymsg', 'output', output['name'], 'mode', f'{width}x{height}'], check=True, stdout=subprocess.DEVNULL)
    # IPC discovery is explicit so test runners and VM control can reuse this session.
    (runtime / 'campus-environment.json').write_text(json.dumps({key: os.environ[key] for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR')}))
    apps = {name: spawn([sys.executable, '-u', str(ROOT / 'bin' / name)]) for name in ('cibyp-desktop', 'cibyp-shell')}
    retries = dict.fromkeys(apps, 0)
    while not stopping and compositor.poll() is None:
        for name, child in list(apps.items()):
            if child.poll() is not None:
                retries[name] += 1
                if retries[name] > 5:
                    raise RuntimeError(f'{name} repeatedly exited; inspect the session log')
                print(f'Restarting {name}, exit={child.returncode}', flush=True)
                apps[name] = spawn([sys.executable, '-u', str(ROOT / 'bin' / name)])
        time.sleep(.4)
finally:
    for child in reversed(children):
        if child.poll() is None:
            terminate_owned(child, signal.SIGTERM)
    for child in children:
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            terminate_owned(child, signal.SIGKILL)
    if 'bus_pid' in globals() and bus_pid:
        try:
            os.kill(bus_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    (runtime / 'campus-environment.json').unlink(missing_ok=True)
    (runtime / 'campus-session.pid').unlink(missing_ok=True)
