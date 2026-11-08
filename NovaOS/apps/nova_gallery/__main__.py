"""Nova Gallery – przeglądarka zdjęć: miniatury (asynchronicznie), podgląd z zoomem,
obracanie, pokaz slajdów, pełny ekran, ustawianie tapety, usuwanie do kosza."""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal, QUrl
from PySide6.QtGui import QIcon, QImage, QImageReader, QKeySequence, QPixmap, QShortcut, QTransform, QPainter
from PySide6.QtWidgets import (QFileDialog, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QHBoxLayout,
                               QLabel, QListWidget, QListWidgetItem, QMainWindow, QStackedWidget, QVBoxLayout,
                               QWidget)

from novakit import app as novaapp
from novakit.config import Store, user_dir
from novakit.i18n import tr
from novakit.widgets import Toast, confirm, flat_button

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".svg", ".avif", ".heic", ".jxl"}
THUMB = 180


class ThumbSignals(QObject):
    ready = Signal(str, QImage)


class ThumbJob(QRunnable):
    def __init__(self, path: str, signals: ThumbSignals):
        super().__init__()
        self.path, self.signals = path, signals

    def run(self) -> None:
        reader = QImageReader(self.path)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid():
            reader.setScaledSize(size.scaled(QSize(THUMB * 2, THUMB * 2), Qt.KeepAspectRatio))
        img = reader.read()
        if not img.isNull():
            self.signals.ready.emit(self.path, img)


def list_images(folder: Path, recursive: bool = False) -> list[Path]:
    it = folder.rglob("*") if recursive else folder.glob("*")
    files = [p for p in it if p.is_file() and p.suffix.lower() in IMAGE_EXT]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


