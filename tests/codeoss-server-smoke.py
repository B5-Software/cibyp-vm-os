#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the actual bundled server without touching the user's IDE profile."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import tempfile

spec = importlib.util.spec_from_file_location('cibyp_server', Path(__file__).parents[1] / 'recipes/overlay/codeoss/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
if len(sys.argv) > 1:
    server.ROOT = Path(sys.argv[1]).resolve()
commit = json.loads((server.ROOT / 'product.json').read_text())['commit']
with tempfile.TemporaryDirectory(prefix='cibyp-codeoss-check-') as temporary:
    os.environ['HOME'] = temporary
    state_dir = Path(temporary) / '.local/state/cibyp/codeoss' / commit
    try:
        first = server.start(commit, '1' * 64)
        second = server.start(commit, '2' * 64)
        assert first == second, 'Reconnect must reuse the server and its valid token'
        assert (state_dir / 'connection-token').stat().st_mode & 0o777 == 0o600
        assert (state_dir / 'server.json').stat().st_mode & 0o777 == 0o600
        assert server.alive(json.loads((state_dir / 'server.json').read_text()))
        try:
            server.start('0' * 40, '1' * 64)
            raise AssertionError('Mismatched desktop commit must be rejected')
        except ValueError:
            pass
        print('PASS actual Code-OSS server, private token/state, reconnect and commit mismatch')
    finally:
        if (state_dir / 'server.json').exists():
            state = json.loads((state_dir / 'server.json').read_text())
            if server.alive(state):
                os.kill(state['pid'], signal.SIGTERM)
