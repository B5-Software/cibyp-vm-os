"""GTK4/VTE terminal with real cwd, tabs, search and live colors."""
import os
from pathlib import Path
import sys
import signal
import gi
gi.require_version('Vte', '3.91')
from gi.repository import Gdk, GLib, Gtk, Pango, Vte
import cibypui as ui


class TerminalWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='终端 · Campus')
        self.set_default_size(980, 630)
        ui.window_frame(self, '终端', 'terminal')
        self.terminals, self.counter = [], 0
        requested = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path('/workspace') if Path('/workspace').is_dir() else Path.home()
        self.cwd = requested.absolute()
        content = ui.box(True, 0)
        toolbar = ui.box()
        toolbar.add_css_class('toolbar')
        for title, callback, glyph in [('新标签页', self.new_tab, 'add'), ('复制', self.copy, 'copy'), ('粘贴', self.paste, 'paste'), ('查找', self.search, 'search')]:
            toolbar.append(ui.button(title, callback, glyph))
        toolbar.append(ui.label(str(self.cwd), 'dim', True))
        content.append(toolbar)
        self.tabs = Gtk.Notebook(scrollable=True, vexpand=True)
        content.append(self.tabs)
        self.notice = ui.label('Ctrl + Shift + C / V 复制粘贴 · Ctrl + Shift + T 新标签页', 'status')
        content.append(self.notice)
        self.set_child(content)
        ui.shortcuts(self, {'ctrl+shift+t': self.new_tab, 'ctrl+shift+w': lambda: self.close_tab(self.current()), 'ctrl+shift+c': self.copy, 'ctrl+shift+v': self.paste, 'ctrl+shift+f': self.search, 'ctrl+plus': lambda: self.font(1), 'ctrl+equal': lambda: self.font(1), 'ctrl+minus': lambda: self.font(-1)})
        ui.on_theme(self.colors)
        self.connect('close-request', self.close_requested)
        self.connect('destroy', lambda *_: [self.end_child(terminal) for terminal in self.terminals])
        if not self.cwd.is_dir() or not os.access(self.cwd, os.X_OK):
            GLib.idle_add(lambda: ui.dialog(self, '工作目录不可用', str(self.cwd), [('关闭', lambda _: self.destroy()), ('选择目录', lambda _: ui.choose_file(self, self.change_directory, folder=True))]))
        else:
            self.new_tab()

    def change_directory(self, path):
        self.cwd = Path(path)
        self.new_tab()

    def current(self):
        page = self.tabs.get_current_page()
        return self.terminals[page] if 0 <= page < len(self.terminals) else None

    def new_tab(self):
        if not self.cwd.is_dir():
            ui.dialog(self, '工作目录不存在', str(self.cwd))
            return
        terminal = Vte.Terminal()
        terminal._child_running = False
        terminal._font_size = 12
        terminal.set_scrollback_lines(15000)
        terminal.set_font(Pango.FontDescription.from_string('DejaVu Sans Mono 12'))
        terminal.set_mouse_autohide(True)
        terminal.set_hexpand(True)
        terminal.set_vexpand(True)
        terminal.set_margin_start(9)
        terminal.set_margin_end(9)
        terminal.set_margin_top(6)
        terminal.set_margin_bottom(6)
        terminal.search_set_wrap_around(True)
        self.counter += 1
        tab = ui.box(spacing=6)
        title = ui.label(f'终端 {self.counter}')
        tab.append(title)
        tab.append(ui.button('×', lambda: self.close_tab(terminal), css='flat'))
        self.terminals.append(terminal)
        self.tabs.append_page(terminal, tab)
        self.tabs.set_current_page(len(self.terminals)-1)
        terminal.connect('window-title-changed', lambda term: title.set_text((term.get_window_title() or '终端')[:36]))
        terminal.connect('child-exited', lambda term, status: (setattr(term, '_child_running', False), self.notice.set_text(f'会话已结束 · 状态 {status} · 可以关闭此标签页')))
        ui.context_menu(terminal, lambda: [('复制', self.copy, 'copy', terminal.get_has_selection()), ('粘贴', self.paste, 'paste'), ('查找', self.search, 'search'), None, ('新标签页', self.new_tab, 'add'), ('放大字号', lambda: self.font(1), 'add'), ('缩小字号', lambda: self.font(-1), 'back'), ('清屏', lambda: terminal.reset(False, False), 'refresh'), ('关闭标签页', lambda: self.close_tab(terminal), 'close')])
        shell = os.environ.get('SHELL', '/bin/bash')
        if not Path(shell).is_file():
            shell = '/bin/bash'
        environment = [f'{key}={value}' for key, value in os.environ.items() if key not in ('LD_PRELOAD', 'CIBYP_LAYER_READY')]
        environment += ['TERM=xterm-256color', 'COLORTERM=truecolor']
        def spawned(term, pid, error, _data):
            if error:
                self.notice.set_text('启动失败：' + str(error))
            else:
                term._child_running = True
                term._child_pid = pid
                self.notice.set_text(f'工作目录：{self.cwd} · 进程 {pid}')
        terminal.spawn_async(Vte.PtyFlags.DEFAULT, str(self.cwd), [shell, '-l'], environment, GLib.SpawnFlags.DEFAULT, None, None, -1, None, spawned, None)
        self.colors()
        terminal.grab_focus()

    def colors(self):
        def rgba(value):
            result = Gdk.RGBA()
            result.parse(value)
            return result
        dark = ui.config()['theme'] == 'dark'
        palette = ['#4d596c', '#cb5c6c', '#398773', '#ac793a', '#5279c4', '#9b6eb7', '#388ea0', '#d7e1ee', '#78879e', '#ed8592', '#77b69a', '#d6ad71', '#87a8f0', '#c3a0df', '#7bbdcc', '#f2f5fb']
        for terminal in self.terminals:
            terminal.set_colors(rgba(ui.palette()['text']), rgba(ui.palette()['bg']), [rgba(value) for value in palette])

    def copy(self):
        terminal = self.current()
        if terminal:
            terminal.copy_clipboard_format(Vte.Format.TEXT)

    def paste(self):
        terminal = self.current()
        if terminal:
            terminal.paste_clipboard()
            terminal.grab_focus()

    def font(self, change):
        terminal = self.current()
        if terminal:
            terminal._font_size = max(8, min(28, terminal._font_size+change))
            terminal.set_font(Pango.FontDescription.from_string(f'DejaVu Sans Mono {terminal._font_size}'))

    def search(self):
        terminal = self.current()
        if not terminal:
            return
        def find(value):
            import re
            if value:
                # VTE requires PCRE2_MULTILINE for terminal searches.
                terminal.search_set_regex(Vte.Regex.new_for_search(re.escape(value), -1, 0x00000400), 0)
                self.notice.set_text('找到匹配内容' if terminal.search_find_next() else '没有找到匹配内容')
        ui.dialog(self, '查找终端内容', actions=[('取消', None), ('查找', find)], entry='')

    def close_tab(self, terminal):
        if terminal not in self.terminals:
            return
        def remove():
            self.end_child(terminal)
            index = self.terminals.index(terminal)
            self.terminals.remove(terminal)
            self.tabs.remove_page(index)
            if not self.terminals:
                self.destroy()
        if terminal._child_running:
            ui.dialog(self, '关闭这个终端？', '此标签页中运行的任务会结束。', [('取消', None), ('关闭', lambda _: remove())])
        else:
            remove()

    def end_child(self, terminal):
        if terminal._child_running and getattr(terminal, '_child_pid', None):
            try:
                os.kill(terminal._child_pid, signal.SIGHUP)
            except ProcessLookupError:
                pass
            terminal._child_running = False

    def close_requested(self, *_):
        if any(terminal._child_running for terminal in self.terminals):
            ui.dialog(self, '关闭所有终端？', '正在运行的任务会结束。', [('取消', None), ('关闭全部', lambda _: self.destroy())])
            return True
        return False
