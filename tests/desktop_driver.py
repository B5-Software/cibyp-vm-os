#!/usr/bin/env python3
"""Small real Wayland/RFB driver for reproducible application smoke checks."""
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time

OUTPUT = Path(os.environ.get('CIBYP_PREVIEW_OUTPUT', '/tmp/cibyp-campus-preview'))
ENV = json.loads((OUTPUT / 'environment.json').read_text())
ENV.update(GSK_RENDERER='cairo', GTK_A11Y='none', GDK_BACKEND='wayland')
ROOT = Path(__file__).resolve().parent.parent


def run(argv, **kwargs):
    return subprocess.run(argv, env=ENV, check=True, capture_output=True, text=True, **kwargs)


def launch(name, *args):
    log = (OUTPUT / (name + '.log')).open('w')
    return subprocess.Popen(['python3', '-u', str(ROOT / 'recipes/overlay/desktop/bin' / name), *map(str, args)], env=ENV, stdout=log, stderr=log)


def ctl(value):
    with socket.socket(socket.AF_UNIX) as client:
        client.connect(str(Path(ENV['XDG_RUNTIME_DIR']) / 'cibyp-shell.sock'))
        client.sendall(value.encode())
    time.sleep(.3)


def screenshot(name):
    target = ROOT / ('preview-' + name + '.png')
    run(['grim', str(target)])
    return target


def keys(*args):
    run(['wtype', '-s', '250', '-d', '20', *args])
    time.sleep(.2)


def exact(sock, count):
    result = b''
    while len(result) < count:
        value = sock.recv(count-len(result))
        if not value:
            raise RuntimeError('VNC closed unexpectedly')
        result += value
    return result


class Pointer:
    def __init__(self):
        self.socket = socket.create_connection(('127.0.0.1', int(ENV.get('CIBYP_PREVIEW_PORT', 5909))), timeout=3)
        exact(self.socket, 12)
        self.socket.sendall(b'RFB 003.008\n')
        count = exact(self.socket, 1)[0]
        types = exact(self.socket, count)
        if 1 not in types:
            raise RuntimeError('Isolated preview must allow local unauthenticated VNC')
        self.socket.sendall(b'\x01')
        if exact(self.socket, 4) != b'\0\0\0\0':
            raise RuntimeError('VNC rejected connection')
        self.socket.sendall(b'\x01')
        header = exact(self.socket, 24)
        exact(self.socket, struct.unpack('!I', header[20:24])[0])

    def click(self, x, y, button=1):
        for mask in (0, 1 << (button-1), 0):
            self.socket.sendall(struct.pack('!BBHH', 5, mask, x, y))
            time.sleep(.07)
        time.sleep(.25)

    def key(self, keysym, down=True):
        self.socket.sendall(struct.pack('!BBHI', 4, int(down), 0, keysym))
        time.sleep(.025)

    def press(self, keysym):
        self.key(keysym)
        self.key(keysym, False)

    def text(self, value):
        for character in value:
            value = ord(character)
            self.press(0xff0d if character == '\n' else value if value < 128 else 0x01000000 | value)
        time.sleep(.25)

    def chord(self, key, *modifiers):
        for modifier in modifiers:
            self.key(modifier)
        self.press(key)
        for modifier in reversed(modifiers):
            self.key(modifier, False)
        time.sleep(.3)

    def close(self):
        self.socket.close()


if __name__ == '__main__':
    # Run as the same unprivileged desktop user.
    apps = [launch(name) for name in ('cibyp-files', 'cibyp-editor', 'cibyp-calc', 'cibyp-settings', 'cibyp-terminal')]
    time.sleep(3)
    print(run(['swaymsg', '-r', '-t', 'get_tree']).stdout)
    for name in ('cibyp-files', 'cibyp-editor', 'cibyp-calc', 'cibyp-settings', 'cibyp-terminal'):
        print(name, (OUTPUT/(name+'.log')).read_text()[-3000:])
    screenshot('apps')
