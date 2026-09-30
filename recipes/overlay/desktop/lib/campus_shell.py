"""Bottom taskbar, searchable launcher, clock and window controls for Wayland."""
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
from gi.repository import Gdk, Gio, GLib, Gtk, Pango
import cibypui as ui
from campus_core import ACCENTS
from campus_windows import WindowManager, command, query

APPS = {
    'files': ('文件', 'files', ['cibyp-files']),
    'browser': ('浏览器', 'browser', ['chromium', '--ozone-platform=wayland']),
    'terminal': ('终端', 'terminal', ['cibyp-terminal']),
    'editor': ('编辑器', 'editor', ['cibyp-editor']),
    'calc': ('计算器', 'calc', ['cibyp-calc']),
    'viewer': ('图片', 'image', ['cibyp-viewer']),
    'settings': ('设置', 'settings', ['cibyp-settings']),
    'about': ('关于', 'info', ['cibyp-about']),
}


def app_key(row):
    value = row['app_id'].lower()
    for key in APPS:
        if value.endswith('.' + key) or value == 'cibyp-' + key:
            return key
    if 'foot' in value or 'terminal' in value:
        return 'terminal'
    if 'chrom' in value or 'firefox' in value:
        return 'browser'
    return value


class ShellWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='Campus 任务栏')
        self.add_css_class('campus')
        self.set_decorated(False)
        ui.try_layer_shell(self, 'cibyp-panel', exclusive=64)
        self.manager = WindowManager()
        self.windows, self.signature, self.polling = [], None, False
        self.popup = None
        ui.shortcuts(self, {'escape': lambda: self.popup.popdown() if self.popup else None})
        self.skip_super = False
        self.binding_process = subprocess.Popen(['swaymsg', '-m', '-r', '-t', 'subscribe', '["binding"]'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        def bindings():
            for line in self.binding_process.stdout:
                try:
                    binding = json.loads(line).get('binding', {})
                    if binding.get('command') == 'nop campus-super-down':
                        self.skip_super = False
                    elif 'Mod4' in binding.get('event_state_mask', []) and binding.get('symbols') != ['Super_L']:
                        self.skip_super = True
                except ValueError:
                    pass
        threading.Thread(target=bindings, daemon=True).start()
        self.connect('destroy', lambda *_: self.binding_process.terminate())
        panel = ui.box(spacing=12)
        panel.add_css_class('taskbar')
        panel.set_size_request(-1, 48)
        self.start_button = ui.button('Campus', self.launcher, 'grid', 'task flat', '开始菜单 · Super')
        panel.append(self.start_button)
        panel.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        self.tasks = ui.box(spacing=5)
        scroll = Gtk.ScrolledWindow(hexpand=True)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        scroll.set_child(self.tasks)
        panel.append(scroll)
        self.workspace_button = ui.button('1', self.workspaces, 'grid', 'flat', '切换工作区')
        panel.append(self.workspace_button)
        self.quick_button = ui.button('', self.quick_settings, 'settings', 'flat', '快捷设置')
        panel.append(self.quick_button)
        self.clock_button = Gtk.Button()
        self.clock_button.add_css_class('flat')
        self.clock_label = Gtk.Label()
        self.clock_button.set_child(self.clock_label)
        self.clock_button.connect('clicked', lambda *_: self.calendar())
        panel.append(self.clock_button)
        panel.append(ui.button('│', self.manager.show_desktop, css='flat', tip='显示桌面 · Super+D'))
        ui.context_menu(panel, [('显示 / 恢复桌面', self.manager.show_desktop, 'grid'), ('个性化', lambda: ui.launch(['cibyp-settings']), 'settings'), ('截图', self.screenshot, 'image')])
        self.set_child(panel)
        ui.on_theme(self.theme_changed)
        self.server = self.control_socket()
        self.theme_changed()
        self.tick()
        self.poll()
        GLib.timeout_add_seconds(1, self.tick)
        GLib.timeout_add(400, self.poll)

    def theme_changed(self):
        self.signature = None
        self.render_tasks()
        accent = ui.accent()
        background = ui.palette()['surface']
        colors = ui.palette()
        command(f"client.focused {accent} {background} {colors['text']} {accent} {accent}; client.unfocused {colors['line']} {colors['raised']} {colors['dim']} {colors['line']} {colors['line']}; client.focused_inactive {colors['line']} {colors['raised']} {colors['dim']} {colors['line']} {colors['line']}")

    def tick(self):
        now = datetime.now()
        self.clock_label.set_text(now.strftime('%H:%M\n%m月%d日'))
        self.clock_button.set_tooltip_text(now.strftime('%Y年%m月%d日 ') + '星期' + '一二三四五六日'[now.weekday()])
        return True

    def poll(self):
        if self.polling:
            return True
        self.polling = True
        def complete(result, error):
            self.polling = False
            if error:
                print('Taskbar:', error)
                return
            self.windows, workspaces = result
            current = next((row['name'] for row in workspaces if row['focused']), '1')
            self.workspace_button.get_child().get_last_child().set_text(current)
            signature = json.dumps([self.windows, ui.config()['pinned']], sort_keys=True)
            if signature != self.signature:
                self.signature = signature
                self.render_tasks()
        ui.background(lambda: (self.manager.snapshot(), query('get_workspaces')), complete)
        return True

    def render_tasks(self):
        groups = {key: [] for key in ui.config()['pinned']}
        for row in self.windows:
            groups.setdefault(app_key(row), []).append(row)
        self.groups = groups
        if not hasattr(self, 'task_widgets'):
            self.task_widgets = {}
        for key in list(self.task_widgets):
            if key not in groups:
                self.tasks.remove(self.task_widgets.pop(key))
        previous = None
        for key, rows in groups.items():
            title, glyph, argv = APPS.get(key, (rows[0]['title'] if rows else key, ui.app_icon_name(key), None))
            if key not in self.task_widgets:
                item = Gtk.Button()
                item.add_css_class('task')
                content = ui.box(spacing=7)
                content.append(ui.icon(glyph, 32, True))
                item.caption = ui.label()
                item.caption.set_max_width_chars(17)
                item.caption.set_ellipsize(Pango.EllipsizeMode.END)
                content.append(item.caption)
                item.set_child(content)
                item.connect('clicked', lambda item, key=key: self.task_action(key, item))
                ui.context_menu(item, lambda key=key: self.task_options(key))
                middle = Gtk.GestureClick()
                middle.set_button(2)
                middle.connect('pressed', lambda *_args, argv=argv: ui.launch(argv) if argv else None)
                item.add_controller(middle)
                self.tasks.append(item)
                self.task_widgets[key] = item
            item = self.task_widgets[key]
            item.remove_css_class('active')
            item.remove_css_class('running')
            if rows:
                item.add_css_class('active' if any(row['focused'] for row in rows) else 'running')
            item.caption.set_visible(bool(rows))
            item.caption.set_text(rows[0]['title'] + (f'  · {len(rows)}' if len(rows) > 1 else '') if rows else '')
            item.set_tooltip_text(title if not rows else '\n'.join(row['title'] + (' · 已最小化' if row['minimized'] else '') for row in rows))
            self.tasks.reorder_child_after(item, previous)
            previous = item

    def task_action(self, key, item):
        rows = self.groups.get(key, [])
        argv = APPS.get(key, ('', '', None))[2]
        if not rows and argv:
            ui.launch(argv)
        elif len(rows) == 1:
            self.manager.minimize(rows[0]) if rows[0]['focused'] else self.manager.restore(rows[0])
        else:
            ui.popover(item, [(row['title'] + (' · 已最小化' if row['minimized'] else ''), lambda row=row: self.manager.restore(row), ui.app_icon_name(key)) for row in rows])

    def task_options(self, key):
        rows = self.groups.get(key, [])
        title, glyph, argv = APPS.get(key, (key, ui.app_icon_name(key), None))
        result = []
        if argv:
            result.append(('打开新窗口', lambda: ui.launch(argv), glyph))
        result += [(row['title'], lambda row=row: self.manager.restore(row), glyph) for row in rows]
        if rows:
            result += [None, ('最小化所有窗口', lambda: [self.manager.minimize(row) for row in rows], 'back'), ('关闭所有窗口', lambda: [command(f'[con_id={row["id"]}] kill') for row in rows], 'close')]
        if key in APPS:
            result += [None, ('取消固定' if key in ui.config()['pinned'] else '固定到任务栏', lambda: self.toggle_pin(key), 'grid')]
        return result

    def toggle_pin(self, key):
        pinned = ui.config()['pinned']
        pinned.remove(key) if key in pinned else pinned.append(key)
        ui.set_preferences(pinned=pinned)

    def create_popup(self, anchor, child, keyboard=False):
        if self.popup:
            self.popup.popdown()
        self.popup_anchor = anchor
        if keyboard:
            # A global shortcut has no GTK pointer serial for a popup grab.
            # Use a native layer window that owns focus and catches click-away.
            menu = Gtk.ApplicationWindow(application=self.get_application())
            menu.set_decorated(False)
            menu.add_css_class('campus')
            menu.add_css_class('campus-overlay')
            ui.try_layer_shell(menu, 'campus-launcher', layer='overlay', anchors=('top', 'bottom', 'left', 'right'))
            ui.layer_keyboard(menu, True)
            overlay = Gtk.Overlay()
            overlay.set_child(Gtk.Box())
            child.add_css_class('popup-card')
            child.set_halign(Gtk.Align.START)
            child.set_valign(Gtk.Align.END)
            child.set_margin_bottom(0)
            overlay.add_overlay(child)
            menu.set_child(overlay)
            click = Gtk.GestureClick()
            click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            def outside(_gesture, _count, x, y):
                target = overlay.pick(x, y, Gtk.PickFlags.DEFAULT)
                while target and target != child:
                    target = target.get_parent()
                if target != child:
                    menu.close()
            click.connect('pressed', outside)
            overlay.add_controller(click)
            ui.shortcuts(menu, {'escape': menu.close})
            menu.popdown = menu.close
            def closed(*_):
                if self.popup == menu:
                    self.popup = None
                return False
            menu.connect('close-request', closed)
            self.popup = menu
            menu.present()
        else:
            menu = Gtk.Popover()
            menu.set_parent(anchor)
            menu.set_position(Gtk.PositionType.TOP)
            menu.set_has_arrow(False)
            menu.set_autohide(True)
            menu.set_child(child)
            def closed(*_):
                if self.popup == menu:
                    self.popup = None
                GLib.idle_add(lambda: (menu.unparent(), False)[1])
            menu.connect('closed', closed)
            self.popup = menu
            menu.popup()
        return menu

    def launcher(self, keyboard=False):
        if self.popup and self.popup_anchor == self.start_button:
            self.popup.popdown()
            return
        content = ui.pad(ui.box(True, 15), 15)
        content.set_size_request(540, -1)
        heading = ui.box()
        heading.append(ui.label('课间，开启新任务', 'heading', True))
        heading.append(ui.icon('grid', 32, True))
        content.append(heading)
        search = Gtk.SearchEntry(placeholder_text='搜索应用，或输入 / 打开路径…')
        content.append(search)
        grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE)
        grid.set_max_children_per_line(5)
        grid.set_min_children_per_line(5)
        grid.set_row_spacing(8)
        grid.set_column_spacing(8)
        entries = []
        for key, (title, glyph, argv) in APPS.items():
            entries.append((title, key + ' ' + title, glyph, lambda argv=argv: ui.launch(argv)))
        # DesktopAppInfo handles quoted Exec arguments and field codes correctly.
        known = {'cibyp-' + key for key in APPS}
        for application in Gio.AppInfo.get_all():
            identifier = (application.get_id() or '').removesuffix('.desktop')
            if not application.should_show() or identifier in known or identifier.startswith('cibyp-'):
                continue
            entries.append((application.get_display_name(), application.get_display_name() + ' ' + identifier, ui.app_icon_name(identifier), lambda app=application: app.launch([], None)))
        widgets = []
        for title, searchable, glyph, callback in entries:
            item = Gtk.Button()
            item.add_css_class('flat')
            item.add_css_class('launcher-app')
            item.set_tooltip_text(title)
            card = ui.box(True, 8)
            picture = ui.icon(glyph, 43, True)
            picture.set_halign(Gtk.Align.CENTER)
            card.append(picture)
            caption = Gtk.Label(label=title)
            caption.set_max_width_chars(9)
            caption.set_ellipsize(Pango.EllipsizeMode.END)
            card.append(caption)
            item.set_child(card)
            item.connect('clicked', lambda _item, callback=callback: (self.popup.popdown() if self.popup else None, callback()))
            grid.append(item)
            widgets.append((item, searchable.casefold(), callback))
        scroll = Gtk.ScrolledWindow(min_content_height=250, max_content_height=380)
        scroll.set_child(grid)
        content.append(scroll)
        hint = ui.label('Super + E 文件  ·  Super + Enter 终端', 'dim')
        content.append(hint)
        def filter_apps(*_):
            term = search.get_text().casefold().strip()
            count = 0
            for item, searchable, _callback in widgets:
                shown = term in searchable
                item.get_parent().set_visible(shown)
                count += shown
            hint.set_text(f'找到 {count} 个应用' if term else 'Super + E 文件  ·  Super + Enter 终端')
        search.connect('search-changed', filter_apps)
        def activate(*_):
            text = search.get_text().strip()
            if text.startswith(('/', '~/')):
                path = Path(text).expanduser()
                if path.exists():
                    ui.open_path(path)
                    self.popup.popdown()
                else:
                    hint.set_text('这个路径不存在')
            else:
                callback = next((callback for item, _term, callback in widgets if item.get_parent().get_visible()), None)
                if callback:
                    self.popup.popdown()
                    callback()
        search.connect('activate', activate)
        footer = ui.box()
        footer.append(ui.button('设置', lambda: ui.launch(['cibyp-settings']), 'settings', 'flat'))
        footer.append(ui.label('CIBYP OS · Campus', 'dim', True))
        footer.append(ui.button('电源', self.power, 'power', 'flat'))
        content.append(footer)
        self.create_popup(self.start_button, content, keyboard=keyboard)
        search.grab_focus()

    def calendar(self):
        content = ui.pad(ui.box(True, 12), 12)
        content.append(ui.label(datetime.now().strftime('%Y年%m月%d日'), 'heading'))
        content.append(Gtk.Calendar())
        content.append(ui.button('新建课堂笔记', lambda: ui.launch(['cibyp-editor']), 'editor'))
        self.create_popup(self.clock_button, content)

    def workspaces(self):
        ui.popover(self.workspace_button, [(f'工作区 {index}', lambda index=index: command(f'workspace number {index}'), 'grid') for index in range(1, 5)])

    def quick_settings(self):
        content = ui.pad(ui.box(True, 14), 14)
        content.append(ui.label('课间快捷设置', 'heading'))
        managed = ui.config().get('appearance_source') == 'app'
        if managed:
            content.append(ui.label('外观实时跟随 CIBYP App 个性化设置', 'dim'))
        row = ui.box()
        for title, theme in [('晴日 · 浅色', 'light'), ('晚自习 · 深色', 'dark')]:
            item = ui.button(title, lambda theme=theme: ui.set_preferences(theme=theme), 'image')
            item.set_sensitive(not managed)
            row.append(item)
        content.append(row)
        row = ui.box()
        for key in ACCENTS:
            item = ui.button('●', lambda key=key: ui.set_preferences(accent=key), tip=key)
            item.set_sensitive(not managed)
            provider = Gtk.CssProvider()
            provider.load_from_data(f'button {{ color: {ACCENTS[key]}; font-size: 24px; }}'.encode())
            item.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1)
            row.append(item)
        content.append(row)
        if shutil.which('pactl'):
            row = ui.box()
            row.append(ui.label('音量', expand=True))
            row.append(ui.button('−', lambda: ui.launch(['pactl', 'set-sink-volume', '@DEFAULT_SINK@', '-5%'])))
            row.append(ui.button('+', lambda: ui.launch(['pactl', 'set-sink-volume', '@DEFAULT_SINK@', '+5%'])))
            row.append(ui.button('静音', lambda: ui.launch(['pactl', 'set-sink-mute', '@DEFAULT_SINK@', 'toggle'])))
            content.append(row)
        content.append(ui.button('截图', self.screenshot, 'image'))
        content.append(ui.button('全部设置', lambda: ui.launch(['cibyp-settings']), 'settings'))
        content.append(ui.button('电源', self.power, 'power'))
        self.create_popup(self.quick_button, content)

    def power(self):
        content = ui.pad(ui.box(True, 12), 15)
        content.append(ui.label('电源', 'heading'))
        def confirm(action):
            if self.popup:
                self.popup.popdown()
            ui.dialog(self, '重新启动？' if action == 'reboot' else '关闭系统？', '请先保存正在编辑的文件。', [('取消', None), ('重新启动' if action == 'reboot' else '关机', lambda _: ui.launch(['sudo', '-n', 'systemctl', action]))])
        content.append(ui.button('重新启动', lambda: confirm('reboot'), 'refresh'))
        content.append(ui.button('关机', lambda: confirm('poweroff'), 'power', 'danger'))
        self.create_popup(self.quick_button, content)

    def screenshot(self):
        if self.popup:
            self.popup.popdown()
        directory = Path.home() / 'Pictures' / 'Screenshots'
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (datetime.now().strftime('校园截图-%Y%m%d-%H%M%S-%f') + '.png')
        def capture():
            ui.background(lambda: subprocess.run(['grim', str(target)], check=True, capture_output=True, timeout=10), lambda _result, error: ui.dialog(self, '截图失败', str(error)) if error else ui.launch(['cibyp-viewer', str(target)]))
            return False
        GLib.timeout_add(200, capture)

    def control_socket(self):
        path = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / 'cibyp-shell.sock'
        path.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path))
        os.chmod(path, 0o600)
        server.listen(8)
        server.setblocking(False)
        def received(_fd, _condition):
            try:
                client, _ = server.accept()
                # A broken client must not freeze the compositor UI.
                client.settimeout(.05)
                with client:
                    value = client.recv(4096).decode().strip()
                self.dispatch(value)
            except (OSError, ValueError, RuntimeError) as error:
                print('Desktop command:', error)
            return True
        GLib.io_add_watch(server.fileno(), GLib.IO_IN, received)
        return server

    def dispatch(self, value):
        name, _, argument = value.partition(' ')
        if name == 'menu-key':
            def released():
                if not self.skip_super:
                    self.launcher(keyboard=True)
                self.skip_super = False
                return False
            GLib.timeout_add(60, released)
            return
        handlers = {'menu': lambda: self.launcher(keyboard=True), 'calendar': self.calendar, 'power': self.power, 'screenshot': self.screenshot, 'desktop': self.manager.show_desktop, 'maximize': self.manager.maximize, 'minimize': self.manager.minimize, 'next': self.manager.cycle, 'previous': lambda: self.manager.cycle(True), 'left': lambda: self.manager.snap('left'), 'right': lambda: self.manager.snap('right'), 'reload': self.theme_changed}
        if name in handlers:
            handlers[name]()
        elif name in ('minimize-pid', 'maximize-pid'):
            row = self.manager.focused(int(argument))
            if row:
                self.manager.minimize(row) if name.startswith('minimize') else self.manager.maximize(row)
        elif name == 'toast':
            ui.dialog(self, 'CIBYP OS', argument[:500])
