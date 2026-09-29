#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 B5-Software
#
# CIBYP 桌面·共享主题与绘制库（自研，不依赖任何图标资源/主题包）
#
# 设计语言：
#   - 深空底色 + 靛蓝(CB) / 青绿(ACCENT2) 点缀，圆角卡片，细描边，柔和阴影
#   - 所有图标用 Cairo 现画（draw_icon），不依赖 SVG/PNG 资源与第三方主题
#   - 字体优先 Noto Sans CJK，缺失时回退系统 sans
#
# 被 cibyp-shell / cibyp-desktop / cibyp-files / cibyp-editor / cibyp-settings /
# cibyp-calc / cibyp-viewer / cibyp-about 共用。

import math
import os
import shutil
import sys

import gi

gi.require_version('Gtk', '4.0')
# GTK4 的 draw_func 要把 cairo.Context 转成 Python 对象：必须显式声明 foreign struct，
# 否则报 "Couldn't find foreign struct converter for 'cairo.Context'"（实测踩坑）
try:
    gi.require_foreign('cairo')
except Exception:
    pass
try:
    import cairo  # noqa: F401, E402
except Exception:
    pass
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

# ------------------------------------------------------------------ 设计令牌

BG_DEEP = (0x0B / 255, 0x0F / 255, 0x1A / 255)
BG_DEEP2 = (0x16 / 255, 0x1E / 255, 0x33 / 255)
SURFACE = (0x12 / 255, 0x18 / 255, 0x26 / 255)
SURFACE_HI = (0x1B / 255, 0x24 / 255, 0x39 / 255)
BORDER = (1, 1, 1, 0.09)
TEXT = (0xE9 / 255, 0xEE / 255, 0xF8 / 255)
TEXT_DIM = (0x93 / 255, 0xA0 / 255, 0xBB / 255)
ACCENT = (0x7C / 255, 0x6B / 255, 0xFF / 255)      # 靛蓝紫
ACCENT2 = (0x4D / 255, 0xD6 / 255, 0xC1 / 255)     # 青绿
DANGER = (0xFF / 255, 0x6B / 255, 0x81 / 255)
WARN = (0xFF / 255, 0xC4 / 255, 0x6B / 255)

RADIUS = 14
RADIUS_SM = 9 & 0xFF


def rgba(t, a=None):
    r, g, b = t[:3]
    return (r, g, b, 1.0 if a is None else a)


# ------------------------------------------------------------------ CSS

CSS = f"""
* {{
  font-family: "Noto Sans CJK SC", "Noto Sans CJK", "Noto Sans", "DejaVu Sans", sans-serif;
}}
window, .cibyp-transparent {{
  background: transparent;
}}
window.cibyp-app {{
  background: rgb(11, 15, 26);
}}
.cibyp-panel {{
  background: rgba(15, 20, 33, 0.88);
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
}}
.cibyp-card {{
  background: rgba(19, 25, 40, 0.96);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: {RADIUS}px;
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.55), 0 2px 6px rgba(0, 0, 0, 0.35);
}}
.cibyp-subcard {{
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: {RADIUS_SM}px;
}}
.cibyp-btn {{
  background: transparent;
  border: none;
  border-radius: {RADIUS_SM}px;
  color: {_css_rgb(TEXT) if False else 'rgb(233,238,248)'};
  padding: 4px 8px;
  min-height: 26px;
}}
.cibyp-btn:hover {{ background: rgba(255, 255, 255, 0.08); }}
.cibyp-btn:active {{ background: rgba(255, 255, 255, 0.14); }}
.cibyp-btn.accent {{ background: rgba(124, 107, 255, 0.22); }}
.cibyp-chip {{
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 999px;
  padding: 2px 10px;
}}
.cibyp-title {{ font-size: 13pt; font-weight: 700; color: rgb(233,238,248); }}
.cibyp-dim {{ color: rgb(147,160,187); }}
.cibyp-mono {{ font-family: "Noto Sans Mono", "DejaVu Sans Mono", monospace; }}
.cibyp-entry {{
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: {RADIUS_SM}px;
  color: rgb(233,238,248);
  padding: 6px 10px;
  caret-color: rgb(124,107,255);
}}
.cibyp-entry:focus {{ border-color: rgba(124, 107, 255, 0.65); }}
.cibyp-list {{
  background: transparent;
  color: rgb(233,238,248);
}}
.cibyp-list row {{ border-radius: {RADIUS_SM}px; }}
.cibyp-list row:selected {{ background: rgba(124, 107, 255, 0.28); }}
.cibyp-list row:hover {{ background: rgba(255, 255, 255, 0.06); }}
scrollbar slider {{
  background: rgba(255, 255, 255, 0.14);
  border-radius: 999px;
  min-width: 6px; min-height: 6px;
}}
scrollbar slider:hover {{ background: rgba(255, 255, 255, 0.24); }}
.switch {{ background: rgba(255,255,255,0.10); border-radius: 999px; }}
.switch:checked {{ background: rgba(124, 107, 255, 0.75); }}
tooltip {{
  background: rgba(19, 25, 40, 0.98);
  color: rgb(233,238,248);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 8px;
}}
"""


