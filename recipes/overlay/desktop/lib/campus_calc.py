"""Scientific calculator; expressions are parsed, never executed."""
import json
import math
import re
from gi.repository import Gtk, Gdk
import cibypui as ui
from campus_core import CONFIG_DIR, atomic_write, evaluate


class CalculatorWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='计算器 · Campus')
        self.set_default_size(560, 570)
        ui.window_frame(self, '计算器', 'calc')
        self.memory, self.answer, self.degrees = 0., 0., False
        self.history_file = CONFIG_DIR / 'calculator-history.json'
        try:
            history = json.loads(self.history_file.read_text())
            self.history = [row for row in history if isinstance(row, list) and len(row) == 2 and all(isinstance(value, str) for value in row)][:50]
        except (OSError, ValueError, TypeError):
            self.history = []
        content = ui.pad(ui.box(True, 12))
        self.display = Gtk.Entry(placeholder_text='输入算式，例如 (12 + 8) / 5', xalign=1)
        self.display.add_css_class('calculator-display')
        self.display.connect('activate', lambda *_: self.calculate())
        content.append(self.display)
        self.notice = ui.label('支持括号、科学函数和键盘输入', 'dim')
        content.append(self.notice)
        memory = ui.box()
        for text, callback in [('MC', lambda: self.set_memory(0)), ('MR', lambda: self.insert(format(self.memory, '.12g'))), ('MS', lambda: self.set_memory(self.value())), ('M+', lambda: self.set_memory(self.memory + self.value())), ('M−', lambda: self.set_memory(self.memory - self.value()))]:
            memory.append(ui.button(text, callback, tip={'MC': '清除记忆', 'MR': '读取记忆', 'MS': '保存记忆', 'M+': '加到记忆', 'M−': '从记忆减去'}[text]))
        angle = Gtk.ToggleButton(label='RAD')
        angle.connect('toggled', lambda item: (setattr(self, 'degrees', item.get_active()), item.set_label('DEG' if item.get_active() else 'RAD')))
        memory.append(angle)
        content.append(memory)
        grid = Gtk.Grid(column_spacing=7, row_spacing=7, column_homogeneous=True)
        keys = [['sin(', 'cos(', 'tan(', '(', ')'], ['sqrt(', 'ln(', 'log(', 'C', '⌫'], ['π', '7', '8', '9', '÷'], ['e', '4', '5', '6', '×'], ['xʸ', '1', '2', '3', '−'], ['%', '±', '0', '.', '+'], ['Ans', '复制', '=', '=', '=']]
        for row, values in enumerate(keys):
            for col, key in enumerate(values):
                if row == 6 and col > 2:
                    continue
                callback = self.calculate if key == '=' else self.copy if key == '复制' else lambda key=key: self.key(key)
                grid.attach(ui.button(key, callback, css='calculator-key primary' if key == '=' else 'calculator-key'), col, row, 3 if row == 6 and col == 2 else 1, 1)
        content.append(grid)
        self.history_button = ui.button('历史记录', self.show_history, 'history')
        content.append(self.history_button)
        self.set_child(content)
        ui.context_menu(content, [('复制结果', self.copy, 'copy'), ('历史记录', self.show_history, 'history'), ('清空', lambda: self.display.set_text(''), 'trash')])
        ui.shortcuts(self, {'escape': lambda: self.display.set_text(''), 'ctrl+c': self.copy})
        self.display.grab_focus()

    def insert(self, value):
        bounds = self.display.get_selection_bounds()
        if bounds:
            start, end = bounds
            self.display.delete_text(start, end)
            self.display.set_position(start)
        position = self.display.get_position()
        self.display.insert_text(value, position)
        self.display.set_position(position + len(value))
        self.display.grab_focus()

    def key(self, key):
        if key == 'C':
            self.display.set_text('')
        elif key == '⌫':
            bounds = self.display.get_selection_bounds()
            if bounds:
                self.display.delete_text(*bounds)
            else:
                position = self.display.get_position()
                self.display.delete_text(max(position-1, 0), position)
        elif key == '±':
            text = self.display.get_text()
            self.display.set_text(f'-({text})' if text else '-')
        else:
            self.insert({'π': 'pi', '÷': '/', '×': '*', '−': '-', 'xʸ': '**', '%': '/100', 'Ans': 'ans'}.get(key, key))
        self.display.grab_focus()

    def value(self):
        expression = re.sub(r'\bans\b', f'({self.answer!r})', self.display.get_text())
        return evaluate(expression, self.degrees)

    def calculate(self):
        expression = self.display.get_text()
        if not expression.strip():
            return
        try:
            self.answer = self.value()
            result = format(self.answer, '.12g')
            self.display.set_text(result)
            self.display.set_position(-1)
            self.notice.set_text(expression + ' = ' + result)
            self.history.insert(0, [expression, result])
            self.history = self.history[:50]
            atomic_write(self.history_file, json.dumps(self.history, ensure_ascii=False))
        except Exception as error:
            self.notice.set_text('无法计算：' + str(error))

    def set_memory(self, value):
        self.memory = value
        self.notice.set_text('记忆值：' + format(value, '.12g'))

    def copy(self):
        self.get_clipboard().set(self.display.get_text())
        self.notice.set_text('已复制到剪贴板')

    def show_history(self):
        if not self.history:
            ui.dialog(self, '历史记录', '计算后会显示在这里。')
            return
        options = [(expression + ' = ' + result, lambda value=expression: self.display.set_text(value), 'history') for expression, result in self.history[:12]]
        options += [None, ('清空历史记录', self.clear_history, 'trash')]
        ui.popover(self.history_button, options)

    def clear_history(self):
        self.history = []
        atomic_write(self.history_file, '[]')
