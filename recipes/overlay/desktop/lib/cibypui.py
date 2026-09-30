"""Live campus themes and native GTK4 application primitives."""
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 B5-Software
import glob
import os
from pathlib import Path
import subprocess
import sys
import threading
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_foreign('cairo')
from gi.repository import Gdk, Gio, GLib, Gtk, Pango
from campus_core import CONFIG_DIR, CONFIG_FILE, load_config, update_config, accent_color, appearance_palette
from campus_icons import draw_icon, _round_rect

ROOT = Path(__file__).resolve().parent.parent
_provider = None
_state = load_config()
_callbacks, _windows = [], []
_watch_started = False
_popovers = []


def rgb(value):
    return tuple(int(value[i:i+2], 16)/255 for i in (1, 3, 5))


def color(name='text'):
    return rgb(accent_color(_state) if name == 'accent' else appearance_palette(_state)[name])


def palette():
    return appearance_palette(_state)


def accent():
    return accent_color(_state)


def config():
    return dict(_state)


def apply_theme():
    global _state, _provider
    _state = load_config()
    palette = appearance_palette(_state)
    css = '''
    @define-color accent_color ACCENT;
    @define-color accent_bg_color ACCENT;
    @define-color accent_fg_color white;
    @define-color theme_selected_bg_color ACCENT;
    @define-color theme_selected_fg_color white;
    * { font-family: "Noto Sans CJK SC", "Noto Sans", sans-serif; font-size: 13px; }
    window.campus { background: BG; color: TEXT; }
    window.campus decoration { border-radius: 18px; box-shadow: 0 8px 24px SHADOW; }
    headerbar { background: SURFACE; color: TEXT; border-bottom: 1px solid LINE; min-height: 42px; padding: 5px 10px; box-shadow: none; }
    headerbar label { font-weight: 600; }
    button { background: SURFACE; color: TEXT; border: 1px solid LINE; border-radius: 9px; padding: 7px 11px; min-height: 20px; box-shadow: none; }
    button:hover { background: RAISED; }
    button:checked, button.selected { background: RAISED; border-color: ACCENT; }
    button:disabled { opacity: 0.4; }
    button.flat { background: transparent; border-color: transparent; }
    button.primary { background: ACCENT; color: white; border-color: ACCENT; }
    button.danger { color: #d46676; }
    button.close:hover { background: #dc6676; color: white; }
    entry, searchentry, spinbutton, textview { background: SURFACE; color: TEXT; border-radius: 9px; border: 1px solid LINE; padding: 7px 10px; caret-color: ACCENT; }
    entry:focus-within, searchentry:focus-within { border-color: ACCENT; outline-color: ACCENT; }
    textview { border: none; border-radius: 0; }
    textview text { background: SURFACE; color: TEXT; }
    selection { background: ACCENT; color: white; }
    .toolbar { background: SURFACE; border-bottom: 1px solid LINE; padding: 9px; }
    .sidebar { background: RAISED; border-right: 1px solid LINE; padding: 12px; }
    .status { background: SURFACE; color: DIM; border-top: 1px solid LINE; padding: 7px 12px; }
    .card { background: SURFACE; border: 1px solid LINE; border-radius: 14px; padding: 16px; }
    .campus-title { font-size: 23px; font-weight: 700; }
    .heading { font-size: 16px; font-weight: 600; }
    .dim { color: DIM; }
    .mono, .mono * { font-family: "Noto Sans Mono", "DejaVu Sans Mono", monospace; }
    list, listview, flowbox { background: transparent; color: TEXT; }
    row { border-radius: 9px; padding: 4px; }
    row:selected, row:hover { background: RAISED; color: TEXT; }
    popover contents { background: SURFACE; color: TEXT; border: 1px solid LINE; border-radius: 15px; padding: 7px; box-shadow: 0 8px 20px SHADOW; }
    popover button { border: none; background: transparent; }
    popover button:hover { background: RAISED; }
    popover arrow { background: SURFACE; }
    .taskbar { background: SURFACE; color: TEXT; border-top: 1px solid LINE; padding: 8px 15px; }
    .task { min-height: 34px; border-radius: 10px; padding: 4px 9px; }
    .task.active { background: RAISED; border-bottom: 3px solid ACCENT; }
    .task.running { border-bottom: 3px solid DIM; }
    .shortcut { border: none; background: transparent; border-radius: 16px; padding: 9px; }
    .shortcut:hover { background: SURFACE; }
    .launcher-app { min-width: 72px; min-height: 75px; }
    .calculator-key { min-height: 23px; padding: 5px 10px; }
    .calculator-key label { font-size: 18px; }
    .calculator-display { font-size: 30px; min-height: 58px; }
    .accent { color: ACCENT; }
    notebook header { background: RAISED; border-bottom: 1px solid LINE; }
    notebook tab { padding: 7px 13px; }
    notebook tab:checked { background: SURFACE; }
    notebook tab:checked { box-shadow: inset 0 -3px ACCENT; }
    checkbutton check:checked { background: ACCENT; border-color: ACCENT; color: white; }
    scale highlight, switch:checked { background: ACCENT; }
    tooltip { background: SURFACE; color: TEXT; border-radius: 8px; padding: 4px; }
    '''
    values = {key.upper(): value for key, value in palette.items()}
    values['accent'.upper()] = accent_color(_state)
    for key, value in values.items():
        css = css.replace(key, value)
    display = Gdk.Display.get_default()
    if display:
        if _provider:
            Gtk.StyleContext.remove_provider_for_display(display, _provider)
        _provider = Gtk.CssProvider()
        _provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(display, _provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', _state['theme'] == 'dark')
    for callback in list(_callbacks):
        safe(callback)
    for window in _windows:
        window.queue_draw()


def install_css():
    global _watch_started
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    apply_theme()
    if not _watch_started:
        _watch_started = True
        monitor = Gio.File.new_for_path(str(CONFIG_DIR)).monitor_directory(Gio.FileMonitorFlags.NONE, None)
        def changed(_monitor, file, other, _event):
            if any(item and item.get_basename() == CONFIG_FILE.name for item in (file, other)):
                GLib.idle_add(lambda: (apply_theme(), False)[1])
        monitor.connect('changed', changed)
        globals()['_config_monitor'] = monitor


def on_theme(callback):
    _callbacks.append(callback)


def set_preferences(**changes):
    if _state.get('appearance_source') == 'app':
        changes = {key: value for key, value in changes.items() if key not in ('theme', 'accent', 'accent_color', 'background_color', 'appearance_source')}
    elif 'theme' in changes:
        changes.setdefault('background_color', None)
    if 'accent' in changes:
        changes.setdefault('accent_color', None)
    if not changes:
        return
    update_config(**changes)
    apply_theme()


def label(text='', css=None, expand=False):
    item = Gtk.Label(label=text, xalign=0)
    if css:
        item.add_css_class('campus-title' if css == 'title' else css)
    item.set_hexpand(expand)
    return item


def pad(widget, value=16):
    for side in ('top', 'bottom', 'start', 'end'):
        getattr(widget, 'set_margin_' + side)(value)
    return widget


def box(vertical=False, spacing=8):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL, spacing=spacing)


