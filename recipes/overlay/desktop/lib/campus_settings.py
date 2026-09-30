"""Immediate, persistent desktop preferences shared by every application."""
import json
import platform
import shutil
import subprocess
from gi.repository import Gtk
import cibypui as ui
from campus_core import ACCENTS


class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='设置 · Campus')
        self.set_default_size(880, 650)
        ui.window_frame(self, '设置', 'settings')
        layout = ui.box(spacing=0)
        side = ui.box(True, 8)
        side.set_size_request(170, -1)
        side.add_css_class('sidebar')
        side.append(ui.label('校园桌面', 'heading'))
        side.append(ui.label('把桌面调成喜欢的样子', 'dim'))
        self.stack = Gtk.Stack(hexpand=True, vexpand=True)
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        for title, name, glyph, creator in [('外观', 'appearance', 'image', self.appearance), ('桌面与任务栏', 'desktop', 'grid', self.desktop), ('快捷键', 'shortcuts', 'terminal', self.keyboard), ('显示与系统', 'system', 'settings', self.system)]:
            side.append(ui.button(title, lambda name=name: self.stack.set_visible_child_name(name), glyph, 'flat'))
            scroll = Gtk.ScrolledWindow()
            page = ui.pad(ui.box(True, 18), 25)
            page.append(ui.label(title, 'title'))
            creator(page)
            scroll.set_child(page)
            self.stack.add_named(scroll, name)
        layout.append(side)
        layout.append(self.stack)
        self.set_child(layout)
        ui.context_menu(layout, [('外观设置', lambda: self.stack.set_visible_child_name('appearance'), 'image'), ('桌面设置', lambda: self.stack.set_visible_child_name('desktop'), 'grid')])

    def section(self, page, title, detail=None):
        card = ui.box(True, 12)
        card.add_css_class('card')
        card.append(ui.label(title, 'heading'))
        if detail:
            text = ui.label(detail, 'dim')
            text.set_wrap(True)
            card.append(text)
        page.append(card)
        return card

    def appearance(self, page):
        card = self.section(page, '深浅色', '立即应用到桌面、任务栏与已打开的内置应用。')
        row = ui.box()
        self.theme_buttons = {}
        for title, value in [('晴日 · 浅色', 'light'), ('晚自习 · 深色', 'dark')]:
            item = ui.button(title, lambda value=value: ui.set_preferences(theme=value), 'image')
            item.set_hexpand(True)
            self.theme_buttons[value] = item
            row.append(item)
        card.append(row)
        card = self.section(page, '强调色', '选中状态、按钮和进度条使用统一颜色。')
        row = ui.box()
        self.accent_buttons = {}
        for value, title in [('blue', '晴空'), ('mint', '薄荷'), ('rose', '樱花'), ('violet', '丁香'), ('orange', '日落')]:
            item = ui.button('● ' + title, lambda value=value: ui.set_preferences(accent=value))
            item.set_hexpand(True)
            provider = Gtk.CssProvider()
            provider.load_from_data(f'button {{ color: {ACCENTS[value]}; }}'.encode())
            item.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1)
            self.accent_buttons[value] = item
            row.append(item)
        card.append(row)
        card = self.section(page, '校园壁纸', '用柔和的天空、教学楼与树影，让桌面轻松一些。')
        row = ui.box()
        self.wallpaper_buttons = {}
        for title, value in [('校园一角', 'campus'), ('课间天空', 'sky'), ('几何笔记', 'notebook')]:
            item = ui.button(title, lambda value=value: ui.set_preferences(wallpaper=value), 'image')
            item.set_hexpand(True)
            self.wallpaper_buttons[value] = item
            row.append(item)
        card.append(row)
        def update():
            managed = ui.config().get('appearance_source') == 'app'
            self.sync_label.set_text('外观由 CIBYP App 的个性化设置统一管理，修改后实时应用到两端。' if managed else '独立桌面外观；连接 CIBYP App 后自动跟随 App。')
            self.color_label.set_text(f"强调色 {ui.accent()}   ·   背景色 {ui.palette()['bg']}")
            self.background_picker.set_sensitive(not managed)
            background = ui.Gdk.RGBA()
            background.parse(ui.palette()['bg'])
            self.background_picker.set_rgba(background)
            for buttons, name in [(self.theme_buttons, 'theme'), (self.accent_buttons, 'accent'), (self.wallpaper_buttons, 'wallpaper')]:
                for value, item in buttons.items():
                    selected = ui.accent() == ACCENTS[value] if name == 'accent' else ui.config()[name] == value
                    item.add_css_class('selected') if selected else item.remove_css_class('selected')
                    if name in ('theme', 'accent'):
                        item.set_sensitive(not managed)
        card = self.section(page, 'App 与 VM 个性化同步')
        self.sync_label = ui.label('', 'dim')
        self.sync_label.set_wrap(True)
        card.append(self.sync_label)
        self.color_label = ui.label('', 'dim')
        card.append(self.color_label)
        row = ui.box()
        row.append(ui.label('背景色', expand=True))
        self.background_picker = Gtk.ColorButton(title='选择背景色', use_alpha=False)
        def background_changed(widget):
            color = widget.get_rgba()
            value = '#' + ''.join(f'{round(part*255):02x}' for part in (color.red, color.green, color.blue))
            ui.set_preferences(background_color=value)
        self.background_picker.connect('color-set', background_changed)
        row.append(self.background_picker)
        card.append(row)
        ui.on_theme(update)
        update()

    def switch(self, card, title, key, default=False):
        row = ui.box()
        row.append(ui.label(title, expand=True))
        item = Gtk.Switch(active=bool(ui.config().get(key, default)), valign=Gtk.Align.CENTER)
        item.connect('notify::active', lambda *_: ui.set_preferences(**{key: item.get_active()}))
        row.append(item)
        card.append(row)

    def desktop(self, page):
        card = self.section(page, '桌面', '右键桌面可以新建文件、打开终端或调整外观。')
        self.switch(card, '显示桌面快捷方式', 'show_desktop_icons', True)
        self.switch(card, '文件管理器显示隐藏文件', 'show_hidden')
        card = self.section(page, '固定到任务栏', '应用运行后仍显示在任务栏；右键应用可管理固定状态。')
        self.pin_buttons = {}
        for key, title, glyph in [('files', '文件', 'files'), ('browser', '浏览器', 'browser'), ('terminal', '终端', 'terminal'), ('editor', '编辑器', 'editor'), ('calc', '计算器', 'calc'), ('viewer', '图片', 'image'), ('settings', '设置', 'settings')]:
            item = Gtk.CheckButton(label=title, active=key in ui.config()['pinned'])
            def changed(widget, key=key):
                pinned = ui.config()['pinned']
                if widget.get_active() and key not in pinned:
                    pinned.append(key)
                elif not widget.get_active() and key in pinned:
                    pinned.remove(key)
                ui.set_preferences(pinned=pinned)
            item.connect('toggled', changed)
            card.append(item)
            self.pin_buttons[key] = item
        def update():
            for key, item in self.pin_buttons.items():
                active = key in ui.config()['pinned']
                if item.get_active() != active:
                    item.set_active(active)
        ui.on_theme(update)
        card = self.section(page, '窗口与工作区')
        card.append(ui.label('标题栏：拖动移动；双击最大化；右键打开窗口菜单。\n任务栏：点击恢复窗口；再次点击最小化；同一应用的多个窗口集中显示。\n右下角细条：显示桌面；再次点击恢复刚刚隐藏的窗口。', 'dim'))

    def keyboard(self, page):
        card = self.section(page, '常用快捷键')
        for key, title in [('Super / Super + 空格', '打开开始菜单'), ('Super + E', '打开文件管理器'), ('Super + Enter', '打开终端'), ('Super + D', '显示 / 恢复桌面'), ('Super + ↑ / ↓', '最大化 / 最小化'), ('Super + ← / →', '窗口贴靠屏幕左 / 右半边'), ('Alt + Tab / Alt + Shift + Tab', '切换窗口'), ('Alt + F4', '关闭当前窗口'), ('Super + 1 … 4', '切换工作区'), ('Super + Shift + 1 … 4', '把窗口移到工作区'), ('Print Screen', '截图到图片文件夹'), ('Super + 鼠标左 / 右键', '移动 / 调整窗口大小')]:
            row = ui.box()
            row.append(ui.label(title, expand=True))
            row.append(ui.label(key, 'dim'))
            card.append(row)
        card = self.section(page, '应用快捷键')
        card.append(ui.label('文件：Ctrl + C / X / V，F2 重命名，Delete 移到回收站。\n编辑器：Ctrl + S 保存，Ctrl + F 查找，Ctrl + H 替换，Ctrl + Z 撤销。\n终端：Ctrl + Shift + C / V 复制粘贴，Ctrl + Shift + T 新标签页。\n图片：← / → 切换，空格播放或暂停，R 旋转。', 'dim'))

    def system(self, page):
        card = self.section(page, '显示器', '当前会话使用原生 Wayland。')
        self.outputs = ui.box(True)
        card.append(self.outputs)
        def complete(outputs, error):
            if error:
                self.outputs.append(ui.label('未连接到 Wayland 桌面会话', 'dim'))
                return
            for output in outputs:
                text = f'{output["name"]} · {output.get("current_mode", {}).get("width", 0)} × {output.get("current_mode", {}).get("height", 0)}'
                row = ui.box()
                row.append(ui.label(text, expand=True))
                modes = output.get('modes', [])
                if modes:
                    values = list(dict.fromkeys(f'{mode["width"]}x{mode["height"]}' for mode in modes))
                    selector = Gtk.DropDown.new_from_strings(values)
                    current = output.get('current_mode') or {}
                    selected = f'{current.get("width")}x{current.get("height")}'
                    if selected in values:
                        selector.set_selected(values.index(selected))
                    def apply(item, _spec, name=output['name'], values=values):
                        mode = values[item.get_selected()]
                        ui.sway(f'output {json.dumps(name)} mode {mode}')
                    selector.connect('notify::selected', apply)
                    row.append(selector)
                self.outputs.append(row)
        ui.background(lambda: json.loads(subprocess.check_output(['swaymsg', '-r', '-t', 'get_outputs'], timeout=3)), complete)
        card = self.section(page, '系统')
        card.append(ui.label(f'CIBYP OS · Campus 桌面\nLinux {platform.release()}\n{platform.machine()} · GTK 4 · Sway / Wayland', 'dim'))
        card.append(ui.button('系统信息与许可证', lambda: ui.launch(['cibyp-about']), 'info'))


class AboutWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='关于 CIBYP OS')
        self.set_default_size(560, 480)
        ui.window_frame(self, '关于', 'info')
        content = ui.pad(ui.box(True, 18), 30)
        content.append(ui.icon('grid', 72, True))
        content.append(ui.label('CIBYP OS', 'title'))
        content.append(ui.label('Campus · 把校园的轻松带进桌面', 'heading'))
        text = ui.label('原生 Wayland 桌面，统一的应用与窗口体验。\n\n桌面：Sway + GTK 4 + layer-shell\n内核：' + platform.release() + '\n架构：' + platform.machine() + '\n\nCopyright © 2026 B5-Software\nGPL-3.0-or-later · 自由软件', 'dim')
        text.set_wrap(True)
        content.append(text)
        content.append(ui.button('打开项目主页', lambda: ui.launch(['chromium', '--ozone-platform=wayland', 'https://github.com/B5-Software/cibyp-vm-os']), 'browser'))
        self.set_child(content)
