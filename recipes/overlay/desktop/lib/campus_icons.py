# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 B5-Software
import math

_ICON_STROKE = 1.9
TEXT = (0.18, 0.23, 0.31)

def rgba(value, alpha=None):
    return (*value[:3], 1.0 if alpha is None else alpha)

def _stroke(cr, color, width=_ICON_STROKE):
    cr.set_source_rgba(*rgba(color))
    cr.set_line_width(width)
    cr.set_line_cap(1)  # ROUND
    cr.set_line_join(1)


def draw_icon(cr, name, x, y, size, color=TEXT, stroke=_ICON_STROKE):
    """在 (x, y, size, size) 区域绘制线性图标（自绘，无资源依赖）"""
    cr.save()
    cr.translate(x, y)
    s = size / 24.0
    cr.scale(s, s)
    _stroke(cr, color, stroke)
    n = name

    def rect(rx, ry, rw, rh, r=3):
        _round_rect(cr, rx, ry, rw, rh, r)
        cr.stroke()

    def fill_rect(rx, ry, rw, rh, r=3):
        _round_rect(cr, rx, ry, rw, rh, r)
        cr.set_source_rgba(*rgba(color))
        cr.fill()

    if n in ('terminal', 'console'):
        rect(2.5, 4, 19, 16, 3)
        cr.move_to(6.5, 9.5); cr.line_to(9.5, 12); cr.line_to(6.5, 14.5); cr.stroke()
        cr.move_to(11.5, 15); cr.line_to(17, 15); cr.stroke()
    elif n in ('files', 'folder'):
        cr.move_to(3, 7.5); cr.line_to(3, 19); cr.line_to(21, 19); cr.line_to(21, 8.5)
        cr.line_to(12, 8.5); cr.line_to(10, 6); cr.line_to(3, 6); cr.close_path(); cr.stroke()
    elif n == 'editor':
        rect(4, 3.5, 16, 17, 3)
        cr.move_to(8, 8.5); cr.line_to(16, 8.5); cr.stroke()
        cr.move_to(8, 12); cr.line_to(16, 12); cr.stroke()
        cr.move_to(8, 15.5); cr.line_to(13, 15.5); cr.stroke()
    elif n == 'settings':
        cr.arc(12, 12, 3.2, 0, math.pi * 2); cr.stroke()
        for i in range(8):
            a = i * math.pi / 4
            cr.move_to(12 + math.cos(a) * 6.2, 12 + math.sin(a) * 6.2)
            cr.line_to(12 + math.cos(a) * 8.6, 12 + math.sin(a) * 8.6)
        cr.stroke()
        cr.arc(12, 12, 8.6, 0, math.pi * 2); cr.stroke()
    elif n == 'calc':
        rect(5, 3, 14, 18, 3)
        fill_rect(7.5, 6, 9, 3.4, 1.5)
        for ry in (12.5, 16):
            for rx in (7.5, 11.5, 15.5):
                cr.arc(rx, ry, 1.05, 0, math.pi * 2); cr.fill()
    elif n == 'viewer':
        rect(3, 5, 18, 14, 3)
        cr.move_to(6, 15.5); cr.line_to(10, 11.5); cr.line_to(13, 14); cr.line_to(16, 10.5); cr.line_to(18, 15.5)
        cr.stroke()
        cr.arc(8.2, 9.2, 1.3, 0, math.pi * 2); cr.stroke()
    elif n in ('browser', 'globe'):
        cr.arc(12, 12, 8.6, 0, math.pi * 2); cr.stroke()
        cr.move_to(3.4, 12); cr.line_to(20.6, 12); cr.stroke()
        cr.save(); cr.translate(12, 12); cr.scale(0.45, 1); cr.arc(0, 0, 8.6, 0, math.pi * 2); cr.restore(); cr.stroke()
    elif n in ('menu', 'apps'):
        for ry in (6.5, 12, 17.5):
            for rx in (5.5, 12, 18.5):
                cr.arc(rx, ry, 1.55, 0, math.pi * 2); cr.fill()
    elif n in ('power', 'shutdown'):
        cr.arc(12, 12.6, 7.2, -math.pi * 0.32, math.pi * 1.32); cr.stroke()
        cr.move_to(12, 3.2); cr.line_to(12, 11.4); cr.stroke()
    elif n == 'reboot':
        cr.arc(12, 12, 7.4, math.pi * 0.35, math.pi * 1.65); cr.stroke()
        cr.move_to(17.4, 5.6); cr.line_to(18.4, 10.4); cr.line_to(13.6, 9.4); cr.close_path()
        cr.set_source_rgba(*rgba(color)); cr.fill()
    elif n == 'close':
        cr.move_to(6.4, 6.4); cr.line_to(17.6, 17.6); cr.stroke()
        cr.move_to(17.6, 6.4); cr.line_to(6.4, 17.6); cr.stroke()
    elif n == 'minimize':
        cr.move_to(6.5, 15.5); cr.line_to(17.5, 15.5); cr.stroke()
    elif n == 'maximize':
        rect(6, 6, 12, 12, 2.5)
    elif n == 'restore':
        rect(8, 5.5, 10.5, 10.5, 2.5)
        cr.move_to(5.5, 8.5); cr.line_to(5.5, 18.5); cr.line_to(15.5, 18.5); cr.stroke()
    elif n == 'search':
        cr.arc(10.8, 10.8, 5.6, 0, math.pi * 2); cr.stroke()
        cr.move_to(15.2, 15.2); cr.line_to(20, 20); cr.stroke()
    elif n == 'file':
        cr.move_to(6, 3.5); cr.line_to(14, 3.5); cr.line_to(18, 7.5); cr.line_to(18, 20.5); cr.line_to(6, 20.5)
        cr.close_path(); cr.stroke()
        cr.move_to(14, 3.5); cr.line_to(14, 7.5); cr.line_to(18, 7.5); cr.stroke()
    elif n == 'home':
        cr.move_to(3.5, 11.5); cr.line_to(12, 4); cr.line_to(20.5, 11.5); cr.stroke()
        cr.move_to(6, 11); cr.line_to(6, 20); cr.line_to(18, 20); cr.line_to(18, 11); cr.stroke()
    elif n == 'back':
        cr.move_to(14.5, 5.5); cr.line_to(8, 12); cr.line_to(14.5, 18.5); cr.stroke()
    elif n == 'forward':
        cr.move_to(9.5, 5.5); cr.line_to(16, 12); cr.line_to(9.5, 18.5); cr.stroke()
    elif n == 'up':
        cr.move_to(5.5, 14.5); cr.line_to(12, 8); cr.line_to(18.5, 14.5); cr.stroke()
    elif n in ('plus', 'add'):
        cr.move_to(12, 5.5); cr.line_to(12, 18.5); cr.stroke()
        cr.move_to(5.5, 12); cr.line_to(18.5, 12); cr.stroke()
    elif n == 'down':
        cr.move_to(12, 4); cr.line_to(12, 16); cr.stroke()
        cr.move_to(6, 11); cr.line_to(12, 17); cr.line_to(18, 11); cr.stroke()
        cr.move_to(5, 20); cr.line_to(19, 20); cr.stroke()
    elif n == 'history':
        cr.arc(12, 12, 8, -.4, math.pi*1.6); cr.stroke()
        cr.move_to(12, 7); cr.line_to(12, 12); cr.line_to(16, 14); cr.stroke()
        cr.move_to(3, 6); cr.line_to(3, 11); cr.line_to(8, 11); cr.stroke()
    elif n == 'play':
        cr.move_to(8, 4); cr.line_to(20, 12); cr.line_to(8, 20); cr.close_path(); cr.stroke()
    elif n == 'trash':
        cr.move_to(5.5, 7); cr.line_to(18.5, 7); cr.stroke()
        cr.move_to(9.5, 7); cr.line_to(9.8, 4.5); cr.line_to(14.2, 4.5); cr.line_to(14.5, 7); cr.stroke()
        cr.move_to(7, 7); cr.line_to(7.9, 20); cr.line_to(16.1, 20); cr.line_to(17, 7); cr.stroke()
    elif n == 'refresh':
        cr.arc(12, 12, 7.2, math.pi * 0.25, math.pi * 1.75); cr.stroke()
        cr.move_to(4.4, 6.2); cr.line_to(5.4, 11.6); cr.line_to(10.6, 10.2); cr.close_path()
        cr.set_source_rgba(*rgba(color)); cr.fill()
    elif n in ('wallpaper', 'image'):
        rect(3.5, 5, 17, 14, 3)
        cr.move_to(6, 15.8); cr.line_to(10.5, 10.8); cr.line_to(14, 13.8); cr.line_to(17.8, 9.4); cr.stroke()
    elif n == 'info':
        cr.arc(12, 12, 8.6, 0, math.pi * 2); cr.stroke()
        cr.arc(12, 7.8, 1.15, 0, math.pi * 2); cr.fill()
        cr.move_to(12, 11); cr.line_to(12, 17); cr.stroke()
    elif n in ('volume', 'speaker'):
        cr.move_to(4.5, 10); cr.line_to(8, 10); cr.line_to(12, 6.5); cr.line_to(12, 17.5); cr.line_to(8, 14); cr.line_to(4.5, 14)
        cr.close_path(); cr.stroke()
        cr.arc(13.5, 12, 4.2, -math.pi * 0.5, math.pi * 0.5); cr.stroke()
    elif n == 'wifi':
        for r, a in ((8.4, 0.35), (5.8, 0.6), (3.2, 0.9)):
            cr.arc(12, 17.5, r, math.pi * 1.15, math.pi * 1.85); cr.stroke()
        cr.arc(12, 17, 1.15, 0, math.pi * 2); cr.fill()
    elif n == 'battery':
        rect(3, 8, 15, 8, 2.5)
        fill_rect(19, 10.6, 2, 2.8, 1)
        fill_rect(5, 10, 6, 4, 1.2)
    elif n == 'user':
        cr.arc(12, 8.6, 3.6, 0, math.pi * 2); cr.stroke()
        cr.arc(12, 20, 7.2, math.pi * 1.15, math.pi * 1.85); cr.stroke()
    elif n == 'grid':
        for ry in (5, 12.5):
            for rx in (5, 12.5):
                rect(rx, ry, 6.5, 6.5, 2)
    elif n == 'cut':
        cr.move_to(6.5, 4.5); cr.line_to(15.5, 17.5); cr.stroke()
        cr.move_to(17.5, 4.5); cr.line_to(8.5, 17.5); cr.stroke()
        cr.arc(6.4, 19, 2.4, 0, math.pi * 2); cr.stroke()
        cr.arc(17.6, 19, 2.4, 0, math.pi * 2); cr.stroke()
    elif n == 'copy':
        rect(7.5, 7.5, 12, 12, 2.5)
        cr.move_to(4.5, 15.5); cr.line_to(4.5, 4.5); cr.line_to(15.5, 4.5); cr.stroke()
    elif n == 'paste':
        rect(5, 6, 14, 15, 3)
        fill_rect(9, 3.5, 6, 4, 1.5)
    elif n == 'edit':
        cr.move_to(5, 19); cr.line_to(6.2, 14.6); cr.line_to(16.2, 4.6); cr.line_to(19.4, 7.8)
        cr.line_to(9.4, 17.8); cr.close_path(); cr.stroke()
    elif n == 'save':
        cr.move_to(4.5, 6); cr.line_to(4.5, 19.5); cr.line_to(19.5, 19.5); cr.line_to(19.5, 9.5); cr.line_to(15.5, 4.5)
        cr.line_to(4.5, 4.5); cr.close_path(); cr.stroke()
        rect(8, 4.5, 7, 5, 1.2)
    elif n == 'open':
        cr.move_to(4, 10); cr.line_to(20, 10); cr.stroke()
        cr.move_to(6, 10); cr.line_to(8.5, 19.5); cr.line_to(20.5, 19.5); cr.line_to(20, 10); cr.stroke()
        cr.move_to(7, 10); cr.line_to(7, 5.5); cr.line_to(13, 5.5); cr.stroke()
    elif n in ('window', 'desktop'):
        rect(3, 5, 18, 14, 3)
        fill_rect(6, 8, 12, 2.4, 1.2)
    elif n == 'lock':
        rect(5.5, 10.5, 13, 10, 3)
        cr.arc(12, 10.5, 4.2, math.pi, 0); cr.stroke()
    else:  # 未知图标 → 圆点占位（保持视觉一致）
        cr.arc(12, 12, 3.2, 0, math.pi * 2); cr.fill()
    cr.restore()


def _round_rect(cr, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    cr.new_path()
    cr.arc(x + r, y + r, r, math.pi, math.pi * 1.5)
    cr.arc(x + w - r, y + r, r, math.pi * 1.5, math.pi * 2)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi * 0.5)
    cr.arc(x + r, y + h - r, r, math.pi * 0.5, math.pi)
    cr.close_path()
