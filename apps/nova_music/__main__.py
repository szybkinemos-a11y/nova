"""Nova Music – odtwarzacz muzyki: biblioteka z tagami, okładki, kolejka, losowo/powtarzanie."""
from __future__ import annotations

import os
import random
import sys
from pathlib import Path

# Qt ≥ 6.10 ulega awarii w backendzie PipeWire, gdy demon PipeWire nie działa
# (np. sesja bez dźwięku). Wtedy wybieramy backend PulseAudio/ALSA.
_rt = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
if "QT_AUDIO_BACKEND" not in os.environ and not os.path.exists(os.path.join(_rt, "pipewire-0")):
    os.environ["QT_AUDIO_BACKEND"] = "pulseaudio"

from PySide6.QtCore import QSortFilterProxyModel, Qt, QThread, QUrl, Signal, QObject
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut, QStandardItem, QStandardItemModel
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMainWindow,
                               QSlider, QTableView, QVBoxLayout, QWidget)

from novakit import app as novaapp
from novakit.config import Store, user_dir
from novakit.i18n import tr
from novakit.widgets import SearchField, card, flat_button, icon, notify
from nova_music.library import Track, cover_art, fmt_time, read_track, scan


class Scanner(QObject):
    done = Signal(list)

    def __init__(self, folders):
        super().__init__()
        self.folders = folders

    def run(self):
        self.done.emit(scan(self.folders))


