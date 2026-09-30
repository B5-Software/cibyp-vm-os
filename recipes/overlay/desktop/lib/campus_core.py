"""Desktop state and application operations, independent of GTK and Wayland."""
# SPDX-License-Identifier: GPL-3.0-or-later
import ast
import json
import math
import operator
import os
import re
from pathlib import Path
import shutil
import tempfile

CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'cibyp'
CONFIG_FILE = CONFIG_DIR / 'desktop.json'
DEFAULTS = {
    'theme': 'light', 'accent': 'blue', 'wallpaper': 'campus',
    'show_hidden': False, 'show_desktop_icons': True,
    'pinned': ['files', 'browser', 'terminal', 'editor'],
    'accent_color': None, 'background_color': None, 'appearance_source': 'desktop',
}
ACCENTS = {'blue': '#5279d9', 'mint': '#278877', 'rose': '#c76385',
           'violet': '#8666c4', 'orange': '#bc743b'}
THEME_PALETTES = {
    'light': dict(bg='#f6f7fb', surface='#ffffff', raised='#edf0f6', text='#293347', dim='#738097', line='#dfe5ef', shadow='rgba(55,73,107,0.13)'),
    'dark': dict(bg='#1a2232', surface='#252e41', raised='#303c52', text='#e5ecf8', dim='#a1aec6', line='#3a475f', shadow='rgba(0,0,0,0.28)'),
}


def accent_color(state):
    return state.get('accent_color') or ACCENTS[state['accent']]


def appearance_palette(state):
    palette = dict(THEME_PALETTES[state['theme']])
    if state.get('background_color'):
        background = state['background_color']
        components = [int(background[i:i+2], 16) for i in (1, 3, 5)]
        dark = sum(value*weight for value, weight in zip(components, (.299, .587, .114)))/255 < .5
        def shade(offset):
            return '#' + ''.join(f'{max(0, min(255, value+offset)):02x}' for value in components)
        palette.update(bg=background, surface=shade(20 if dark else -10),
                       raised=shade(30 if dark else -20), line=shade(40 if dark else -5))
    return palette


def atomic_write(path, contents):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_config():
    result = dict(DEFAULTS)
    try:
        value = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
        if isinstance(value, dict):
            result.update(value)
    except (OSError, ValueError):
        pass
    if result.get('theme') not in ('light', 'dark'):
        result['theme'] = 'light'
    if result.get('accent') not in ACCENTS:
        result['accent'] = 'blue'
    for key in ('accent_color', 'background_color'):
        value = result.get(key)
        result[key] = value.lower() if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) else None
    if result.get('appearance_source') not in ('app', 'desktop'):
        result['appearance_source'] = 'desktop'
    if not isinstance(result.get('pinned'), list):
        result['pinned'] = list(DEFAULTS['pinned'])
    result['pinned'] = list(dict.fromkeys(item for item in result['pinned'] if isinstance(item, str) and item in ('files', 'browser', 'terminal', 'editor', 'calc', 'viewer', 'settings', 'about')))
    if result.get('wallpaper') not in ('campus', 'sky', 'notebook'):
        result['wallpaper'] = 'campus'
    return result


def update_config(**changes):
    # A process lock prevents two applications from losing one another's changes.
    import fcntl
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with (CONFIG_DIR / '.settings.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = load_config()
        state.update(changes)
        atomic_write(CONFIG_FILE, json.dumps(state, ensure_ascii=False, indent=2))
        return state


def valid_name(name):
    if not name or name in ('.', '..') or '/' in name or '\0' in name:
        raise ValueError('请输入有效的名称，不能包含路径分隔符')
    return name


def unique_target(directory, name):
    directory = Path(directory)
    valid_name(name)
    target = directory / name
    stem, suffix = Path(name).stem, Path(name).suffix
    index = 1
    while target.exists() or target.is_symlink():
        target = directory / f'{stem} (副本 {index}){suffix}'
        index += 1
    return target


def paste_items(paths, mode, destination):
    destination = Path(destination).resolve()
    results = []
    for value in paths:
        source = Path(value)
        try:
            if not source.exists() and not source.is_symlink():
                raise FileNotFoundError('源文件已经不存在')
            if source.is_dir() and not source.is_symlink():
                if destination == source.resolve() or source.resolve() in destination.parents:
                    raise ValueError('不能把文件夹放进它自身或子目录')
            if mode == 'cut' and source.parent.resolve() == destination:
                results.append((True, str(source)))
                continue
            target = unique_target(destination, source.name)
            if mode == 'cut':
                shutil.move(str(source), str(target))
            elif source.is_dir() and not source.is_symlink():
                shutil.copytree(source, target, symlinks=True)
            else:
                shutil.copy2(source, target, follow_symlinks=False)
            results.append((True, str(target)))
        except (OSError, ValueError, shutil.Error) as error:
            results.append((False, f'{source.name}: {error}'))
    return results


def human_size(size):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024


def evaluate(expression, degrees=False):
    if len(expression) > 256:
        raise ValueError('表达式过长')
    text = expression.replace('×', '*').replace('÷', '/').replace('−', '-').replace('^', '**').replace('π', 'pi')
    tree = ast.parse(text, mode='eval')
    if sum(1 for _ in ast.walk(tree)) > 128:
        raise ValueError('表达式过于复杂')
    binary = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
              ast.Div: operator.truediv, ast.Mod: operator.mod}
    functions = {'sqrt': math.sqrt, 'abs': abs, 'log': math.log10, 'ln': math.log,
                 'sin': math.sin, 'cos': math.cos, 'tan': math.tan, 'exp': math.exp}

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            result = node.value
        elif isinstance(node, ast.Name) and node.id in ('pi', 'e', 'ans'):
            result = {'pi': math.pi, 'e': math.e, 'ans': 0}[node.id]
        elif isinstance(node, ast.UnaryOp) and type(node.op) in (ast.UAdd, ast.USub):
            result = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow):
                if abs(right) > 100 or abs(left) > 1e100:
                    raise ValueError('指数超出计算范围')
                result = left ** right
            elif type(node.op) in binary:
                result = binary[type(node.op)](left, right)
            else:
                raise ValueError('不支持该运算')
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in functions and len(node.args) == 1 and not node.keywords:
            value = visit(node.args[0])
            if degrees and node.func.id in ('sin', 'cos', 'tan'):
                value = math.radians(value)
            result = functions[node.func.id](value)
        else:
            raise ValueError('只支持数字、括号和常用科学函数')
        if isinstance(result, complex) or not math.isfinite(result):
            raise ValueError('结果超出实数计算范围')
        return result
    return visit(tree.body)


def collect_windows(tree):
    windows = []
    def walk(node, workspace=''):
        if node.get('type') == 'workspace':
            workspace = node.get('name', '')
        if node.get('pid') and (node.get('app_id') or node.get('window_properties')):
            app_id = node.get('app_id') or node.get('window_properties', {}).get('class', '')
            if app_id not in ('cibyp-panel', 'cibyp-desktop'):
                windows.append({'id': node['id'], 'pid': node['pid'], 'rect': node.get('rect', {}), 'app_id': app_id, 'title': node.get('name') or app_id,
                                'focused': bool(node.get('focused')), 'workspace': workspace,
                                'minimized': workspace == '__i3_scratch',
                                'visible': bool(node.get('visible'))})
        for key in ('nodes', 'floating_nodes'):
            for child in node.get(key, []):
                walk(child, workspace)
    if isinstance(tree, dict):
        walk(tree)
    return windows
