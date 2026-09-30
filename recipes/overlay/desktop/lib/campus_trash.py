"""Freedesktop trash recovery. Never overwrite an existing original file."""
from configparser import ConfigParser
import os
from pathlib import Path
import shutil
from urllib.parse import unquote
from campus_core import unique_target


def trash_root():
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share'))) / 'Trash'


def original_path(path):
    metadata = path.parent.parent / 'info' / (path.name + '.trashinfo')
    parser = ConfigParser(interpolation=None)
    parser.read(metadata, encoding='utf-8')
    original = Path(unquote(parser.get('Trash Info', 'Path')))
    if not original.is_absolute():
        raise ValueError('回收站记录中的原位置无效')
    return original, metadata


def restore(paths):
    results = []
    for path in paths:
        try:
            original, metadata = original_path(path)
            original.parent.mkdir(parents=True, exist_ok=True)
            target = unique_target(original.parent, original.name)
            shutil.move(str(path), str(target))
            metadata.unlink(missing_ok=True)
            results.append((True, str(target)))
        except Exception as error:
            results.append((False, f'{path.name}: {error}'))
    return results