class Music(QMainWindow):
    REPEAT = ["off", "all", "one"]

    def __init__(self, files: list[str] | None = None):
        super().__init__()
        self.setWindowTitle("Nova Music")
        self.resize(1080, 680)
        self.store = Store("music", {"folders": [str(user_dir("MUSIC", "Music"))], "volume": 70,
                                     "shuffle": False, "repeat": "all"})
        self.tracks: list[Track] = []
        self.current = -1

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(self.store.get("volume") / 100)
        self.player.positionChanged.connect(self._position)
        self.player.durationChanged.connect(lambda d: self.seek.setRange(0, d))
        self.player.mediaStatusChanged.connect(self._status)
        self.player.playbackStateChanged.connect(self._state)
        self.player.errorOccurred.connect(lambda _e, msg: self.now_title.setText(tr("Cannot play: {m}", m=msg)))

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 12)
        top = QHBoxLayout()
        self.search = SearchField(tr("Search title, artist, album…"))
        add = flat_button("folder-music", tr("Add music folder"), "folder-add")
        add.clicked.connect(self.add_folder)
        rescan = flat_button("view-refresh", tr("Rescan library"))
        rescan.clicked.connect(self.rescan)
        top.addWidget(self.search, 1)
        top.addWidget(add)
        top.addWidget(rescan)
        root.addLayout(top)

        self.model = QStandardItemModel(0, 4)
        self.model.setHorizontalHeaderLabels([tr("Title"), tr("Artist"), tr("Album"), tr("Time")])
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.doubleClicked.connect(lambda idx: self.play_index(self.proxy.mapToSource(idx).row()))
        self.empty = QLabel(tr("No music found. Put files in your Music folder or add a folder with the button above."))
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setObjectName("Subtitle")
        self.empty.setWordWrap(True)
        root.addWidget(self.table, 1)
        root.addWidget(self.empty, 1)

        # --- odtwarzacz
        bar = QHBoxLayout()
        self.cover = QLabel()
        self.cover.setFixedSize(64, 64)
        self.cover.setScaledContents(True)
        self.cover.setPixmap(icon("nova-music").pixmap(64, 64))
        info = QVBoxLayout()
        self.now_title = QLabel(tr("Nothing playing"))
        self.now_title.setStyleSheet("font-weight:600; font-size:12pt")
        self.now_artist = QLabel("")
        self.now_artist.setObjectName("Subtitle")
        info.addWidget(self.now_title)
        info.addWidget(self.now_artist)
        self.shuffle = flat_button("media-playlist-shuffle", tr("Shuffle"), checkable=True)
        self.shuffle.setChecked(self.store.get("shuffle"))
        self.shuffle.toggled.connect(lambda on: self.store.set("shuffle", on))
        prev = flat_button("media-skip-backward", tr("Previous"))
        self.play_btn = flat_button("media-playback-start", tr("Play / Pause") + " (Space)")
        nxt = flat_button("media-skip-forward", tr("Next"))
        self.repeat = flat_button("media-playlist-repeat", "", checkable=True)
        self._repeat_mode = self.store.get("repeat")
        self._update_repeat()
        self.repeat.clicked.connect(self._cycle_repeat)
        prev.clicked.connect(self.prev)
        nxt.clicked.connect(self.next)
        self.play_btn.clicked.connect(self.toggle)
        self.play_btn.setIconSize(self.play_btn.iconSize() * 1.5)
        self.pos_lbl = QLabel("0:00")
        self.seek = QSlider(Qt.Horizontal)
        self.seek.sliderMoved.connect(self.player.setPosition)
        self.dur_lbl = QLabel("0:00")
        vol_icon = QLabel()
        vol_icon.setPixmap(icon("audio-volume-high").pixmap(18, 18))
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(self.store.get("volume"))
        self.vol.setFixedWidth(110)
        self.vol.valueChanged.connect(self._volume)
        seek_row = QHBoxLayout()
        for w in (self.shuffle, prev, self.play_btn, nxt, self.repeat):
            seek_row.addWidget(w)
        seek_row.addWidget(self.pos_lbl)
        seek_row.addWidget(self.seek, 1)
        seek_row.addWidget(self.dur_lbl)
        bar.addWidget(self.cover)
        bar.addLayout(info, 1)
        bar.addLayout(seek_row, 3)
        bar.addWidget(vol_icon)
        bar.addWidget(self.vol)
        root.addWidget(card(bar))
        self.setCentralWidget(central)

        QShortcut(QKeySequence(Qt.Key_Space), self.table, activated=self.toggle)
        QShortcut(QKeySequence("Ctrl+Right"), self, activated=self.next)
        QShortcut(QKeySequence("Ctrl+Left"), self, activated=self.prev)
        QShortcut(QKeySequence.Find, self, activated=self.search.setFocus)

        if files:
            self.set_tracks([read_track(Path(f)) for f in files if Path(f).is_file()])
            self.play_index(0)
        else:
            self.rescan()

    # ------------------------------------------------------------ biblioteka
    def rescan(self) -> None:
        folders = [Path(f) for f in self.store.get("folders") if Path(f).is_dir()]
        self.empty.setText(tr("Scanning library…"))
        self.thread = QThread(self)
        self.worker = Scanner(folders)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.done.connect(self.set_tracks)
        self.worker.done.connect(self.thread.quit)
        self.thread.start()

    def set_tracks(self, tracks: list[Track]) -> None:
        self.tracks = tracks
        self.model.setRowCount(0)
        for t in tracks:
            items = [QStandardItem(t.display_title), QStandardItem(t.artist), QStandardItem(t.album),
                     QStandardItem(fmt_time(t.duration) if t.duration else "")]
            items[3].setData(t.duration, Qt.UserRole)
            self.model.appendRow(items)
        self.table.setVisible(bool(tracks))
        self.empty.setVisible(not tracks)
        self.empty.setText(tr("No music found. Put files in your Music folder or add a folder with the button above."))
        self.setWindowTitle(f"Nova Music — {tr('{n} tracks', n=len(tracks))}")

    def add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Add music folder"), str(Path.home()))
        if d:
            folders = self.store.get("folders")
            if d not in folders:
                folders.append(d)
                self.store.set("folders", folders)
            self.rescan()

    # ------------------------------------------------------------ odtwarzanie
    def play_index(self, row: int) -> None:
        if not (0 <= row < len(self.tracks)):
            return
        self.current = row
        t = self.tracks[row]
        self.player.setSource(QUrl.fromLocalFile(str(t.path)))
        self.player.play()
        self.now_title.setText(t.display_title)
        self.now_artist.setText(" — ".join(x for x in (t.artist, t.album) if x))
        data = cover_art(t.path)
        pm = QPixmap()
        if data and pm.loadFromData(data):
            self.cover.setPixmap(pm)
        else:
            self.cover.setPixmap(icon("nova-music").pixmap(64, 64))
        self.table.selectRow(self.proxy.mapFromSource(self.model.index(row, 0)).row())
        if not self.isActiveWindow():
            notify(t.display_title, t.artist, "nova-music", "Nova Music")

    def toggle(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        elif self.current < 0:
            sel = self.table.selectionModel().selectedRows()
            self.play_index(self.proxy.mapToSource(sel[0]).row() if sel else 0)
        else:
            self.player.play()

    def _order(self) -> list[int]:
        return [self.proxy.mapToSource(self.proxy.index(r, 0)).row() for r in range(self.proxy.rowCount())]

    def next(self, auto: bool = False) -> None:
        order = self._order()
        if not order:
            return
        if self.shuffle.isChecked() and len(order) > 1:
            self.play_index(random.choice([r for r in order if r != self.current]))
            return
        pos = order.index(self.current) if self.current in order else -1
        if pos + 1 < len(order):
            self.play_index(order[pos + 1])
        elif not auto or self._repeat_mode == "all":
            self.play_index(order[0])

    def prev(self) -> None:
        if self.player.position() > 3000:
            self.player.setPosition(0)
            return
        order = self._order()
        if order and self.current in order:
            self.play_index(order[(order.index(self.current) - 1) % len(order)])

    def _status(self, status) -> None:
        if status == QMediaPlayer.EndOfMedia:
            if self._repeat_mode == "one":
                self.player.setPosition(0)
                self.player.play()
            else:
                self.next(auto=True)

    def _state(self, state) -> None:
        playing = state == QMediaPlayer.PlayingState
        self.play_btn.setIcon(icon("media-playback-pause" if playing else "media-playback-start"))

    def _position(self, ms: int) -> None:
        if not self.seek.isSliderDown():
            self.seek.setValue(ms)
        self.pos_lbl.setText(fmt_time(ms / 1000))
        self.dur_lbl.setText(fmt_time(self.player.duration() / 1000))

    def _volume(self, v: int) -> None:
        self.audio.setVolume(v / 100)
        self.store.set("volume", v)

    def _cycle_repeat(self) -> None:
        i = (self.REPEAT.index(self._repeat_mode) + 1) % 3
        self._repeat_mode = self.REPEAT[i]
        self.store.set("repeat", self._repeat_mode)
        self._update_repeat()

    def _update_repeat(self) -> None:
        names = {"off": tr("Repeat: off"), "all": tr("Repeat: all"), "one": tr("Repeat: one")}
        self.repeat.setChecked(self._repeat_mode != "off")
        self.repeat.setIcon(icon("media-playlist-repeat-song" if self._repeat_mode == "one" else "media-playlist-repeat"))
        self.repeat.setToolTip(names[self._repeat_mode])


def main() -> int:
    files = [a for a in sys.argv[1:] if not a.startswith("-")]
    files = [QUrl(f).toLocalFile() if f.startswith("file:") else f for f in files]
    return novaapp.run(lambda: Music(files), "nova-music", "Nova Music")


if __name__ == "__main__":
    sys.exit(main())