class Viewer(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.item = QGraphicsPixmapItem()
        self.item.setTransformationMode(Qt.SmoothTransformation)
        self.scene().addItem(self.item)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setBackgroundBrush(Qt.black)
        self.fit = True
        self.rotation = 0

    def show_image(self, path: Path) -> bool:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        img = reader.read()
        if img.isNull():
            return False
        self.rotation = 0
        self.item.setPixmap(QPixmap.fromImage(img))
        self.item.setTransform(QTransform())
        self.scene().setSceneRect(self.item.boundingRect())
        self.fit_view()
        return True

    def fit_view(self) -> None:
        self.fit = True
        self.resetTransform()
        r = self.item.sceneBoundingRect()
        if r.width() > self.viewport().width() or r.height() > self.viewport().height():
            self.fitInView(r, Qt.KeepAspectRatio)

    def zoom(self, factor: float) -> None:
        self.fit = False
        self.scale(factor, factor)

    def rotate_image(self, deg: int) -> None:
        self.rotation = (self.rotation + deg) % 360
        r = self.item.boundingRect()
        t = QTransform().translate(r.width() / 2, r.height() / 2).rotate(self.rotation).translate(-r.width() / 2, -r.height() / 2)
        self.item.setTransform(t)
        self.scene().setSceneRect(self.item.sceneBoundingRect())
        self.fit_view()

    def wheelEvent(self, ev) -> None:
        self.zoom(1.15 if ev.angleDelta().y() > 0 else 1 / 1.15)

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        if self.fit:
            self.fit_view()


class Gallery(QMainWindow):
    def __init__(self, start: str | None = None):
        super().__init__()
        self.setWindowTitle("Nova Gallery")
        self.resize(1100, 720)
        self.store = Store("gallery", {"folder": str(user_dir("PICTURES", "Pictures")), "recursive": False})
        self.images: list[Path] = []
        self.index = -1
        self.pool = QThreadPool.globalInstance()
        self.signals = ThumbSignals()
        self.signals.ready.connect(self._thumb_ready)
        self.items: dict[str, QListWidgetItem] = {}

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(10, 8, 10, 8)
        self.back_btn = flat_button("go-previous", tr("Back to grid") + " (Esc)")
        self.back_btn.clicked.connect(self.show_grid)
        open_btn = flat_button("folder-open", tr("Open folder"))
        open_btn.clicked.connect(self.choose_folder)
        self.title = QLabel()
        self.title.setObjectName("Section")
        self.prev_btn = flat_button("go-previous-view", tr("Previous") + " (←)", "go-previous")
        self.next_btn = flat_button("go-next-view", tr("Next") + " (→)", "go-next")
        zin = flat_button("zoom-in", tr("Zoom in"))
        zout = flat_button("zoom-out", tr("Zoom out"))
        zfit = flat_button("zoom-fit-best", tr("Fit to window"))
        rotl = flat_button("object-rotate-left", tr("Rotate left"))
        rotr = flat_button("object-rotate-right", tr("Rotate right"))
        self.slide_btn = flat_button("media-playback-start", tr("Slideshow"), checkable=True)
        wall = flat_button("preferences-desktop-wallpaper", tr("Set as wallpaper"))
        delete = flat_button("edit-delete", tr("Move to trash") + " (Del)")
        full = flat_button("view-fullscreen", tr("Fullscreen") + " (F11)")
        self.prev_btn.clicked.connect(lambda: self.step(-1))
        self.next_btn.clicked.connect(lambda: self.step(1))
        zin.clicked.connect(lambda: self.viewer.zoom(1.25))
        zout.clicked.connect(lambda: self.viewer.zoom(0.8))
        zfit.clicked.connect(lambda: self.viewer.fit_view())
        rotl.clicked.connect(lambda: self.viewer.rotate_image(-90))
        rotr.clicked.connect(lambda: self.viewer.rotate_image(90))
        self.slide_btn.toggled.connect(self._slideshow)
        wall.clicked.connect(self.set_wallpaper)
        delete.clicked.connect(self.delete)
        full.clicked.connect(self.toggle_full)
        self.view_tools = [self.back_btn, self.prev_btn, self.next_btn, zin, zout, zfit, rotl, rotr,
                           self.slide_btn, wall, delete, full]
        bar.addWidget(self.back_btn)
        bar.addWidget(open_btn)
        bar.addWidget(self.title, 1)
        for w in self.view_tools[1:]:
            bar.addWidget(w)
        self.toolbar = QWidget()
        self.toolbar.setLayout(bar)
        root.addWidget(self.toolbar)

        self.stack = QStackedWidget()
        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.IconMode)
        self.grid.setIconSize(QSize(THUMB, THUMB))
        self.grid.setGridSize(QSize(THUMB + 20, THUMB + 40))
        self.grid.setResizeMode(QListWidget.Adjust)
        self.grid.setMovement(QListWidget.Static)
        self.grid.setUniformItemSizes(True)
        self.grid.setSpacing(6)
        self.grid.itemActivated.connect(lambda it: self.open_image(self.grid.row(it)))
        self.empty = QLabel(tr("No images in this folder."))
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setObjectName("Subtitle")
        self.viewer = Viewer()
        self.stack.addWidget(self.grid)
        self.stack.addWidget(self.viewer)
        self.stack.addWidget(self.empty)
        root.addWidget(self.stack, 1)
        self.info = QLabel()
        self.info.setObjectName("Subtitle")
        self.info.setContentsMargins(12, 4, 12, 6)
        root.addWidget(self.info)
        self.setCentralWidget(central)
        self.toast = Toast(self)
        self.slide_timer = QTimer(self, interval=4000, timeout=lambda: self.step(1))

        for seq, fn in [("Left", lambda: self.step(-1)), ("Right", lambda: self.step(1)),
                        ("Escape", self._escape), ("F11", self.toggle_full), ("Delete", self.delete),
                        ("Ctrl+O", self.choose_folder), ("+", lambda: self.viewer.zoom(1.25)),
                        ("-", lambda: self.viewer.zoom(0.8)), ("0", self.viewer.fit_view),
                        ("R", lambda: self.viewer.rotate_image(90))]:
            QShortcut(QKeySequence(seq), self, activated=fn)

        start_path = Path(start) if start else None
        if start_path and start_path.is_file():
            self.load_folder(start_path.parent, select=start_path)
        else:
            self.load_folder(start_path if start_path and start_path.is_dir() else Path(self.store.get("folder")))

    # ------------------------------------------------------------ siatka
    def load_folder(self, folder: Path, select: Path | None = None) -> None:
        folder.mkdir(parents=True, exist_ok=True) if folder == Path(self.store.get("folder")) else None
        self.folder = folder
        self.images = list_images(folder, self.store.get("recursive")) if folder.is_dir() else []
        self.grid.clear()
        self.items.clear()
        placeholder = QIcon.fromTheme("image-x-generic")
        for p in self.images:
            it = QListWidgetItem(placeholder, p.name)
            it.setToolTip(str(p))
            self.grid.addItem(it)
            self.items[str(p)] = it
            self.pool.start(ThumbJob(str(p), self.signals))
        self.title.setText(f"{folder.name or folder}  ·  {tr('{n} images', n=len(self.images))}")
        if select and select in self.images:
            self.open_image(self.images.index(select))
        else:
            self.show_grid()

    def _thumb_ready(self, path: str, img: QImage) -> None:
        it = self.items.get(path)
        if it is not None:
            it.setIcon(QIcon(QPixmap.fromImage(img)))

    def choose_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Open folder"), str(self.folder))
        if d:
            self.store.set("folder", d)
            self.load_folder(Path(d))

    def show_grid(self) -> None:
        self.slide_btn.setChecked(False)
        self.stack.setCurrentWidget(self.grid if self.images else self.empty)
        for w in self.view_tools:
            w.setVisible(False)
        self.info.setText(str(self.folder))

    # ------------------------------------------------------------ podgląd
    def open_image(self, i: int) -> None:
        if not (0 <= i < len(self.images)):
            return
        self.index = i
        p = self.images[i]
        if not self.viewer.show_image(p):
            self.toast.show_message(tr("Cannot open image"))
            return
        self.stack.setCurrentWidget(self.viewer)
        for w in self.view_tools:
            w.setVisible(True)
        self.grid.setCurrentRow(i)
        pm = self.viewer.item.pixmap()
        st = p.stat()
        self.info.setText(f"{p.name}  ·  {pm.width()}×{pm.height()}  ·  {st.st_size / 1048576:.2f} MB  ·  "
                          f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(st.st_mtime))}  ·  {i + 1}/{len(self.images)}")
        self.setWindowTitle(f"{p.name} — Nova Gallery")

    def step(self, d: int) -> None:
        if self.stack.currentWidget() is self.viewer and self.images:
            self.open_image((self.index + d) % len(self.images))

    def _escape(self) -> None:
        if self.isFullScreen():
            self.toggle_full()
        else:
            self.show_grid()

    def toggle_full(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self.toolbar.show()
            self.info.show()
        else:
            self.showFullScreen()
            self.toolbar.hide()
            self.info.hide()

    def _slideshow(self, on: bool) -> None:
        self.slide_timer.start() if on else self.slide_timer.stop()

    def set_wallpaper(self) -> None:
        if not (0 <= self.index < len(self.images)):
            return
        p = str(self.images[self.index])
        if shutil.which("plasma-apply-wallpaperimage"):
            subprocess.run(["plasma-apply-wallpaperimage", p], capture_output=True)
            self.toast.show_message(tr("Wallpaper changed"))
        else:
            self.toast.show_message(tr("Wallpaper can only be set in a KDE Plasma session"))

    def delete(self) -> None:
        if self.stack.currentWidget() is not self.viewer or not (0 <= self.index < len(self.images)):
            return
        p = self.images[self.index]
        if not confirm(self, tr("Move to trash"), tr("Move “{n}” to trash?", n=p.name), yes=tr("Move to trash")):
            return
        from PySide6.QtCore import QFile
        if QFile.moveToTrash(str(p)):
            del self.images[self.index]
            self.grid.takeItem(self.index)
            self.items.pop(str(p), None)
            if self.images:
                self.open_image(min(self.index, len(self.images) - 1))
            else:
                self.show_grid()
            self.toast.show_message(tr("Moved to trash"))


def main() -> int:
    start = next((a for a in sys.argv[1:] if not a.startswith("-")), None)
    if start and start.startswith("file:"):
        start = QUrl(start).toLocalFile()
    return novaapp.run(lambda: Gallery(start), "nova-gallery", "Nova Gallery")


if __name__ == "__main__":
    sys.exit(main())