def _css_rgb(_t):  # pragma: no cover - 占位，保持 f-string 简单
    return 'rgb(233,238,248)'


def install_css():
    """把主题 CSS 装到默认显示（每个进程调用一次）"""
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode('utf-8'))
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    return provider


# ------------------------------------------------------------------ 字体/尺寸

def panel_height():
    return 38


def font(size, weight=None):
    """返回 (family, size, weight) 供 Cairo 使用"""
    desc = f'Noto Sans CJK SC {size}'
    if weight:
        desc += f' {weight}'
    return desc


# ------------------------------------------------------------------ 图标（Cairo 自绘）

_ICON_STROKE = 1.9


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
    elif n == 'plus':
        cr.move_to(12, 5.5); cr.line_to(12, 18.5); cr.stroke()
        cr.move_to(5.5, 12); cr.line_to(18.5, 12); cr.stroke()
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


def paint_wallpaper(cr, w, h, variant='aurora'):
    """自研壁纸：深空渐变 + 星点 + 极光弧 + 几何网格（Cairo 绘制，无资源文件）
    variant: aurora（靛蓝紫+青绿）/ midnight（深蓝+青）/ graphite（石墨灰+淡紫）
    """
    palettes = {
        'aurora': ((0x0B / 255, 0x0F / 255, 0x1A / 255), (0x16 / 255, 0x1E / 255, 0x33 / 255), ACCENT, ACCENT2),
        'midnight': ((0x06 / 255, 0x0D / 255, 0x1C / 255), (0x0E / 255, 0x1F / 255, 0x3A / 255), (0x3F / 255, 0x8C / 255, 0xFF / 255), (0x39 / 255, 0xD2 / 255, 0xFF / 255)),
        'graphite': ((0x0D / 255, 0x0E / 255, 0x12 / 255), (0x1B / 255, 0x1D / 255, 0x24 / 255), (0x9A / 255, 0x8F / 255, 0xFF / 255), (0x7A / 255, 0x86 / 255, 0x9E / 255)),
    }
    g0, g1, c1, c2 = palettes.get(variant, palettes['aurora'])

    grad = _linear(cr, 0, 0, w, h)
    grad.add_color_stop_rgb(0, *g0)
    grad.add_color_stop_rgb(0.55, *g1)
    grad.add_color_stop_rgb(1, *g0)
    cr.set_source(grad)
    cr.rectangle(0, 0, w, h)
    cr.fill()

    # 极光弧
    for (cx, cy, r, col, alpha) in (
        (w * 0.18, h * 1.05, h * 0.95, c1, 0.20),
        (w * 0.86, h * 1.12, h * 1.05, c2, 0.13),
        (w * 0.5, -h * 0.35, h * 0.8, c1, 0.08),
    ):
        g = _radial(cr, cx, cy, r)
        g.add_color_stop_rgba(0, col[0], col[1], col[2], alpha)
        g.add_color_stop_rgba(1, col[0], col[1], col[2], 0.0)
        cr.set_source(g)
        cr.rectangle(0, 0, w, h)
        cr.fill()

    # 细网格
    cr.set_source_rgba(1, 1, 1, 0.028)
    cr.set_line_width(1)
    step = 48
    for gx in range(0, int(w) + 1, step):
        cr.move_to(gx + 0.5, 0); cr.line_to(gx + 0.5, h)
    for gy in range(0, int(h) + 1, step):
        cr.move_to(0, gy + 0.5); cr.line_to(w, gy + 0.5)
    cr.stroke()

    # 星点（确定性伪随机，保证每次一致）
    seed = 20260927
    cr.set_source_rgba(1, 1, 1, 0.5)
    for i in range(90):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        px = (seed / 0x7FFFFFFF) * w
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        py = (seed / 0x7FFFFFFF) * h * 0.72
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        rr = 0.5 + (seed / 0x7FFFFFFF) * 1.3
        cr.set_source_rgba(1, 1, 1, 0.10 + 0.38 * (seed / 0x7FFFFFFF))
        cr.arc(px, py, rr, 0, math.pi * 2)
        cr.fill()

    # 中央品牌水印
    cx, cy = w / 2, h * 0.42
    draw_brandmark(cr, cx - 34, cy - 34, 68, alpha=0.16)
    cr.select_font_face('Noto Sans CJK SC', 0, 0)
    cr.set_font_size(15)
    cr.set_source_rgba(1, 1, 1, 0.20)
    text = 'CIBYP-VM-OS'
    ext = cr.text_extents(text)
    cr.move_to(cx - ext.width / 2 - ext.x_bearing, cy + 62)
    cr.show_text(text)