ICON_COLORS = dict(files='#e6ae55', folder='#e6ae55', editor='#66a6bc', browser='#6a94de', terminal='#566583', settings='#9d8cca', calc='#dd92a9', image='#75a98c', viewer='#75a98c', info='#7694bd')


def icon(name, size=20, tile=False):
    area = Gtk.DrawingArea()
    area.set_content_width(size)
    area.set_content_height(size)
    def draw(_area, cr, width, height):
        actual = min(width, height)
        if tile:
            cr.set_source_rgb(*rgb(ICON_COLORS.get(name, accent_color(_state))))
            _round_rect(cr, 0, 0, actual, actual, actual*.25)
            cr.fill()
            cr.set_source_rgba(1, 1, 1, .18)
            _round_rect(cr, 3, 3, actual-6, actual*.4, actual*.2)
            cr.fill()
            draw_icon(cr, name, actual*.19, actual*.19, actual*.62, (1, 1, 1), 1.6)
        else:
            draw_icon(cr, name, (width-actual)/2, (height-actual)/2, actual, color())
    area.set_draw_func(draw)
    return area


def button(text='', callback=None, glyph=None, css=None, tip=None):
    item = Gtk.Button()
    content = box(spacing=7)
    if glyph:
        content.append(icon(glyph))
    if text:
        content.append(label(text))
    item.set_child(content)
    if callback:
        item.connect('clicked', lambda *_: safe(callback))
    if css:
        for name in css.split():
            item.add_css_class(name)
    if tip:
        item.set_tooltip_text(tip)
    return item


def safe(callback):
    try:
        callback()
    except Exception as error:
        print(f'Application action: {error}', file=sys.stderr)


def launch(command, cwd=None):
    argv = list(command)
    own = ROOT / 'bin' / argv[0]
    if own.is_file():
        argv = [sys.executable, str(own), *argv[1:]]
    environment = dict(os.environ)
    environment.pop('LD_PRELOAD', None)
    return subprocess.Popen(argv, cwd=cwd, env=environment, start_new_session=True)


