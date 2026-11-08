"""Nova Monitor – monitor zasobów: CPU, pamięć, dyski, sieć, procesy, informacje o systemie."""
from __future__ import annotations

import os
import platform
import signal
import sys
import time
from collections import deque

import psutil
from PySide6.QtCore import QRectF, QSortFilterProxyModel, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QStandardItem, QStandardItemModel, QLinearGradient
from PySide6.QtWidgets import (QAbstractItemView, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMainWindow,
                               QMenu, QProgressBar, QPushButton, QScrollArea, QTableView, QTabWidget,
                               QVBoxLayout, QWidget)

from novakit import app as novaapp
from novakit.i18n import tr
from novakit.widgets import SearchField, card, confirm, section, title

HISTORY = 60


def human(n: float, suffix: str = "B") -> str:
    for unit in ("", "K", "M", "G", "T"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}{suffix}" if unit else f"{n:.0f} {suffix}"
        n /= 1024
    return f"{n:.1f} P{suffix}"


class Graph(QWidget):
    """Wykres liniowy historii (0..100 albo autoskalowanie)."""

    def __init__(self, color: str, series: int = 1, autoscale: bool = False, colors: list[str] | None = None):
        super().__init__()
        self.colors = [QColor(c) for c in (colors or [color] * series)]
        self.data = [deque([0.0] * HISTORY, maxlen=HISTORY) for _ in range(series)]
        self.autoscale = autoscale
        self.setMinimumHeight(110)

    def push(self, *values: float) -> None:
        for d, v in zip(self.data, values):
            d.append(v)
        self.update()

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        fg = self.palette().windowText().color()
        grid = QColor(fg)
        grid.setAlphaF(0.08)
        p.setPen(QPen(grid, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 10, 10)
        for i in range(1, 4):
            y = r.top() + r.height() * i / 4
            p.drawLine(int(r.left()), int(y), int(r.right()), int(y))
        peak = max((max(d) for d in self.data), default=1) if self.autoscale else 100
        peak = peak or 1
        step = r.width() / (HISTORY - 1)
        for d, color in zip(self.data, self.colors):
            path = QPainterPath()
            for i, v in enumerate(d):
                x = r.left() + i * step
                y = r.bottom() - (v / peak) * (r.height() - 6)
                path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
            fill = QPainterPath(path)
            fill.lineTo(r.right(), r.bottom())
            fill.lineTo(r.left(), r.bottom())
            grad = QLinearGradient(0, r.top(), 0, r.bottom())
            c1 = QColor(color)
            c1.setAlphaF(0.35)
            c2 = QColor(color)
            c2.setAlphaF(0.02)
            grad.setColorAt(0, c1)
            grad.setColorAt(1, c2)
            p.fillPath(fill, grad)
            p.setPen(QPen(color, 2))
            p.drawPath(path)


class Overview(QWidget):
    def __init__(self):
        super().__init__()
        lay = QGridLayout(self)
        lay.setSpacing(14)
        self.cpu_graph = Graph("#7B61FF")
        self.mem_graph = Graph("#22D3EE", series=2, colors=["#22D3EE", "#A855F7"])
        self.net_graph = Graph("#34D399", series=2, autoscale=True, colors=["#34D399", "#F59E0B"])
        self.disk_graph = Graph("#3B82F6", series=2, autoscale=True, colors=["#3B82F6", "#EC4899"])
        self.cpu_lbl, self.mem_lbl, self.net_lbl, self.disk_lbl = (QLabel() for _ in range(4))
        for i, (name, graph, lbl) in enumerate([
            (tr("Processor"), self.cpu_graph, self.cpu_lbl), (tr("Memory"), self.mem_graph, self.mem_lbl),
            (tr("Network"), self.net_graph, self.net_lbl), (tr("Disk activity"), self.disk_graph, self.disk_lbl)]):
            v = QVBoxLayout()
            v.addWidget(section(name))
            v.addWidget(lbl)
            v.addWidget(graph, 1)
            lay.addWidget(card(v), i // 2, i % 2)
        # rdzenie
        self.cores = []
        cv = QVBoxLayout()
        cv.addWidget(section(tr("CPU cores")))
        grid = QGridLayout()
        for i in range(psutil.cpu_count() or 1):
            bar = QProgressBar()
            bar.setTextVisible(False)
            lbl = QLabel(f"#{i}")
            grid.addWidget(lbl, i // 4, (i % 4) * 2)
            grid.addWidget(bar, i // 4, (i % 4) * 2 + 1)
            self.cores.append(bar)
        cv.addLayout(grid)
        lay.addWidget(card(cv), 2, 0, 1, 2)
        self.prev_net = psutil.net_io_counters()
        self.prev_disk = psutil.disk_io_counters()
        self.prev_t = time.monotonic()

    def tick(self) -> None:
        now = time.monotonic()
        dt = max(now - self.prev_t, 0.1)
        self.prev_t = now
        total = psutil.cpu_percent()
        per = psutil.cpu_percent(percpu=True)
        freq = psutil.cpu_freq()
        self.cpu_graph.push(total)
        self.cpu_lbl.setText(f"{total:.0f}%  ·  {freq.current / 1000:.2f} GHz" if freq else f"{total:.0f}%")
        for bar, v in zip(self.cores, per):
            bar.setValue(int(v))
        vm, sw = psutil.virtual_memory(), psutil.swap_memory()
        self.mem_graph.push(vm.percent, sw.percent)
        self.mem_lbl.setText(tr("RAM {u} / {t} ({p:.0f}%)  ·  Swap {s:.0f}%",
                                u=human(vm.used), t=human(vm.total), p=vm.percent, s=sw.percent))
        net = psutil.net_io_counters()
        rx, tx = (net.bytes_recv - self.prev_net.bytes_recv) / dt, (net.bytes_sent - self.prev_net.bytes_sent) / dt
        self.prev_net = net
        self.net_graph.push(rx, tx)
        self.net_lbl.setText(f"↓ {human(rx)}/s   ↑ {human(tx)}/s")
        disk = psutil.disk_io_counters()
        if disk and self.prev_disk:
            rd, wr = (disk.read_bytes - self.prev_disk.read_bytes) / dt, (disk.write_bytes - self.prev_disk.write_bytes) / dt
            self.prev_disk = disk
            self.disk_graph.push(rd, wr)
            self.disk_lbl.setText(tr("Read {r}/s   Write {w}/s", r=human(rd), w=human(wr)))


class Processes(QWidget):
    COLS = ["PID", "Name", "User", "CPU %", "Memory", "Threads", "State"]

    def __init__(self, parent_win):
        super().__init__()
        self.win = parent_win
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = SearchField(tr("Filter processes…"))
        self.end_btn = QPushButton(tr("End process"))
        self.end_btn.setObjectName("Danger")
        self.end_btn.clicked.connect(lambda: self.signal(signal.SIGTERM))
        top.addWidget(self.search, 1)
        top.addWidget(self.end_btn)
        lay.addLayout(top)
        self.model = QStandardItemModel(0, len(self.COLS))
        self.model.setHorizontalHeaderLabels([tr(c) for c in self.COLS])
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(1)
        self.proxy.setSortRole(Qt.UserRole)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)
        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(3, Qt.DescendingOrder)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.verticalHeader().hide()
        self.view.setShowGrid(False)
        self.view.setAlternatingRowColors(True)
        self.view.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.view)
        self.me = os.getuid()

    def _item(self, text, sort):
        it = QStandardItem(str(text))
        it.setData(sort, Qt.UserRole)
        return it

    def refresh(self) -> None:
        sel = self.selected_pid()
        rows = []
        for p in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_info", "num_threads", "status"]):
            i = p.info
            mem = i["memory_info"].rss if i["memory_info"] else 0
            rows.append([self._item(i["pid"], i["pid"]), self._item(i["name"] or "?", (i["name"] or "").lower()),
                         self._item(i["username"] or "?", i["username"] or ""),
                         self._item(f"{(i['cpu_percent'] or 0):.1f}", i["cpu_percent"] or 0.0),
                         self._item(human(mem), mem), self._item(i["num_threads"] or 0, i["num_threads"] or 0),
                         self._item(i["status"], i["status"])])
        self.view.setUpdatesEnabled(False)
        self.model.setRowCount(0)
        for r in rows:
            self.model.appendRow(r)
        self.proxy.sort(self.proxy.sortColumn(), self.proxy.sortOrder())
        self.view.setUpdatesEnabled(True)
        if sel:
            for row in range(self.proxy.rowCount()):
                if self.proxy.index(row, 0).data(Qt.UserRole) == sel:
                    self.view.selectRow(row)
                    break

    def selected_pid(self) -> int | None:
        idx = self.view.selectionModel().selectedRows() if self.view.selectionModel() else []
        return idx[0].data(Qt.UserRole) if idx else None

    def _menu(self, pos) -> None:
        m = QMenu(self)
        m.addAction(tr("End process"), lambda: self.signal(signal.SIGTERM))
        m.addAction(tr("Kill process"), lambda: self.signal(signal.SIGKILL))
        m.addAction(tr("Pause"), lambda: self.signal(signal.SIGSTOP))
        m.addAction(tr("Resume"), lambda: self.signal(signal.SIGCONT))
        m.exec(self.view.viewport().mapToGlobal(pos))

    def signal(self, sig) -> None:
        pid = self.selected_pid()
        if not pid:
            return
        try:
            proc = psutil.Process(pid)
            name = proc.name()
        except psutil.Error:
            return
        if sig in (signal.SIGTERM, signal.SIGKILL) and not confirm(
                self, tr("End process"), tr("End process “{n}” (PID {p})? Unsaved data may be lost.", n=name, p=pid),
                danger=True, yes=tr("End process")):
            return
        try:
            proc.send_signal(sig)
        except psutil.AccessDenied:
            from novakit.proc import privileged, run
            run(privileged(["kill", f"-{int(sig)}", str(pid)]), timeout=60)
        except psutil.Error:
            pass
        self.refresh()


class SystemInfo(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        w = QWidget()
        lay = QVBoxLayout(w)
        osr = {}
        try:
            for line in open("/etc/os-release", encoding="utf-8"):
                if "=" in line:
                    k, v = line.rstrip().split("=", 1)
                    osr[k] = v.strip('"')
        except OSError:
            pass
        cpu = platform.processor() or "?"
        try:
            for line in open("/proc/cpuinfo", encoding="utf-8"):
                if line.startswith("model name"):
                    cpu = line.split(":", 1)[1].strip()
                    break
        except OSError:
            pass
        boot = time.strftime("%Y-%m-%d %H:%M", time.localtime(psutil.boot_time()))
        info = [(tr("System"), osr.get("PRETTY_NAME", platform.system())),
                (tr("Kernel"), platform.release()), (tr("Architecture"), platform.machine()),
                (tr("Processor"), f"{cpu} ({psutil.cpu_count(False)}/{psutil.cpu_count()})"),
                (tr("Memory"), human(psutil.virtual_memory().total)),
                (tr("Hostname"), platform.node()), (tr("Booted"), boot),
                (tr("Firmware"), "UEFI" if os.path.isdir("/sys/firmware/efi") else "BIOS (legacy)")]
        g = QGridLayout()
        for r, (k, v) in enumerate(info):
            kl = QLabel(k)
            kl.setObjectName("Subtitle")
            vl = QLabel(v)
            vl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            g.addWidget(kl, r, 0)
            g.addWidget(vl, r, 1)
        lay.addWidget(card(g))
        lay.addWidget(section(tr("Disks")))
        for part in psutil.disk_partitions():
            if part.fstype in ("squashfs", "tmpfs", "overlay") or part.mountpoint.startswith("/snap"):
                continue
            try:
                u = psutil.disk_usage(part.mountpoint)
            except OSError:
                continue
            v = QVBoxLayout()
            v.addWidget(QLabel(f"<b>{part.mountpoint}</b>  ({part.device}, {part.fstype})"))
            bar = QProgressBar()
            bar.setValue(int(u.percent))
            v.addWidget(bar)
            v.addWidget(QLabel(tr("{u} used of {t} · {f} free", u=human(u.used), t=human(u.total), f=human(u.free))))
            lay.addWidget(card(v))
        lay.addStretch(1)
        self.setWidget(w)


class Monitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nova Monitor")
        self.resize(1000, 700)
        psutil.cpu_percent(percpu=True)
        for p in psutil.process_iter(["cpu_percent"]):
            pass
        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(18, 14, 18, 14)
        v.addWidget(title("Nova Monitor", tr("Live system resource usage")))
        self.tabs = QTabWidget()
        self.overview = Overview()
        self.procs = Processes(self)
        self.tabs.addTab(self.overview, tr("Overview"))
        self.tabs.addTab(self.procs, tr("Processes"))
        self.tabs.addTab(SystemInfo(), tr("System"))
        v.addWidget(self.tabs)
        self.setCentralWidget(central)
        self.timer = QTimer(self, interval=1000, timeout=self.tick)
        self.timer.start()
        self.n = 0
        self.tick()

    def tick(self) -> None:
        self.overview.tick()
        if self.tabs.currentWidget() is self.procs and self.n % 2 == 0:
            self.procs.refresh()
        self.n += 1


def main() -> int:
    return novaapp.run(Monitor, "nova-monitor", "Nova Monitor")


if __name__ == "__main__":
    sys.exit(main())