def draw_brandmark(cr, x, y, size, alpha=1.0, color=None):
    """品牌标记：圆角方 + 双环（自研）"""
    col = color or ACCENT
    cr.save()
    cr.translate(x, y)
    s = size / 100.0
    cr.scale(s, s)
    g = _linear(cr, 0, 0, 100, 100)
    g.add_color_stop_rgba(0, col[0], col[1], col[2], 0.95 * alpha)
    g.add_color_stop_rgba(1, ACCENT2[0], ACCENT2[1], ACCENT2[2], 0.85 * alpha)
    _round_rect(cr, 0, 0, 100, 100, 26)
    cr.set_source(g)
    cr.fill()
    cr.set_source_rgba(1, 1, 1, 0.92 * alpha)
    cr.set_line_width(7)
    cr.arc(50, 50, 26, math.pi * 0.15, math.pi * 1.75)
    cr.stroke()
    cr.arc(50, 50, 12, 0, math.pi * 2)
    cr.fill()
    cr.restore()


def _linear(cr, x0, y0, x1, y1):
    import cairo
    return cairo.LinearGradient(x0, y0, x1, y1)


def _radial(cr, cx, cy, r):
    import cairo
    return cairo.RadialGradient(cx, cy, 0, cx, cy, max(r, 1))


# ------------------------------------------------------------------ layer-shell 预加载

_LAYER_SHELL_ENV = 'CIBYP_LAYER_SHELL_PRELOADED'


def _find_layer_shell_lib():
    import glob
    for pat in ('/usr/lib/*/libgtk4-layer-shell.so.0', '/usr/lib/libgtk4-layer-shell.so.0'):
        hits = glob.glob(pat)
        if hits:
            return hits[0]
    return ''


def ensure_layer_shell_preload():
    """gtk4-layer-shell 与 GTK4 存在动态链接顺序限制：必须 LD_PRELOAD 才能让窗口
    变成 layer surface。做法：本进程未预加载时，带 LD_PRELOAD 重新 exec 自己
    （幂等；用环境变量防死循环）。只影响自研 GTK 应用，不会污染 sway/bash 等进程。"""
    lib = _find_layer_shell_lib()
    if not lib:
        return
    if lib in os.environ.get('LD_PRELOAD', ''):
        return
    if os.environ.get(_LAYER_SHELL_ENV) == '1':
        return
    env = dict(os.environ)
    env['LD_PRELOAD'] = (lib + ':' + env.get('LD_PRELOAD', '')).strip(':')
    env[_LAYER_SHELL_ENV] = '1'
    try:
        os.execve(sys.executable, [sys.executable, os.path.abspath(sys.argv[0])] + sys.argv[1:], env)
    except Exception:
        pass  # 失败则继续（面板会退化为普通窗口，不致命）


_INSTANCE_LOCKS = {}


