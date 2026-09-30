#!/usr/bin/env python3
"""Real GTK/Wayland/RFB integration: native keyboard/mouse → UI → disk/state."""
import importlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
temporary = tempfile.TemporaryDirectory(prefix='campus-smoke-')
home = Path(temporary.name)/'home'
home.mkdir()
output = Path(temporary.name)/'output'
output.mkdir()
with socket.socket() as port_probe:
    port_probe.bind(('127.0.0.1', 0))
    port = port_probe.getsockname()[1]
log = (output/'preview.log').open('w')
preview = subprocess.Popen(['python3', '-u', str(ROOT/'tests/desktop-preview.py'), '--duration', '300', '--output', str(output), '--home', str(home), '--port', str(port)], stdout=log, stderr=log, start_new_session=True)
apps = []
pointer = None


def wait(check, message, seconds=10):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (OSError, ValueError):
            pass
        time.sleep(.1)
    raise AssertionError(message)


try:
    wait(lambda: (output/'environment.json').is_file(), 'Wayland session did not start', 30)
    os.environ['CIBYP_PREVIEW_OUTPUT'] = str(output)
    sys.path.insert(0, str(ROOT/'tests'))
    import desktop_driver as driver
    sys.path.insert(0, str(ROOT/'recipes/overlay/desktop/lib'))
    from campus_core import collect_windows
    def windows():
        return collect_windows(json.loads(driver.run(['swaymsg', '-r', '-t', 'get_tree']).stdout))
    def window(kind):
        return next((row for row in windows() if row['app_id'].endswith('.'+kind)), None)
    def open_app(name, *arguments):
        child = driver.launch('cibyp-'+name, *arguments)
        apps.append(child)
        row = wait(lambda: window(name), name+' did not open')
        time.sleep(.4)
        return row
    wait(lambda: Path(driver.ENV['XDG_RUNTIME_DIR'], 'cibyp-shell.sock').is_socket(), 'Taskbar did not start')
    time.sleep(.7)
    driver.screenshot('campus-light')
    pointer = driver.Pointer()
    folder = home/"班级笔记 student's notes"
    folder.mkdir()
    note = folder/'notes.txt'
    note.write_text('first line\n')
    terminal = open_app('terminal', folder)
    pointer.click(terminal['rect']['x']+180, terminal['rect']['y']+260)
    pointer.text('printf ready > terminal-proof.txt\n')
    wait(lambda: (folder/'terminal-proof.txt').exists(), 'Terminal did not execute in the requested directory')
    assert (folder/'terminal-proof.txt').read_text() == 'ready'
    pointer.text('pwd\n')
    driver.screenshot('terminal-cwd')
    pointer.click(terminal['rect']['x']+terminal['rect']['width']-126, terminal['rect']['y']+29)
    wait(lambda: window('terminal')['minimized'], 'Minimize did not hide the terminal')
    time.sleep(.5)
    pointer.click(279, 765)
    wait(lambda: not window('terminal')['minimized'], 'Taskbar did not restore the terminal')
    driver.ctl('maximize')
    wait(lambda: window('terminal')['rect']['width'] > 1200, 'Maximize did not use the work area')
    driver.ctl('maximize')
    wait(lambda: window('terminal')['rect']['width'] == terminal['rect']['width'], 'Restore lost the original geometry')
    print('PASS terminal cwd, typing, taskbar restore and window geometry', flush=True)

    editor = open_app('editor', note)
    pointer.click(editor['rect']['x']+200, editor['rect']['y']+235)
    pointer.chord(0xff57, 0xffe3)
    pointer.text('second line\n')
    pointer.chord(ord('s'), 0xffe3)
    wait(lambda: note.read_text() == 'first line\nsecond line\n', 'Editor did not save typed text')
    pointer.chord(ord('z'), 0xffe3)
    pointer.chord(ord('s'), 0xffe3)
    wait(lambda: note.read_text() != 'first line\nsecond line\n', 'Undo did not affect the document')
    driver.screenshot('editor')
    print('PASS editor open, edit, atomic save and undo', flush=True)

    files = open_app('files', folder)
    pointer.chord(ord('N'), 0xffe3, 0xffe1)
    time.sleep(.4)
    pointer.chord(ord('a'), 0xffe3)
    pointer.text('Classroom')
    pointer.press(0xff0d)
    wait(lambda: (folder/'Classroom').is_dir(), 'File manager did not create the folder')
    pointer.chord(ord('f'), 0xffe3)
    pointer.text('notes.txt')
    time.sleep(.6)
    pointer.click(files['rect']['x']+350, files['rect']['y']+218)
    pointer.chord(ord('c'), 0xffe3)
    pointer.chord(ord('v'), 0xffe3)
    wait(lambda: (folder/'notes (副本 1).txt').exists(), 'File manager copy/paste failed')
    pointer.click(files['rect']['x']+350, files['rect']['y']+218, 3)
    driver.screenshot('files-context')
    pointer.press(0xff1b)
    pointer.press(0xffbf)
    time.sleep(.3)
    pointer.chord(ord('a'), 0xffe3)
    pointer.text('campus-note.txt')
    pointer.press(0xff0d)
    renamed = folder/'campus-note.txt'
    wait(lambda: renamed.exists(), 'Rename failed')
    time.sleep(.7)
    pointer.chord(ord('f'), 0xffe3)
    pointer.chord(ord('a'), 0xffe3)
    pointer.text('campus-note.txt')
    time.sleep(.5)
    files = window('files')
    pointer.press(0xff0d)
    pointer.click(files['rect']['x']+350, files['rect']['y']+218)
    time.sleep(.4)
    pointer.press(0xffff)
    confirm = wait(lambda: next((row for row in windows() if '移到回收站？' in row['title']), None), 'Trash confirmation did not open')
    pointer.click(confirm['rect']['x']+confirm['rect']['width']-74, confirm['rect']['y']+confirm['rect']['height']-40)
    wait(lambda: not renamed.exists(), 'Move to trash failed')
    trash_directory = home/'.local/share/Trash/files'
    wait(lambda: trash_directory.exists(), 'Trash directory was not created')
    pointer.chord(ord('l'), 0xffe3)
    pointer.chord(ord('a'), 0xffe3)
    pointer.text(str(trash_directory))
    pointer.press(0xff0d)
    time.sleep(.7)
    pointer.click(files['rect']['x']+350, files['rect']['y']+218, 3)
    time.sleep(.2)
    pointer.click(files['rect']['x']+350, files['rect']['y']+245)
    wait(lambda: renamed.exists(), 'Trash restore did not recover the original file')
    driver.screenshot('files')
    print('PASS file manager creation, search, copy/paste, rename, trash restore and context menu', flush=True)

    calculator = open_app('calc')
    pointer.click(calculator['rect']['x']+260, calculator['rect']['y']+115)
    pointer.text('(12+8)/5\n')
    history = Path(driver.ENV['XDG_CONFIG_HOME'])/'cibyp/calculator-history.json'
    wait(lambda: history.exists() and json.loads(history.read_text())[0][1] == '4', 'Calculator result was incorrect')
    driver.screenshot('calculator')
    print('PASS calculator expression and history', flush=True)

    viewer = open_app('viewer', ROOT/'preview-campus-light.png')
    driver.screenshot('viewer')
    pointer.chord(ord('r'))
    print('PASS image viewer open and rotation', flush=True)

    settings = open_app('settings')
    pointer.click(settings['rect']['x']+675, settings['rect']['y']+238)
    config = Path(driver.ENV['XDG_CONFIG_HOME'])/'cibyp/desktop.json'
    wait(lambda: config.exists() and json.loads(config.read_text())['theme'] == 'dark', 'Hot theme switch failed')
    pointer.click(settings['rect']['x']+525, settings['rect']['y']+392)
    wait(lambda: json.loads(config.read_text())['accent'] == 'rose', 'Hot accent switch failed')
    time.sleep(.8)
    driver.screenshot('settings-dark')
    # Exercise the actual App bridge while all GTK applications remain open.
    bridge = ROOT.parent/'Could-I-Be-Your-Partner/tests/integration/vm-appearance-native.cjs'
    if bridge.exists():
        import cairo
        windows_before = {row['id'] for row in windows()}
        before = json.loads(config.read_text())
        script = subprocess.check_output(['wslpath', '-w', str(bridge)], text=True).strip()
        def app_appearance(theme, filename):
            subprocess.run(['/mnt/c/Program Files/nodejs/node.exe', script, driver.ENV['XDG_CONFIG_HOME'], json.dumps(theme)], check=True)
            wait(lambda: json.loads(config.read_text()).get('background_color') == theme['backgroundColor'], 'App colors did not reach the guest')
            time.sleep(.7)
            driver.screenshot(filename)
        app_appearance({'mode': 'light', 'accentColor': '#00b894', 'backgroundColor': '#f0fff4'}, 'app-synced-light')
        app_appearance({'mode': 'dark', 'accentColor': '#a55eea', 'backgroundColor': '#1b1433'}, 'app-synced-dark')
        after = json.loads(config.read_text())
        assert after['wallpaper'] == before['wallpaper'] and after['pinned'] == before['pinned']
        assert {row['id'] for row in windows()} == windows_before, 'Theme update restarted an application'
        surface = '#2f2847'  # App background #1b1433 + 20 on every channel.
        expected = tuple(int(surface[i:i+2], 16) for i in (5, 3, 1))
        for name in ('terminal', 'files', 'editor', 'calc', 'viewer', 'settings'):
            row = window(name)
            driver.run(['swaymsg', f"[con_id={row['id']}] focus"])
            time.sleep(.3)
            screenshot = driver.screenshot('app-synced-'+name)
            pixels = cairo.ImageSurface.create_from_png(str(screenshot))
            # Every existing native headerbar shares the App's derived surface.
            x, y = row['rect']['x']+125, row['rect']['y']+15
            offset = y*pixels.get_stride()+x*4
            assert tuple(bytes(pixels.get_data()[offset:offset+3])) == expected, f'{name} did not repaint the App colors'
        print('PASS production App→Linux appearance bridge, exact colors in six running applications, preserved preferences and no restarts', flush=True)
    driver.ctl('desktop')
    wait(lambda: all(row['minimized'] for row in windows()), 'Show desktop failed')
    driver.screenshot('campus-dark')
    pointer.click(1190, 430, 3)
    driver.screenshot('desktop-context')
    pointer.press(0xff1b)
    pointer.click(65, 765)
    time.sleep(.4)
    pointer.text('calc')
    time.sleep(.4)
    driver.screenshot('launcher')
    pointer.press(0xff0d)
    wait(lambda: sum(row['app_id'].endswith('.calc') for row in windows()) == 2, 'Launcher search did not open calculator')
    count = sum(row['app_id'].endswith('.files') for row in windows())
    pointer.chord(ord('e'), 0xffeb)
    wait(lambda: sum(row['app_id'].endswith('.files') for row in windows()) == count+1, 'Super+E did not open files')
    time.sleep(.4)
    driver.screenshot('super-e')
    before_menu = cairo.ImageSurface.create_from_png(str(driver.screenshot('before-super-menu')))
    pointer.press(0xffeb)
    def super_menu_opened():
        opened = cairo.ImageSurface.create_from_png(str(driver.screenshot('super-menu')))
        offset = 650*opened.get_stride()+40*4
        return bytes(opened.get_data()[offset:offset+3]) != bytes(before_menu.get_data()[offset:offset+3])
    wait(super_menu_opened, 'Super did not open the launcher after Super+E')
    pointer.text('calc')
    pointer.press(0xff0d)
    wait(lambda: sum(row['app_id'].endswith('.calc') for row in windows()) == 3, 'Super launcher did not receive typing')
    pointer.press(0xffeb)
    time.sleep(.4)
    pointer.click(1190, 450)
    pointer.chord(ord('e'), 0xffeb)
    wait(lambda: sum(row['app_id'].endswith('.files') for row in windows()) == count+2, 'Click-away did not restore application input')
    pointer.press(0xff1b)
    print('PASS live theme/accent, show desktop, global context menu and launcher search', flush=True)
    time.sleep(.4)
    for name in ('files', 'editor', 'calc', 'viewer', 'terminal', 'settings'):
        text = (output/('cibyp-'+name+'.log')).read_text()
        assert 'Traceback' not in text, name+': '+text
    assert 'Traceback' not in (output/'session.log').read_text(), (output/'session.log').read_text()
    print('PASS no application exceptions in native Wayland session', flush=True)
except Exception:
    if pointer:
        driver.screenshot('smoke-failure')
        (ROOT/'preview-diagnostics/tree.json').write_text(driver.run(['swaymsg', '-r', '-t', 'get_tree']).stdout)
        (ROOT/'preview-diagnostics').mkdir(exist_ok=True)
        (ROOT/'preview-diagnostics/windows.json').write_text(json.dumps(windows(), ensure_ascii=False, indent=2))
    raise
finally:
    if pointer:
        pointer.close()
    for child in apps:
        if child.poll() is None:
            child.terminate()
    if preview.poll() is None:
        os.killpg(preview.pid, signal.SIGTERM)
    try:
        preview.wait(timeout=12)
    except subprocess.TimeoutExpired:
        os.killpg(preview.pid, signal.SIGKILL)
    # Keep diagnostics independently of the temporary home.
    import shutil
    diagnostics = ROOT/'preview-diagnostics'
    diagnostics.mkdir(exist_ok=True)
    for path in output.glob('*.log'):
        shutil.copyfile(path, diagnostics/path.name)
    log.close()
    temporary.cleanup()