def open_path(path):
    path = Path(path)
    if path.is_dir():
        launch(['cibyp-files', str(path)])
    elif path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.svg'):
        launch(['cibyp-viewer', str(path)])
    elif path.suffix.lower() in ('.txt', '.md', '.py', '.js', '.json', '.html', '.css', '.sh', '.yaml', '.log', '.ini', '.conf', '.xml', '.csv'):
        launch(['cibyp-editor', str(path)])
    else:
        Gio.AppInfo.launch_default_for_uri(path.resolve().as_uri(), None)


def background(operation, complete):
    def run():
        try:
            result, error = operation(), None
        except Exception as caught:
            result, error = None, caught
        GLib.idle_add(lambda: (complete(result, error), False)[1])
    threading.Thread(target=run, daemon=True).start()


def dialog(parent, title, detail='', actions=None, entry=None):
    window = Gtk.Window(application=parent.get_application(), title=title, transient_for=parent, modal=True)
    window.add_css_class('campus')
    window.set_default_size(420, -1)
    window.set_resizable(False)
    content = pad(box(True, 14), 22)
    content.append(label(title, 'heading'))
    if detail:
        description = label(detail, 'dim')
        description.set_wrap(True)
        description.set_max_width_chars(55)
        content.append(description)
    field = Gtk.Entry(text=entry) if entry is not None else None
    if field:
        content.append(field)
    row = box()
    row.set_halign(Gtk.Align.END)
    def choose(callback):
        try:
            if callback:
                callback(field.get_text() if field else None)
            window.set_modal(False)
            window.destroy()
            parent.present()
        except Exception as error:
            notice = label(str(error), 'dim')
            notice.set_wrap(True)
            content.prepend(notice)
    choices = actions or [('知道了', None)]
    for index, (text, callback) in enumerate(choices):
        row.append(button(text, lambda cb=callback: choose(cb), css='primary' if index else None))
    content.append(row)
    window.set_child(content)
    window.present()
    if field:
        field.grab_focus()
        field.select_region(0, -1)
        field.connect('activate', lambda *_: choose(choices[-1][1]))
    shortcuts(window, {'escape': window.close})
    return window


def choose_file(parent, callback, save=False, name=None, folder=False):
    action = Gtk.FileChooserAction.SELECT_FOLDER if folder else Gtk.FileChooserAction.SAVE if save else Gtk.FileChooserAction.OPEN
    chooser = Gtk.FileChooserNative(title='保存文件' if save else '打开文件', transient_for=parent, action=action, accept_label='保存' if save else '打开', cancel_label='取消')
    if save and name:
        chooser.set_current_name(name)
    def response(_chooser, result):
        if result == Gtk.ResponseType.ACCEPT and chooser.get_file():
            safe(lambda: callback(chooser.get_file().get_path()))
        chooser.destroy()
    chooser.connect('response', response)
    chooser.show()
    parent._file_chooser = chooser


def dismiss_popovers(window):
    for menu in list(_popovers):
        if menu.get_root() == window:
            menu.popdown()
            menu.set_visible(False)
            if menu.get_parent():
                menu.unparent()
            if menu in _popovers:
                _popovers.remove(menu)


def popover(anchor, options, x=None, y=None):
    dismiss_popovers(anchor.get_root())
    menu = Gtk.Popover()
    _popovers.append(menu)
    menu.set_parent(anchor)
    menu.set_autohide(True)
    menu.set_has_arrow(False)
    if x is not None:
        rectangle = Gdk.Rectangle()
        rectangle.x, rectangle.y, rectangle.width, rectangle.height = int(x), int(y), 1, 1
        menu.set_pointing_to(rectangle)
    content = box(True, 2)
    for option in options:
        if option is None:
            content.append(Gtk.Separator())
            continue
        title, callback, glyph = option[:3]
        row = button(title, lambda cb=callback: (menu.popdown(), cb()), glyph, 'flat')
        if len(option) > 3:
            row.set_sensitive(bool(option[3]))
        content.append(row)
    menu.set_child(content)
    def closed(*_):
        if menu in _popovers:
            _popovers.remove(menu)
        if menu.get_parent():
            menu.unparent()
    menu.connect('closed', closed)
    menu.popup()
    return menu


def context_menu(widget, options):
    widget._campus_context_menu = True
    gesture = Gtk.GestureClick()
    gesture.set_button(3)
    def pressed(_gesture, _count, x, y):
        target = widget.pick(x, y, Gtk.PickFlags.DEFAULT)
        while target and target != widget:
            if getattr(target, '_campus_context_menu', False):
                return
            target = target.get_parent()
        popover(widget, options() if callable(options) else options, x, y)
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
    gesture.connect('pressed', pressed)
    widget.add_controller(gesture)