def acquire_single_instance(name):
    """按名字获取单实例锁（$XDG_RUNTIME_DIR/<name>.lock，进程退出自动释放）。
    返回 True=获得锁，False=已有实例在跑。用于外壳/壁纸这类必须唯一的常驻组件。"""
    try:
        import fcntl
    except Exception:
        return True
    rt = os.environ.get('XDG_RUNTIME_DIR') or '/tmp'
    path = os.path.join(rt, name + '.lock')
    try:
        fh = open(path, 'w')
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _INSTANCE_LOCKS[name] = fh
        return True
    except Exception:
        return False


def try_layer_shell(window, *, namespace=None, layer='top', anchors=('top', 'left', 'right'), exclusive=None):
    """安全初始化 layer-shell：任何失败都返回 False，让调用方回退为普通窗口。
    返回 True 表示已是 layer surface（后续 LayerShell 调用才有效）。"""
    try:
        gi.require_version('Gtk4LayerShell', '1.0')
        from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        print(f'cibypui: 无法加载 Gtk4LayerShell（{exc}），回退普通窗口', file=sys.stderr)
        return False
    try:
        LayerShell.init_for_window(window)
    except Exception as exc:  # noqa: BLE001
        print(f'cibypui: layer-shell 不可用（{exc}），回退普通窗口', file=sys.stderr)
        return False
    try:
        if namespace:
            LayerShell.set_namespace(window, namespace)
        layer_map = {
            'background': LayerShell.Layer.BACKGROUND,
            'bottom': LayerShell.Layer.BOTTOM,
            'top': LayerShell.Layer.TOP,
            'overlay': LayerShell.Layer.OVERLAY,
        }
        LayerShell.set_layer(window, layer_map.get(layer, LayerShell.Layer.TOP))
        edge_map = {
            'top': LayerShell.Edge.TOP, 'bottom': LayerShell.Edge.BOTTOM,
            'left': LayerShell.Edge.LEFT, 'right': LayerShell.Edge.RIGHT,
        }
        for a in anchors:
            LayerShell.set_anchor(window, edge_map[a], True)
        if exclusive is not None:
            LayerShell.set_exclusive_zone(window, exclusive)
        # 只有真正能设扩展区/锚点，才算 layer-shell 可用
        return True
    except Exception as exc:  # noqa: BLE001
        print(f'cibypui: layer-shell 配置失败（{exc}），回退普通窗口', file=sys.stderr)
        return False


def layer_shell_geometry_fallback(window, width, height):
    """回退普通窗口时的尺寸/最小尺寸设置（位置由 sway 规则处理）"""
    try:
        window.set_default_size(width, height)
        window.set_size_request(min(width, 640), height)
    except Exception:
        pass


# ------------------------------------------------------------------ 小工具

def arg_path(default=''):
    """取命令行里第一个非选项参数（应用自定义解析，不交给 Gtk.Application）"""
    for a in sys.argv[1:]:
        if not a.startswith('-'):
            return os.path.expanduser(a)
    return default


def run_async(fn, *args):
    """在 GLib 主循环里安全执行（供定时器/回调）"""
    GLib.idle_add(lambda: (fn(*args), False)[1])


def launch(cmd):
    """启动外部程序（分离进程）"""
    try:
        Gio.Subprocess.new(cmd, Gio.SubprocessFlags.NONE)
    except Exception:
        pass


def which(name):
    return shutil.which(name) or ''


def app_icon_name(app_id, name=''):
    """把 .desktop 的 id/名字映射到自绘图标名"""
    s = f'{app_id or ""} {name or ""}'.lower()
    for key, icon in (
        ('terminal', 'terminal'), ('console', 'terminal'), ('foot', 'terminal'),
        ('files', 'files'), ('file', 'files'), ('nautilus', 'files'),
        ('edit', 'editor'), ('writer', 'editor'), ('text', 'editor'),
        ('settings', 'settings'), ('control', 'settings'),
        ('calc', 'calc'),
        ('viewer', 'viewer'), ('image', 'viewer'),
        ('chrom', 'browser'), ('firefox', 'browser'), ('browser', 'browser'),
        ('about', 'info'),
    ):
        if key in s:
            return icon
    return 'window'
