#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Start the image's pinned remote extension host as the signed-in guest user."""
import fcntl
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

ROOT = Path('/usr/local/lib/cibyp-codeoss/current').resolve()


def alive(state):
    try:
        pid = int(state['pid'])
        proc = Path('/proc') / str(pid)
        if proc.stat().st_uid != os.getuid():
            return False
        if str(ROOT / 'out/server-main.js').encode() not in (proc / 'cmdline').read_bytes().split(b'\0'):
            return False
        with socket.create_connection(('127.0.0.1', int(state['port'])), timeout=1):
            return True
    except (KeyError, ValueError, OSError):
        return False


def start(commit, token):
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or not re.fullmatch(r'[0-9a-f]{64}', token):
        raise ValueError('Invalid commit or connection token')
    product = json.loads((ROOT / 'product.json').read_text())
    if product.get('commit') != commit:
        raise ValueError('Code-OSS client/server version mismatch; update the CIBYP OS image')
    state_dir = Path.home() / '.local/state/cibyp/codeoss' / commit
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if state_dir.is_symlink() or state_dir.stat().st_uid != os.getuid():
        raise ValueError('Unsafe server state directory')
    state_dir.chmod(0o700)
    os.umask(0o077)
    with (state_dir / 'launch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state_file = state_dir / 'server.json'
        try:
            state = json.loads(state_file.read_text())
            if state.get('commit') == commit and alive(state):
                return {key: state[key] for key in ('commit', 'port', 'token')}
        except (OSError, ValueError, KeyError):
            pass
        token_file = state_dir / 'connection-token'
        token_file.write_text(token)
        token_file.chmod(0o600)
        log_file = state_dir / 'server.log'
        with log_file.open('w') as log:
            process = subprocess.Popen([
                str(ROOT / 'node'), str(ROOT / 'out/server-main.js'),
                '--start-server', '--host', '127.0.0.1', '--port', '0',
                '--connection-token-file', str(token_file),
                '--server-data-dir', str(state_dir / 'data'),
                '--telemetry-level', 'off',
            ], stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True, cwd=Path.home())
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Code-OSS server exited; inspect ' + str(log_file))
            match = re.search(r'Extension host agent listening on (\d+)', log_file.read_text(errors='replace'))
            if match:
                state = {'commit': commit, 'port': int(match[1]), 'token': token, 'pid': process.pid}
                if alive(state):
                    temporary = state_dir / 'server.json.partial'
                    temporary.write_text(json.dumps(state))
                    temporary.replace(state_file)
                    return {key: state[key] for key in ('commit', 'port', 'token')}
            time.sleep(0.1)
        process.terminate()
        raise TimeoutError('Code-OSS server did not become ready; inspect ' + str(log_file))


if __name__ == '__main__':
    try:
        if len(sys.argv) != 4 or sys.argv[1] != '--cibyp-start':
            raise ValueError('Usage: cibyp-codeoss-server --cibyp-start <commit> <token>')
        print(json.dumps(start(sys.argv[2], sys.argv[3])), flush=True)
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
