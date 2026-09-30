# SPDX-License-Identifier: GPL-3.0-or-later
"""Native file manager with asynchronous navigation and recoverable deletion."""
import json
import os
from pathlib import Path
import sys
from datetime import datetime
from gi.repository import Gdk, Gio, GLib, Gtk
import cibypui as ui
from campus_core import CONFIG_DIR, atomic_write, human_size, paste_items, valid_name
from campus_trash import restore, trash_root


class FilesWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='文件 · Campus')
        self.set_default_size(960, 640)
        ui.window_frame(self, '文件', 'files')
        self.cwd = Path.home()
        self.history, self.position, self.generation = [], -1, 0
        self.hidden = ui.config()['show_hidden']
        self.rows, self.busy, self.sort = [], False, 'name'
        self.monitor, self.refresh_timer = None, None
        root = ui.box(True, 0)
        self.set_child(root)
        toolbar = ui.box()
        toolbar.add_css_class('toolbar')
        self.back = ui.button(callback=lambda: self.step(-1), glyph='back', tip='后退 Alt+←')
        self.forward = ui.button(callback=lambda: self.step(1), glyph='forward', tip='前进 Alt+→')
        toolbar.append(self.back)
        toolbar.append(self.forward)
        toolbar.append(ui.button(callback=lambda: self.navigate(self.cwd.parent), glyph='up', tip='上一级 Alt+↑'))
        self.path_entry = Gtk.Entry()
        self.path_entry.set_hexpand(True)
        self.path_entry.connect('activate', lambda *_: self.navigate(self.path_entry.get_text()))
        toolbar.append(self.path_entry)
        toolbar.append(ui.button(callback=self.refresh, glyph='refresh', tip='刷新 F5'))
        root.append(toolbar)
        actions = ui.box()
        actions.add_css_class('toolbar')
        for text, glyph, callback in [('新建', 'plus', self.create_menu), ('复制', 'copy', lambda: self.copy('copy')),
                                       ('剪切', 'cut', lambda: self.copy('cut')), ('粘贴', 'paste', self.paste),
                                       ('回收站', 'trash', self.trash)]:
            actions.append(ui.button(text, callback, glyph))
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text('搜索当前文件夹')
        self.search.set_hexpand(True)
        self.search.connect('search-changed', lambda *_: self.filter_rows())
        self.search.connect('activate', lambda *_: self.focus_results())
        self.search.connect('stop-search', lambda *_: self.focus_results())
        actions.append(self.search)
        actions.append(ui.button('排序', self.sort_menu, 'grid'))
        root.append(actions)
        content = ui.box(spacing=0)
        content.set_vexpand(True)
        sidebar = ui.pad(ui.box(True, 7), 12)
        sidebar.add_css_class('sidebar')
        sidebar.set_size_request(168, -1)
        sidebar.append(ui.label('位置', 'dim'))
        for title, path, glyph in [('主目录', Path.home(), 'home'), ('工作区', Path('/workspace'), 'folder'),
                                   ('桌面', Path.home()/'Desktop', 'grid'), ('文档', Path.home()/'Documents', 'file'),
                                   ('下载', Path.home()/'Downloads', 'down'), ('图片', Path.home()/'Pictures', 'image'),
                                   ('系统文件', Path('/'), 'settings')]:
            sidebar.append(ui.button(title, lambda p=path: self.navigate(p), glyph, 'flat'))
        sidebar.append(ui.button('回收站', self.open_trash, 'trash', 'flat'))
        content.append(sidebar)
        self.list = Gtk.ListBox()
        self.list.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        self.list.set_activate_on_single_click(False)
        self.list.connect('row-activated', lambda _list, row: self.open(row.path))
        self.list.connect('selected-rows-changed', lambda *_: self.update_status())
        self.list.set_filter_func(lambda row: self.search.get_text().casefold() in row.path.name.casefold())
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_child(self.list)
        ui.context_menu(scroll, lambda: self.menu())
        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        def dropped(_target, values, _x, _y):
            paths = [file.get_path() for file in values.get_files() if file.get_path()]
            if paths:
                self.work(lambda: paste_items(paths, 'copy', self.cwd))
                return True
            return False
        drop.connect('drop', dropped)
        scroll.add_controller(drop)
        content.append(scroll)
        root.append(content)
        self.status = ui.label('', 'status')
        root.append(self.status)
        ui.shortcuts(self, {'alt+left': lambda: self.step(-1), 'alt+right': lambda: self.step(1),
                            'alt+up': lambda: self.navigate(self.cwd.parent), 'ctrl+l': self.path_entry.grab_focus,
                            'ctrl+f': self.search.grab_focus, 'ctrl+c': lambda: self.file_shortcut(lambda: self.copy('copy')),
                            'ctrl+x': lambda: self.file_shortcut(lambda: self.copy('cut')), 'ctrl+v': lambda: self.file_shortcut(self.paste),
                            'ctrl+a': lambda: self.file_shortcut(self.list.select_all), 'ctrl+h': self.toggle_hidden,
                            'ctrl+shift+n': lambda: self.new_item(True), 'f2': self.rename,
                            'delete': lambda: self.file_shortcut(self.trash), 'f5': self.refresh, 'return': lambda: self.file_shortcut(self.open_selected)})
        initial = sys.argv[1] if len(sys.argv) > 1 else str(Path.home())
        self.navigate(initial)

    def selected(self):
        return [row.path for row in self.list.get_selected_rows()]

    def file_shortcut(self, callback):
        focus = self.get_focus()
        if isinstance(focus, Gtk.Editable) or isinstance(focus, Gtk.TextView):
            return False
        callback()

    def navigate(self, value, record=True):
        target = Path(value).expanduser().absolute()
        if not target.is_dir():
            ui.dialog(self, '无法打开文件夹', f'{target}\n目录不存在或没有访问权限')
            return
        self.generation += 1
        generation = self.generation
        self.status.set_text('正在读取文件夹…')
        def scan():
            result = []
            for path in target.iterdir():
                try:
                    stat = path.stat()
                    result.append((path, path.is_dir(), stat.st_size, stat.st_mtime))
                except OSError:
                    continue
            return result
        def complete(items, error):
            if generation != self.generation:
                return
            if error:
                ui.dialog(self, '读取失败', str(error))
                self.update_status()
                return
            self.cwd = target
            if record:
                self.history = self.history[:self.position+1] + [target]
                self.position = len(self.history)-1
            self.path_entry.set_text(str(target))
            self.back.set_sensitive(self.position > 0)
            self.forward.set_sensitive(self.position < len(self.history)-1)
            self.items = items
            self.render()
            self.watch_directory()
        ui.background(scan, complete)

    def render(self):
        ui.dismiss_popovers(self)
        selected = set(self.selected())
        while self.list.get_first_child():
            self.list.remove(self.list.get_first_child())
        self.rows = []
        keys = {'name': lambda item: item[0].name.casefold(), 'modified': lambda item: -item[3], 'size': lambda item: -item[2]}
        for path, directory, size, modified in sorted(self.items, key=lambda item: (not item[1], keys[self.sort](item))):
            if not self.hidden and path.name.startswith('.'):
                continue
            row = Gtk.ListBoxRow()
            row.path = path
            content = ui.pad(ui.box(spacing=12), 6)
            glyph = 'folder' if directory else 'image' if path.suffix.lower() in ('.png', '.jpg', '.svg', '.webp') else 'editor'
            content.append(ui.icon(glyph, 30, True))
            name = ui.label(path.name, expand=True)
            name.set_ellipsize(ui.Pango.EllipsizeMode.END)
            content.append(name)
            size_label = ui.label('文件夹' if directory else human_size(size), 'dim')
            size_label.set_size_request(88, -1)
            content.append(size_label)
            date_label = ui.label(datetime.fromtimestamp(modified).strftime('%m-%d %H:%M'), 'dim')
            content.append(date_label)
            row.set_child(content)
            click = Gtk.GestureClick.new()
            click.set_button(1)
            click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            def select(gesture, count, _x, _y, row=row):
                modifiers = gesture.get_current_event_state()
                if modifiers & Gdk.ModifierType.SHIFT_MASK and getattr(self, 'selection_anchor', None) in [item.path for item in self.rows]:
                    visible = [item for item in self.rows if item.get_child_visible()]
                    anchor = next((item for item in visible if item.path == self.selection_anchor), row)
                    start, end = sorted((visible.index(anchor), visible.index(row)))
                    self.list.unselect_all()
                    for item in visible[start:end+1]:
                        self.list.select_row(item)
                elif modifiers & Gdk.ModifierType.CONTROL_MASK:
                    self.list.unselect_row(row) if row.is_selected() else self.list.select_row(row)
                    self.selection_anchor = row.path
                else:
                    self.list.unselect_all()
                    self.list.select_row(row)
                    self.selection_anchor = row.path
                row.grab_focus()
                gesture.set_state(Gtk.EventSequenceState.CLAIMED)
                if count == 2:
                    self.open(row.path)
            click.connect('pressed', select)
            row.add_controller(click)
            ui.context_menu(row, lambda r=row: self.row_menu(r))
            self.list.append(row)
            self.rows.append(row)
            if path in selected:
                self.list.select_row(row)
        self.list.invalidate_filter()
        self.update_status()

    def row_menu(self, row):
        row.grab_focus()
        if row not in self.list.get_selected_rows():
            self.list.unselect_all()
            self.list.select_row(row)
        return self.menu()

    def menu(self):
        selected = self.selected()
        if self.cwd == trash_root() / 'files':
            return [('恢复到原位置', lambda: self.work(lambda: restore(selected)), 'refresh', bool(selected)), ('属性', self.properties, 'info'), ('刷新', self.refresh, 'refresh')]
        return [('打开', self.open_selected, 'open', bool(selected)), None,
                ('复制', lambda: self.copy('copy'), 'copy', bool(selected)),
                ('剪切', lambda: self.copy('cut'), 'cut', bool(selected)), ('粘贴', self.paste, 'paste'),
                ('重命名', self.rename, 'edit', len(selected) == 1),
                ('移到回收站', self.trash, 'trash', bool(selected)), None,
                ('新建文件夹', lambda: self.new_item(True), 'folder'), ('新建文本文件', lambda: self.new_item(False), 'editor'),
                ('在这里打开终端', lambda: ui.launch(['cibyp-terminal', str(self.cwd)]), 'terminal'),
                ('显示 / 隐藏隐藏文件', self.toggle_hidden, 'grid'), ('属性', self.properties, 'info'),
                ('刷新', self.refresh, 'refresh')]

    def update_status(self):
        count = len(self.selected())
        self.status.set_text(f'{self.cwd}   ·   {len(self.rows)} 个项目' + (f'   ·   已选择 {count} 个' if count else ''))

    def filter_rows(self):
        self.list.invalidate_filter()

    def focus_results(self):
        visible = [row for row in self.rows if row.get_child_visible()]
        if visible:
            self.list.unselect_all()
            self.list.select_row(visible[0])
            visible[0].grab_focus()

    def refresh(self):
        self.navigate(self.cwd, False)

    def step(self, offset):
        index = self.position + offset
        if 0 <= index < len(self.history):
            self.position = index
            self.navigate(self.history[index], False)

    def open(self, path):
        try:
            self.navigate(path) if path.is_dir() else ui.open_path(path)
        except Exception as error:
            ui.dialog(self, '打开失败', str(error))

    def open_trash(self):
        path = trash_root() / 'files'
        path.mkdir(parents=True, exist_ok=True)
        self.navigate(path)

    def watch_directory(self):
        if self.monitor:
            self.monitor.cancel()
        self.monitor = Gio.File.new_for_path(str(self.cwd)).monitor_directory(Gio.FileMonitorFlags.NONE, None)
        def changed(*_):
            if self.refresh_timer:
                GLib.source_remove(self.refresh_timer)
            def refresh():
                self.refresh_timer = None
                self.refresh()
                return False
            self.refresh_timer = GLib.timeout_add(350, refresh)
        self.monitor.connect('changed', changed)

    def open_selected(self):
        for path in self.selected():
            self.open(path)

    def create_menu(self):
        ui.popover(self.path_entry, [('新建文件夹', lambda: self.new_item(True), 'folder'), ('新建文本文件', lambda: self.new_item(False), 'editor')])

    def new_item(self, directory):
        def create(name):
            target = self.cwd / valid_name(name.strip())
            if directory:
                target.mkdir()
            else:
                target.open('x').close()
            self.refresh()
        ui.dialog(self, '新建文件夹' if directory else '新建文本文件', actions=[('取消', None), ('创建', create)], entry='新建文件夹' if directory else '未命名.txt')

    def rename(self):
        selected = self.selected()
        if len(selected) != 1:
            return
        source = selected[0]
        def apply(name):
            target = source.parent / valid_name(name.strip())
            if target != source and (target.exists() or target.is_symlink()):
                raise ValueError('同名项目已经存在')
            source.rename(target)
            self.refresh()
        ui.dialog(self, '重命名', actions=[('取消', None), ('保存', apply)], entry=source.name)

    def copy(self, mode):
        paths = self.selected()
        if not paths:
            return
        atomic_write(CONFIG_DIR/'clipboard.json', json.dumps({'mode': mode, 'paths': [str(p) for p in paths]}))
        self.get_display().get_clipboard().set('\n'.join(p.as_uri() for p in paths))
        self.status.set_text(f'已{"剪切" if mode == "cut" else "复制"} {len(paths)} 个项目')

    def work(self, operation):
        if self.busy:
            return
        self.busy = True
        self.status.set_text('正在处理文件…')
        def complete(result, error):
            self.busy = False
            if error:
                ui.dialog(self, '操作失败', str(error))
            elif result:
                failures = [message for ok, message in result if not ok]
                if failures:
                    ui.dialog(self, '部分项目没有完成', '\n'.join(failures))
            self.refresh()
        ui.background(operation, complete)

    def paste(self):
        try:
            data = json.loads((CONFIG_DIR/'clipboard.json').read_text())
        except (ValueError, OSError):
            self.status.set_text('请先复制或剪切文件')
            return
        destination = str(self.cwd)
        def operation():
            result = paste_items(data['paths'], data['mode'], destination)
            if data['mode'] == 'cut':
                # Keep only failures so a partial move can be retried safely.
                remaining = [p for p, (ok, _) in zip(data['paths'], result) if not ok]
                atomic_write(CONFIG_DIR/'clipboard.json', json.dumps(dict(data, paths=remaining)))
            return result
        self.work(operation)

    def trash(self):
        paths = self.selected()
        if not paths:
            return
        if self.cwd == trash_root() / 'files':
            self.status.set_text('右键选择“恢复到原位置”可找回文件。')
            return
        def operation():
            result = []
            for path in paths:
                try:
                    Gio.File.new_for_path(str(path)).trash(None)
                    result.append((True, str(path)))
                except Exception as error:
                    result.append((False, f'{path.name}: {error}'))
            return result
        ui.dialog(self, f'将 {len(paths)} 个项目移到回收站？', '可以从系统回收站恢复。不会永久删除。', [('取消', None), ('移到回收站', lambda _: self.work(operation))])

    def toggle_hidden(self):
        self.hidden = not self.hidden
        ui.set_preferences(show_hidden=self.hidden)
        self.render()

    def sort_menu(self):
        def apply(value):
            self.sort = value
            self.render()
        ui.popover(self.search, [(title, lambda key=key: apply(key), 'grid') for title, key in [('名称', 'name'), ('修改时间', 'modified'), ('大小', 'size')]])

    def properties(self):
        path = (self.selected() or [self.cwd])[0]
        stat = path.stat()
        ui.dialog(self, path.name or str(path), f'位置：{path}\n类型：{"文件夹" if path.is_dir() else "文件"}\n大小：{human_size(stat.st_size)}\n修改：{datetime.fromtimestamp(stat.st_mtime):%Y-%m-%d %H:%M:%S}\n权限：{oct(stat.st_mode & 0o777)}')
