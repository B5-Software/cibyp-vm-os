"""Image viewer with fit/zoom, rotation and directory navigation."""
from pathlib import Path
import sys
import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
import cibypui as ui
from campus_core import human_size


class ViewerWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='图片 · Campus')
        self.set_default_size(980, 680)
        ui.window_frame(self, '图片查看器', 'image')
        self.path, self.pixbuf, self.rotation, self.zoom, self.fit, self.timer = None, None, 0, 1., True, None
        content = ui.box(True, 0)
        toolbar = ui.box()
        toolbar.add_css_class('toolbar')
        for text, callback, glyph in [('打开', self.open, 'folder'), ('上一张', lambda: self.step(-1), 'back'), ('下一张', lambda: self.step(1), 'forward'), ('适应窗口', self.fit_image, 'grid'), ('100%', lambda: self.set_zoom(1), 'image'), ('−', lambda: self.set_zoom(self.zoom / 1.25), None), ('+', lambda: self.set_zoom(self.zoom * 1.25), None), ('旋转', self.rotate, 'refresh'), ('幻灯片', self.slideshow, 'play')]:
            toolbar.append(ui.button(text, callback, glyph))
        content.append(toolbar)
        self.picture = Gtk.Picture(can_shrink=True)
        self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.scroll.set_child(self.picture)
        content.append(self.scroll)
        self.status = ui.label('打开一张图片，或从文件管理器双击图片。', 'status')
        content.append(self.status)
        self.set_child(content)
        ui.context_menu(self.picture, [('打开图片', self.open, 'folder'), ('上一张', lambda: self.step(-1), 'back'), ('下一张', lambda: self.step(1), 'forward'), None, ('适应窗口', self.fit_image, 'grid'), ('实际大小', lambda: self.set_zoom(1), 'image'), ('顺时针旋转', self.rotate, 'refresh'), ('在文件夹中显示', self.reveal, 'files'), ('图片信息', self.properties, 'info')])
        ui.shortcuts(self, {'ctrl+o': self.open, 'left': lambda: self.step(-1), 'right': lambda: self.step(1), 'ctrl+0': self.fit_image, 'ctrl+1': lambda: self.set_zoom(1), 'r': self.rotate, 'space': self.slideshow, 'escape': self.stop_slideshow})
        self.connect('close-request', lambda *_: (self.stop_slideshow(), False)[1])
        if len(sys.argv) > 1:
            self.load(sys.argv[1])

    def open(self):
        ui.choose_file(self, self.load)

    def load(self, path):
        target = Path(path).absolute()
        def complete(pixbuf, error):
            if error:
                ui.dialog(self, '无法打开图片', str(error))
                return
            self.path, self.pixbuf, self.rotation = target, pixbuf, 0
            self.set_title(target.name + ' · 图片')
            self.fit_image()
        ui.background(lambda: GdkPixbuf.Pixbuf.new_from_file(str(target)), complete)

    def redraw(self):
        if not self.pixbuf:
            return
        pixbuf = self.pixbuf
        if self.rotation:
            pixbuf = pixbuf.rotate_simple({90: GdkPixbuf.PixbufRotation.CLOCKWISE, 180: GdkPixbuf.PixbufRotation.UPSIDEDOWN, 270: GdkPixbuf.PixbufRotation.COUNTERCLOCKWISE}[self.rotation])
        self.picture.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
        self.picture.set_size_request(-1 if self.fit else int(pixbuf.get_width()*self.zoom), -1 if self.fit else int(pixbuf.get_height()*self.zoom))
        self.picture.set_hexpand(self.fit)
        self.picture.set_vexpand(self.fit)
        self.status.set_text(f'{self.path.name}  |  {pixbuf.get_width()} × {pixbuf.get_height()}  |  {human_size(self.path.stat().st_size)}  |  {"适应窗口" if self.fit else f"{self.zoom:.0%}"}')

    def fit_image(self):
        self.fit, self.zoom = True, 1.
        self.redraw()

    def set_zoom(self, value):
        self.fit, self.zoom = False, max(.1, min(5., value))
        self.redraw()

    def rotate(self):
        self.rotation = (self.rotation + 90) % 360
        self.redraw()

    def step(self, direction):
        if not self.path:
            return
        images = sorted((p for p in self.path.parent.iterdir() if p.is_file() and p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.svg')), key=lambda p: p.name.casefold())
        if images and self.path in images:
            self.load(images[(images.index(self.path) + direction) % len(images)])

    def slideshow(self):
        if self.timer:
            self.stop_slideshow()
        elif self.path:
            self.timer = GLib.timeout_add_seconds(4, lambda: (self.step(1), True)[1])
            self.status.set_text('幻灯片播放中 · 空格暂停')

    def stop_slideshow(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None

    def reveal(self):
        if self.path:
            ui.launch(['cibyp-files', str(self.path.parent)])

    def properties(self):
        if self.path:
            ui.dialog(self, self.path.name, f'位置：{self.path}\n像素：{self.pixbuf.get_width()} × {self.pixbuf.get_height()}\n大小：{human_size(self.path.stat().st_size)}')