def shortcuts(widget, handlers):
    controller = Gtk.EventControllerKey()
    controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    def pressed(_controller, key, _code, state):
        prefix = ''
        for mask, token in ((Gdk.ModifierType.CONTROL_MASK, 'ctrl+'), (Gdk.ModifierType.ALT_MASK, 'alt+'), (Gdk.ModifierType.SHIFT_MASK, 'shift+')):
            if state & mask:
                prefix += token
        callback = handlers.get(prefix + (Gdk.keyval_name(key) or '').lower())
        if callback:
            try:
                return callback() is not False
            except Exception as error:
                print(f'Keyboard action: {error}', file=sys.stderr)
                return True
        return False
    controller.connect('key-pressed', pressed)
    widget.add_controller(controller)


def sway(command):
    return subprocess.run(['swaymsg', '-r', command], capture_output=True, timeout=2)


def shell_command(command):
    import socket
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(str(Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / 'cibyp-shell.sock'))
        client.sendall(command.encode())


def window_frame(window, title, glyph):
    window.add_css_class('campus')
    _windows.append(window)
    window.connect('destroy', lambda *_: _windows.remove(window) if window in _windows else None)
    header = Gtk.HeaderBar()
    header.set_show_title_buttons(False)
    heading = box(spacing=9)
    heading.append(icon(glyph, 26, True))
    heading.append(label(title))
    header.pack_start(heading)
    def minimize():
        shell_command(f'minimize-pid {os.getpid()}')
    def maximize():
        shell_command(f'maximize-pid {os.getpid()}')
    for text, callback, name in reversed((('−', minimize, '最小化'), ('□', maximize, '最大化 / 还原'), ('×', window.close, '关闭'))):
        header.pack_end(button(text, callback, css='flat close' if text == '×' else 'flat', tip=name))
    gesture = Gtk.GestureClick()
    gesture.set_button(1)
    gesture.connect('pressed', lambda _gesture, count, _x, _y: maximize() if count == 2 else None)
    header.add_controller(gesture)
    context_menu(header, [('最小化', minimize, 'back'), ('最大化 / 还原', maximize, 'grid'), None, ('关闭窗口', window.close, 'close')])
    window.set_titlebar(header)
    return header


def ensure_layer_shell_preload():
    libraries = glob.glob('/usr/lib/*/libgtk4-layer-shell.so.0')
    if libraries and libraries[0] not in os.environ.get('LD_PRELOAD', '') and os.environ.get('CIBYP_LAYER_READY') != '1':
        environment = dict(os.environ, LD_PRELOAD=libraries[0], CIBYP_LAYER_READY='1')
        os.execve(sys.executable, [sys.executable, *sys.argv], environment)


def acquire_single_instance(name):
    import fcntl
    stream = (Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / f'cibyp-{name}.lock').open('w')
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    globals()['_lock_' + name] = stream
    return True


def try_layer_shell(window, namespace=None, layer='top', anchors=('bottom', 'left', 'right'), exclusive=None):
    gi.require_version('Gtk4LayerShell', '1.0')
    from gi.repository import Gtk4LayerShell as Layer
    if not Layer.is_supported():
        raise RuntimeError('需要支持 layer-shell 的 Wayland 会话')
    Layer.init_for_window(window)
    Layer.set_namespace(window, namespace or 'cibyp-panel')
    Layer.set_keyboard_mode(window, Layer.KeyboardMode.ON_DEMAND)
    Layer.set_layer(window, {'background': Layer.Layer.BACKGROUND, 'bottom': Layer.Layer.BOTTOM, 'top': Layer.Layer.TOP, 'overlay': Layer.Layer.OVERLAY}[layer])
    for edge in anchors:
        Layer.set_anchor(window, getattr(Layer.Edge, edge.upper()), True)
    if exclusive is not None:
        Layer.set_exclusive_zone(window, exclusive)
    return True


def app_icon_name(value, name=''):
    value = (value + name).lower()
    for token, glyph in (('file', 'files'), ('editor', 'editor'), ('terminal', 'terminal'), ('foot', 'terminal'), ('chrom', 'browser'), ('firefox', 'browser'), ('browser', 'browser'), ('calc', 'calc'), ('setting', 'settings'), ('view', 'image'), ('about', 'info')):
        if token in value:
            return glyph
    return 'grid'


def panel_height():
    return 64


def run_application(kind, window_type):
    application = Gtk.Application(application_id=f'com.b5software.cibyp.{kind}', flags=Gio.ApplicationFlags.NON_UNIQUE)
    def activate(app):
        install_css()
        window_type(app).present()
    application.connect('activate', activate)
    return application.run([sys.argv[0]])
