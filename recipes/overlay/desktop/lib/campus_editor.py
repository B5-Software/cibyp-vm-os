"""Tabbed UTF-8 editor with native undo, find/replace and safe saves."""
import os
from pathlib import Path
import sys
from gi.repository import Gtk, GLib
import cibypui as ui
from campus_core import atomic_write


class Document:
    def __init__(self, owner, path=None):
        self.owner, self.path, self.stamp = owner, None, None
        self.buffer = Gtk.TextBuffer()
        self.buffer.set_enable_undo(True)
        self.view = Gtk.TextView(buffer=self.buffer, monospace=True)
        self.view.add_css_class('mono')
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_left_margin(18)
        self.view.set_right_margin(18)
        self.view.set_top_margin(15)
        self.scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.scroll.set_child(self.view)
        self.tab = ui.box(spacing=5)
        self.name = ui.label('未命名')
        self.tab.append(self.name)
        self.tab.append(ui.button('×', lambda: owner.close_document(self), css='flat', tip='关闭标签页'))
        self.buffer.connect('modified-changed', lambda *_: self.update_name())
        self.buffer.connect('mark-set', lambda *_: owner.update_status())
        if path:
            self.load(path)

    def text(self):
        return self.buffer.get_text(*self.buffer.get_bounds(), True)

    def load(self, path):
        target = Path(path)
        if target.stat().st_size > 16 * 1024 * 1024:
            raise ValueError('文件超过 16 MB，请使用专门的大文件编辑器。')
        text = target.read_text(encoding='utf-8-sig')
        self.buffer.begin_irreversible_action()
        self.buffer.set_text(text)
        self.buffer.end_irreversible_action()
        self.buffer.set_modified(False)
        self.path, self.stamp = target.resolve(), target.stat().st_mtime_ns
        self.update_name()

    def update_name(self):
        title = self.path.name if self.path else '未命名'
        self.name.set_text(('● ' if self.buffer.get_modified() else '') + title)
        self.owner.set_title(title + ' · 校园编辑器')
        self.owner.update_status()


class EditorWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='校园编辑器')
        self.set_default_size(1000, 670)
        ui.window_frame(self, '编辑器', 'editor')
        self.documents, self.find_mark = [], None
        content = ui.box(True, 0)
        toolbar = ui.box()
        toolbar.add_css_class('toolbar')
        for text, callback, glyph in [('新建', self.new, 'add'), ('打开', self.open, 'folder'), ('保存', self.save, 'save'), ('另存为', self.save_as, 'save'), ('查找', self.toggle_find, 'search')]:
            toolbar.append(ui.button(text, callback, glyph, tip=text))
        wrap = Gtk.CheckButton(label='自动换行', active=True)
        wrap.set_hexpand(True)
        wrap.set_halign(Gtk.Align.END)
        wrap.connect('toggled', lambda item: [doc.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR if item.get_active() else Gtk.WrapMode.NONE) for doc in self.documents])
        toolbar.append(wrap)
        content.append(toolbar)
        self.find_bar = ui.box()
        self.find_bar.add_css_class('toolbar')
        self.query = Gtk.Entry(placeholder_text='查找内容', hexpand=True)
        self.replacement = Gtk.Entry(placeholder_text='替换为', hexpand=True)
        self.query.connect('activate', lambda *_: self.find())
        self.find_bar.append(self.query)
        self.find_bar.append(ui.button('上一个', lambda: self.find(True)))
        self.find_bar.append(ui.button('下一个', self.find))
        self.find_bar.append(self.replacement)
        self.find_bar.append(ui.button('替换', self.replace))
        self.find_bar.append(ui.button('全部替换', self.replace_all))
        self.find_bar.append(ui.button('×', self.toggle_find, css='flat'))
        self.find_bar.set_visible(False)
        content.append(self.find_bar)
        self.tabs = Gtk.Notebook(scrollable=True, vexpand=True)
        self.tabs.connect('switch-page', lambda *_: GLib.idle_add(lambda: (self.update_status(), False)[1]))
        content.append(self.tabs)
        self.status = ui.label('UTF-8', 'status')
        content.append(self.status)
        self.set_child(content)
        self.connect('close-request', self.close_requested)
        ui.shortcuts(self, {'ctrl+n': self.new, 'ctrl+o': self.open, 'ctrl+s': self.save, 'ctrl+shift+s': self.save_as, 'ctrl+f': self.toggle_find, 'ctrl+h': self.show_replace, 'ctrl+w': lambda: self.close_document(self.current()), 'f3': self.find, 'shift+f3': lambda: self.find(True), 'escape': lambda: self.find_bar.set_visible(False)})
        for path in sys.argv[1:]:
            self.open_path(path)
        if not self.documents:
            self.new()

    def current(self):
        page = self.tabs.get_current_page()
        return self.documents[page] if 0 <= page < len(self.documents) else None

    def add(self, doc):
        self.documents.append(doc)
        page = self.tabs.append_page(doc.scroll, doc.tab)
        self.tabs.set_tab_reorderable(doc.scroll, False)
        self.tabs.set_current_page(page)
        doc.view.grab_focus()

    def new(self):
        self.add(Document(self))

    def open(self):
        ui.choose_file(self, self.open_path)

    def open_path(self, path):
        try:
            target = Path(path).resolve()
            for index, doc in enumerate(self.documents):
                if doc.path == target:
                    self.tabs.set_current_page(index)
                    return
            self.add(Document(self, target))
        except Exception as error:
            ui.dialog(self, '无法打开文件', str(error))

    def save(self, after=None):
        doc = self.current()
        if not doc:
            return
        if not doc.path:
            return self.save_as(after)
        def write():
            try:
                atomic_write(doc.path, doc.text())
                doc.stamp = doc.path.stat().st_mtime_ns
                doc.buffer.set_modified(False)
                self.status.set_text(f'已保存 · {doc.path}')
                if after:
                    after()
            except Exception as error:
                ui.dialog(self, '保存失败', str(error))
        if doc.path.exists() and doc.stamp != doc.path.stat().st_mtime_ns:
            ui.dialog(self, '文件已被其他程序修改', '覆盖会替换磁盘上的内容。也可以先另存为。', [('取消', None), ('另存为', lambda _: self.save_as(after)), ('覆盖', lambda _: write())])
        else:
            write()

    def save_as(self, after=None):
        doc = self.current()
        if not doc:
            return
        def selected(path):
            target = Path(path).absolute()
            def write():
                try:
                    atomic_write(target, doc.text())
                    doc.path, doc.stamp = target, target.stat().st_mtime_ns
                    doc.buffer.set_modified(False)
                    doc.update_name()
                    if after:
                        after()
                except Exception as error:
                    ui.dialog(self, '保存失败', str(error))
            if target.exists() and target != doc.path:
                ui.dialog(self, '替换已有文件？', str(target), [('取消', None), ('替换', lambda _: write())])
            else:
                write()
        ui.choose_file(self, selected, save=True, name=doc.path.name if doc.path else '未命名.txt')

    def close_document(self, doc):
        if doc not in self.documents:
            return
        def remove():
            index = self.documents.index(doc)
            self.documents.remove(doc)
            self.tabs.remove_page(index)
            if not self.documents:
                self.new()
        if doc.buffer.get_modified():
            self.tabs.set_current_page(self.documents.index(doc))
            ui.dialog(self, '保存更改？', doc.path.name if doc.path else '未命名文档', [('取消', None), ('不保存', lambda _: remove()), ('保存', lambda _: self.save(remove))])
        else:
            remove()

    def close_requested(self, *_):
        dirty = next((doc for doc in self.documents if doc.buffer.get_modified()), None)
        if dirty:
            self.tabs.set_current_page(self.documents.index(dirty))
            ui.dialog(self, '还有未保存的文档', '保存当前文档后会继续检查其他标签页。', [('取消', None), ('不保存', lambda _: (dirty.buffer.set_modified(False), self.close())), ('保存', lambda _: self.save(self.close))])
            return True
        return False

    def toggle_find(self):
        self.find_bar.set_visible(not self.find_bar.get_visible())
        if self.find_bar.get_visible():
            self.query.grab_focus()

    def show_replace(self):
        self.find_bar.set_visible(True)
        self.query.grab_focus()

    def find(self, reverse=False):
        doc, text = self.current(), self.query.get_text()
        if not doc or not text:
            return
        bounds = doc.buffer.get_selection_bounds()
        start = bounds[0 if reverse else 1] if bounds else doc.buffer.get_iter_at_mark(doc.buffer.get_insert())
        flags = Gtk.TextSearchFlags.TEXT_ONLY
        match = start.backward_search(text, flags, None) if reverse else start.forward_search(text, flags, None)
        if not match:
            start = doc.buffer.get_end_iter() if reverse else doc.buffer.get_start_iter()
            match = start.backward_search(text, flags, None) if reverse else start.forward_search(text, flags, None)
        if match:
            doc.buffer.select_range(*match)
            doc.view.scroll_to_iter(match[0], .15, False, 0, 0)
        else:
            self.status.set_text('没有找到匹配内容')

    def replace(self):
        doc = self.current()
        if not doc or not self.query.get_text():
            return
        bounds = doc.buffer.get_selection_bounds()
        if bounds and doc.buffer.get_text(*bounds, True) == self.query.get_text():
            doc.buffer.begin_user_action()
            doc.buffer.delete(*bounds)
            doc.buffer.insert_at_cursor(self.replacement.get_text())
            doc.buffer.end_user_action()
        self.find()

    def replace_all(self):
        doc, query = self.current(), self.query.get_text()
        if not doc or not query:
            return
        text = doc.text()
        count = text.count(query)
        if count:
            doc.buffer.begin_user_action()
            doc.buffer.delete(*doc.buffer.get_bounds())
            doc.buffer.insert_at_cursor(text.replace(query, self.replacement.get_text()))
            doc.buffer.end_user_action()
        self.status.set_text(f'已替换 {count} 处')

    def update_status(self):
        doc = self.current()
        if doc:
            cursor = doc.buffer.get_iter_at_mark(doc.buffer.get_insert())
            self.status.set_text(f'第 {cursor.get_line()+1} 行 · 第 {cursor.get_line_offset()+1} 列  |  {doc.buffer.get_char_count()} 字符  |  UTF-8')
