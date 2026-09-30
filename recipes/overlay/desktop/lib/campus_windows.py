"""Window behavior is owned by the compositor and remains consistent across apps."""
import json
import subprocess
from campus_core import collect_windows


def query(kind):
    return json.loads(subprocess.check_output(['swaymsg', '-r', '-t', kind], timeout=2))


def command(value):
    result = json.loads(subprocess.check_output(['swaymsg', '-r', value], timeout=2))
    if any(not row.get('success') for row in result):
        raise RuntimeError('; '.join(row.get('error', '窗口操作失败') for row in result if not row.get('success')))


class WindowManager:
    def __init__(self):
        self.restores, self.desktop_hidden = {}, []

    def snapshot(self):
        return collect_windows(query('get_tree'))

    def focused(self, pid=None):
        rows = [row for row in self.snapshot() if pid is None or row['pid'] == pid]
        return next((row for row in rows if row['focused']), rows[0] if rows else None)

    def restore(self, row):
        if row['minimized']:
            command(f'[con_id={row["id"]}] scratchpad show')
        else:
            command(f'[con_id={row["id"]}] focus')

    def minimize(self, row=None):
        row = row or self.focused()
        if row and not row['minimized']:
            command(f'[con_id={row["id"]}] move scratchpad')

    def maximize(self, row=None):
        row = row or self.focused()
        if not row:
            return
        self.restore(row)
        identifier = row['id']
        if identifier in self.restores:
            rect = self.restores.pop(identifier)
        else:
            self.restores[identifier] = row['rect']
            outputs = query('get_outputs')
            area = next((output['rect'] for output in outputs if output.get('focused')), outputs[0]['rect'])
            rect = dict(x=area['x']+4, y=area['y']+4, width=area['width']-8, height=area['height']-72)
        command(f'[con_id={identifier}] floating enable, resize set {rect["width"]} px {rect["height"]} px, move position {rect["x"]} px {rect["y"]} px')

    def snap(self, direction):
        row = self.focused()
        if not row:
            return
        outputs = query('get_outputs')
        area = next((output['rect'] for output in outputs if output.get('focused')), outputs[0]['rect'])
        self.restores.setdefault(row['id'], row['rect'])
        width = area['width']//2-9
        x = area['x'] + (area['width']//2+4 if direction == 'right' else 4)
        command(f'[con_id={row["id"]}] floating enable, resize set {width} px {area["height"]-72} px, move position {x} px {area["y"]+4} px')

    def show_desktop(self):
        rows = self.snapshot()
        if self.desktop_hidden:
            existing = {row['id']: row for row in rows}
            for identifier in self.desktop_hidden:
                row = existing.get(identifier)
                if row and row['minimized']:
                    self.restore(row)
            self.desktop_hidden = []
        else:
            workspace = next((row['name'] for row in query('get_workspaces') if row['focused']), '')
            visible = [row for row in rows if row['workspace'] == workspace and not row['minimized']]
            self.desktop_hidden = [row['id'] for row in visible]
            for row in visible:
                self.minimize(row)

    def cycle(self, backwards=False):
        # Creation order is stable; stacking/focus changes do not make Alt+Tab bounce.
        rows = sorted(self.snapshot(), key=lambda row: row['id'])
        if not rows:
            return
        current = next((index for index, row in enumerate(rows) if row['focused']), -1)
        self.restore(rows[(current + (-1 if backwards else 1)) % len(rows)])
