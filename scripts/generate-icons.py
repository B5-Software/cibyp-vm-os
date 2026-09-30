#!/usr/bin/env python3
"""Generate the same vector app icons used by native Campus widgets."""
from pathlib import Path
import sys
import cairo
root = Path(__file__).resolve().parent.parent / 'recipes/overlay/desktop'
sys.path.insert(0, str(root/'lib'))
from campus_icons import draw_icon, _round_rect

icons = {'files': ('folder', '#e6ae55'), 'editor': ('editor', '#66a6bc'), 'browser': ('browser', '#6a94de'), 'terminal': ('terminal', '#566583'), 'settings': ('settings', '#9d8cca'), 'calc': ('calc', '#dd92a9'), 'viewer': ('image', '#75a98c'), 'about': ('info', '#7694bd')}
directory = root/'icons'
directory.mkdir(exist_ok=True)
for name, (glyph, color) in icons.items():
    surface = cairo.SVGSurface(str(directory/('cibyp-'+name+'.svg')), 64, 64)
    context = cairo.Context(surface)
    context.set_source_rgb(*(int(color[index:index+2], 16)/255 for index in (1, 3, 5)))
    _round_rect(context, 2, 2, 60, 60, 15)
    context.fill()
    context.set_source_rgba(1, 1, 1, .2)
    _round_rect(context, 6, 6, 52, 23, 12)
    context.fill()
    draw_icon(context, glyph, 13, 13, 38, (1, 1, 1), 1.7)
    surface.finish()
    entry = root/'applications'/('cibyp-'+name+'.desktop')
    if entry.exists():
        text = entry.read_text()
        text = '\n'.join('Icon=cibyp-'+name if line.startswith('Icon=') else line for line in text.splitlines())+'\n'
        text = text.replace(' %U', ' %F').replace(' %u', ' %f')
        entry.write_text(text)
