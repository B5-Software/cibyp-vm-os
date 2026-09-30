"""Native layer-shell desktop, illustrated campus wallpaper and desktop actions."""
import math
from pathlib import Path
from gi.repository import Gio, GLib, Gtk, Pango
import cairo
import cibypui as ui
from campus_icons import _round_rect
from campus_core import CONFIG_DIR, atomic_write, valid_name
import json


def wallpaper(cr, width, height):
    dark = ui.config()['theme'] == 'dark'
    style = ui.config().get('wallpaper', 'campus')
    cr.save()
    cr.scale(width / 1280, height / 800)
    sky = cairo.LinearGradient(0, 0, 1000, 800)
    if ui.config().get('background_color'):
        base = ui.color('bg')
        accent = ui.color('accent')
        sky.add_color_stop_rgb(0, *base)
        sky.add_color_stop_rgb(.58, *(value*.97 + tint*.03 for value, tint in zip(base, accent)))
        sky.add_color_stop_rgb(1, *(value*.92 + tint*.08 for value, tint in zip(base, accent)))
    else:
        sky.add_color_stop_rgb(0, *ui.rgb('#25334d' if dark else '#e7efff'))
        sky.add_color_stop_rgb(.58, *ui.rgb('#28394c' if dark else '#edf7f2'))
        sky.add_color_stop_rgb(1, *ui.rgb('#433950' if dark else '#fbe9e8'))
    cr.set_source(sky)
    cr.paint()
    accent = ui.color('accent')
    def rounded(x, y, w, h, radius, color):
        cr.set_source_rgb(*ui.rgb(color))
        _round_rect(cr, x, y, w, h, radius)
        cr.fill()
    # Sun or moon and drifting clouds; deliberately leave room for real windows.
    cr.set_source_rgba(1, .91, .72, .72 if dark else .9)
    cr.arc(1040, 155, 50, 0, math.tau)
    cr.fill()
    if dark:
        cr.set_source_rgb(*ui.rgb('#29374e'))
        cr.arc(1057, 140, 43, 0, math.tau)
        cr.fill()
    for x, y, scale in [(650, 158, 1), (860, 235, .7), (385, 220, .55)]:
        cr.set_source_rgba(1, 1, 1, .09 if dark else .65)
        for dx, dy, radius in [(0, 0, 24), (29, -9, 31), (65, 2, 22)]:
            cr.arc(x + dx*scale, y + dy*scale, radius*scale, 0, math.tau)
            cr.fill()
    if style == 'notebook':
        cr.set_source_rgba(*accent, .12)
        cr.set_line_width(1)
        for x in range(0, 1280, 36):
            cr.move_to(x, 0)
            cr.line_to(x, 800)
        for y in range(0, 800, 36):
            cr.move_to(0, y)
            cr.line_to(1280, y)
        cr.stroke()
        for x, y, radius in [(880, 370, 145), (1150, 650, 100), (370, 690, 160)]:
            cr.set_source_rgba(*accent, .1)
            cr.arc(x, y, radius, 0, math.tau)
            cr.fill()
    elif style == 'campus':
        # Rolling lawn and a warm, simple school building with lit windows at night.
        cr.set_source_rgb(*ui.rgb('#314a48' if dark else '#d3e7da'))
        cr.move_to(0, 650)
        cr.curve_to(340, 575, 730, 730, 1280, 615)
        cr.line_to(1280, 800)
        cr.line_to(0, 800)
        cr.fill()
        cr.set_source_rgb(*ui.rgb('#3b5650' if dark else '#bfdacc'))
        cr.move_to(0, 755)
        cr.curve_to(440, 680, 900, 690, 1280, 735)
        cr.line_to(1280, 800)
        cr.line_to(0, 800)
        cr.fill()
        rounded(560, 394, 460, 284, 13, '#536071' if dark else '#f5e7d7')
        rounded(534, 383, 512, 22, 8, '#798594' if dark else '#dfbfa6')
        rounded(727, 331, 125, 348, 10, '#647186' if dark else '#fff2e1')
        rounded(716, 321, 147, 19, 6, '#8b919d' if dark else '#ddbaa1')
        for x in (593, 650, 898, 955):
            for y in (428, 499, 570):
                rounded(x, y, 34, 45, 5, '#d7bd8c' if dark else '#a7c6d5')
                cr.set_source_rgba(1, 1, 1, .28)
                cr.rectangle(x + 7, y + 3, 4, 37)
                cr.fill()
        rounded(752, 580, 77, 99, 12, '#394c61' if dark else '#8caec0')
        cr.set_source_rgb(*ui.rgb('#f9e7cd' if dark else '#ffffff'))
        cr.arc(789, 393, 27, 0, math.tau)
        cr.fill()
        cr.set_source_rgb(*ui.rgb('#64788e'))
        cr.set_line_width(3)
        cr.move_to(789, 393)
        cr.line_to(789, 376)
        cr.move_to(789, 393)
        cr.line_to(803, 399)
        cr.stroke()
        for x, y, scale in [(456, 565, 1), (1080, 570, 1.1), (1153, 630, .7), (382, 639, .65)]:
            rounded(x-6, y, 12, 115*scale, 5, '#7d8072' if dark else '#b6a58d')
            for dx, dy, radius in [(0, -28, 44), (-25, 1, 36), (24, 1, 36)]:
                cr.set_source_rgb(*ui.rgb('#54766b' if dark else '#99c6af'))
                cr.arc(x + dx*scale, y + dy*scale, radius*scale, 0, math.tau)
                cr.fill()
        # A notebook on the lawn, echoing the app's campus identity.
        cr.save()
        cr.translate(210, 672)
        cr.rotate(-.14)
        rounded(0, 0, 115, 65, 9, '#747aa0' if dark else '#c2badd')
        rounded(8, 5, 99, 53, 6, '#d4d5db' if dark else '#fffaf2')
        cr.set_source_rgba(*accent, .6)
        for y in (20, 32, 44):
            cr.rectangle(20, y, 66, 2)
            cr.fill()
        cr.restore()
    cr.restore()


class DesktopWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='Campus 桌面')
        self.add_css_class('campus')
        self.set_decorated(False)
        ui.try_layer_shell(self, 'cibyp-desktop', 'background', ('top', 'bottom', 'left', 'right'), -1)
        overlay = Gtk.Overlay()
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_draw_func(lambda _area, cr, width, height: wallpaper(cr, width, height))
        overlay.set_child(self.canvas)
        self.shortcuts = ui.pad(ui.box(True, 12), 25)
        self.shortcuts.set_halign(Gtk.Align.START)
        self.shortcuts.set_valign(Gtk.Align.START)
        for title, glyph, command in [('我的文件', 'files', ['cibyp-files']), ('工作目录', 'folder', ['cibyp-files', '/workspace']), ('浏览器', 'browser', ['chromium', '--ozone-platform=wayland']), ('课堂笔记', 'editor', ['cibyp-editor']), ('终端', 'terminal', ['cibyp-terminal'])]:
            item = Gtk.Button()
            item.add_css_class('shortcut')
            content = ui.box(True, 7)
            glyph_widget = ui.icon(glyph, 49, True)
            glyph_widget.set_halign(Gtk.Align.CENTER)
            content.append(glyph_widget)
            caption = ui.label(title)
            caption.set_halign(Gtk.Align.CENTER)
            content.append(caption)
            item.set_child(content)
            item.connect('clicked', lambda _item, command=command: ui.launch(command))
            ui.context_menu(item, [('打开', lambda command=command: ui.launch(command), glyph), ('在文件管理器中打开桌面', self.open_desktop, 'files')])
            self.shortcuts.append(item)
        overlay.add_overlay(self.shortcuts)
        self.desktop_files = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.MULTIPLE)
        self.desktop_files.set_activate_on_single_click(False)
        self.desktop_files.set_min_children_per_line(1)
        self.desktop_files.set_max_children_per_line(4)
        self.desktop_files.set_row_spacing(10)
        self.desktop_files.set_column_spacing(10)
        self.desktop_files.set_halign(Gtk.Align.START)
        self.desktop_files.set_valign(Gtk.Align.START)
        self.desktop_files.set_margin_start(145)
        self.desktop_files.set_margin_top(25)
        self.desktop_files.connect('child-activated', lambda _box, row: ui.open_path(row.path))
        overlay.add_overlay(self.desktop_files)
        self.refresh_files()
        self.file_monitor = Gio.File.new_for_path(str(self.directory())).monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.refresh_timer = None
        def files_changed(*_):
            if self.refresh_timer:
                GLib.source_remove(self.refresh_timer)
            def refresh():
                self.refresh_timer = None
                self.refresh_files()
                return False
            self.refresh_timer = GLib.timeout_add(300, refresh)
        self.file_monitor.connect('changed', files_changed)
        greeting = ui.pad(ui.box(True, 8), 55)
        greeting.set_halign(Gtk.Align.END)
        greeting.set_valign(Gtk.Align.START)
        title = ui.label('今天，也有新发现。', 'title')
        greeting.append(title)
        greeting.append(ui.label('CAMPUS  /  CIBYP OS', 'dim'))
        overlay.add_overlay(greeting)
        ui.context_menu(self.canvas, self.menu)
        self.set_child(overlay)
        def update():
            self.canvas.queue_draw()
            self.shortcuts.set_visible(ui.config().get('show_desktop_icons', True))
            self.desktop_files.set_visible(ui.config().get('show_desktop_icons', True))
        ui.on_theme(update)
        update()

    def refresh_files(self):
        while self.desktop_files.get_first_child():
            self.desktop_files.remove(self.desktop_files.get_first_child())
        try:
            files = sorted(self.directory().iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
        except OSError:
            files = []
        for path in files[:40]:
            if path.name.startswith('.'):
                continue
            row = Gtk.FlowBoxChild()
            row.path = path
            content = ui.pad(ui.box(True, 7), 8)
            content.set_size_request(86, -1)
            picture = ui.icon('folder' if path.is_dir() else 'image' if path.suffix.lower() in ('.png', '.jpg', '.svg') else 'editor', 48, True)
            picture.set_halign(Gtk.Align.CENTER)
            content.append(picture)
            name = Gtk.Label(label=path.name, max_width_chars=11, ellipsize=Pango.EllipsizeMode.END)
            content.append(name)
            row.set_child(content)
            row.set_tooltip_text(str(path))
            ui.context_menu(row, lambda path=path: self.file_menu(path))
            self.desktop_files.append(row)

    def file_menu(self, path):
        def rename():
            def apply(name):
                target = path.parent / valid_name(name)
                if target != path and (target.exists() or target.is_symlink()):
                    raise ValueError('同名项目已经存在')
                path.rename(target)
            ui.dialog(self, '重命名', actions=[('取消', None), ('保存', apply)], entry=path.name)
        def trash():
            ui.dialog(self, '移到回收站？', path.name, [('取消', None), ('移到回收站', lambda _: Gio.File.new_for_path(str(path)).trash(None))])
        def copy():
            atomic_write(CONFIG_DIR/'clipboard.json', json.dumps({'mode': 'copy', 'paths': [str(path)]}))
        return [('打开', lambda: ui.open_path(path), 'open'), ('复制', copy, 'copy'), ('重命名', rename, 'editor'), ('移到回收站', trash, 'trash'), None, ('在文件夹中显示', self.open_desktop, 'files')]

    def directory(self):
        path = Path.home() / 'Desktop'
        path.mkdir(parents=True, exist_ok=True)
        return path

    def open_desktop(self):
        ui.launch(['cibyp-files', str(self.directory())])

    def create(self, folder=False):
        def done(name):
            path = self.directory() / valid_name(name)
            path.mkdir() if folder else path.open('x').close()
            self.open_desktop()
        ui.dialog(self, '新建文件夹' if folder else '新建文本文档', '项目会保存在桌面文件夹。', [('取消', None), ('新建', done)], entry='新建文件夹' if folder else '课堂笔记.txt')

    def menu(self):
        return [('打开桌面文件夹', self.open_desktop, 'files'), ('打开工作目录', lambda: ui.launch(['cibyp-files', '/workspace']), 'folder'), ('在此打开终端', lambda: ui.launch(['cibyp-terminal', str(self.directory())]), 'terminal'), None, ('新建文件夹', lambda: self.create(True), 'folder'), ('新建文本文档', self.create, 'editor'), None, ('外观跟随 CIBYP App' if ui.config().get('appearance_source') == 'app' else '浅色 / 深色', lambda: ui.launch(['cibyp-settings']) if ui.config().get('appearance_source') == 'app' else ui.set_preferences(theme='light' if ui.config()['theme'] == 'dark' else 'dark'), 'image'), ('个性化与设置', lambda: ui.launch(['cibyp-settings']), 'settings')]
