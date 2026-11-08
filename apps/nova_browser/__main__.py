"""Nova Browser – przeglądarka (Chromium/QtWebEngine): karty, zakładki, historia, pobieranie,
tryb prywatny, wyszukiwanie na stronie, zoom, pytania o uprawnienia."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QSize, QStringListModel, Qt, QUrl
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (QApplication, QCompleter, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu,
                               QMessageBox, QProgressBar, QTabWidget, QToolButton, QVBoxLayout, QWidget,
                               QWidgetAction)

from novakit import app as novaapp
from novakit import theme
from novakit.config import Store, user_dir
from novakit.i18n import tr
from novakit.widgets import Toast, flat_button, icon, notify
from nova_browser import newtab
from nova_browser.data import SEARCH_ENGINES, Bookmarks, History, to_url

HOME = "nova:newtab"


class Page(QWebEnginePage):
    def __init__(self, profile, window):
        super().__init__(profile, window)
        self.window = window
        if hasattr(self, "permissionRequested"):          # Qt ≥ 6.8
            self.permissionRequested.connect(self._permission)
        else:                                             # starsze Qt
            self.featurePermissionRequested.connect(self._feature)

    def createWindow(self, _type):
        view = self.window.new_tab(background=_type == QWebEnginePage.WebBrowserBackgroundTab)
        return view.page()

    def _ask(self, origin: QUrl, what: str) -> bool:
        return QMessageBox.question(self.window, tr("Permission request"),
                                    tr("{site} wants to use: {what}. Allow?", site=origin.host(), what=what)) \
            == QMessageBox.Yes

    def _permission(self, perm) -> None:
        names = {"MediaAudioCapture": tr("microphone"), "MediaVideoCapture": tr("camera"),
                 "MediaAudioVideoCapture": tr("camera and microphone"), "Geolocation": tr("location"),
                 "Notifications": tr("notifications"), "DesktopVideoCapture": tr("screen sharing"),
                 "DesktopAudioVideoCapture": tr("screen sharing"), "ClipboardReadWrite": tr("clipboard")}
        kind = str(perm.permissionType()).split(".")[-1]
        if self._ask(perm.origin(), names.get(kind, kind)):
            perm.grant()
        else:
            perm.deny()

    def _feature(self, origin, feature) -> None:
        ok = self._ask(origin, str(feature).split(".")[-1])
        self.setFeaturePermission(origin, feature, QWebEnginePage.PermissionGrantedByUser if ok
                                  else QWebEnginePage.PermissionDeniedByUser)



class Browser(QMainWindow):
    def __init__(self, private: bool = False, url: str | None = None):
        super().__init__()
        self.private = private
        self.store = Store("browser", {"engine": "DuckDuckGo", "zoom": 1.0, "home": HOME})
        self.bookmarks = Bookmarks()
        self.history = History()
        self.setWindowTitle(("Nova Browser – " + tr("Private")) if private else "Nova Browser")
        self.resize(1280, 820)
        self.children_windows = []

        if private:
            self.profile = QWebEngineProfile(self)          # bez nazwy = off-the-record
        else:
            self.profile = QWebEngineProfile("nova", self)
            self.profile.setPersistentCookiesPolicy(QWebEngineProfile.AllowPersistentCookies)
        self.profile.setHttpUserAgent(self.profile.httpUserAgent().replace("QtWebEngine", "NovaBrowser"))
        self.profile.downloadRequested.connect(self._download)
        s = self.profile.settings()
        s.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
        s.setAttribute(QWebEngineSettings.ScrollAnimatorEnabled, True)
        s.setAttribute(QWebEngineSettings.PdfViewerEnabled, True)
        s.setAttribute(QWebEngineSettings.DnsPrefetchEnabled, False)  # prywatność
        if hasattr(QWebEngineSettings, "ForceDarkMode") and theme.is_dark() and os.environ.get("NOVA_FORCE_DARK"):
            s.setAttribute(QWebEngineSettings.ForceDarkMode, True)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(8, 6, 8, 6)
        self.back = flat_button("go-previous", tr("Back") + " (Alt+←)")
        self.fwd = flat_button("go-next", tr("Forward") + " (Alt+→)")
        self.reload = flat_button("view-refresh", tr("Reload") + " (F5)")
        home = flat_button("go-home", tr("Home"))
        self.url = QLineEdit()
        self.url.setObjectName("UrlBar")
        self.url.setPlaceholderText(tr("Search or enter address"))
        self.url.returnPressed.connect(lambda: self.load(self.url.text()))
        self.completer_model = QStringListModel(self)
        comp = QCompleter(self.completer_model, self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        self.url.setCompleter(comp)
        self.url.textEdited.connect(self._suggest)
        self.star = flat_button("bookmark-new", tr("Bookmark this page") + " (Ctrl+D)", "starred-symbolic", checkable=True)
        self.star.clicked.connect(self.toggle_bookmark)
        self.dl_btn = flat_button("download", tr("Downloads"), "folder-download")
        self.dl_menu = QMenu(self)
        self.dl_btn.setMenu(self.dl_menu)
        self.dl_btn.setPopupMode(QToolButton.InstantPopup)
        self.menu_btn = flat_button("application-menu", tr("Menu"), "open-menu")
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        self.menu_btn.setMenu(self._build_menu())
        self.back.clicked.connect(lambda: self.view().back())
        self.fwd.clicked.connect(lambda: self.view().forward())
        self.reload.clicked.connect(self._reload_or_stop)
        home.clicked.connect(lambda: self.load(self.store.get("home", HOME)))
        for w in (self.back, self.fwd, self.reload, home):
            bar.addWidget(w)
        bar.addWidget(self.url, 1)
        for w in (self.star, self.dl_btn, self.menu_btn):
            bar.addWidget(w)
        if private:
            lbl = QLabel("🕶 " + tr("Private"))
            lbl.setObjectName("Subtitle")
            bar.addWidget(lbl)
        lay.addLayout(bar)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        self.progress.hide()
        lay.addWidget(self.progress)

        # pasek wyszukiwania na stronie
        self.find_bar = QWidget()
        fb = QHBoxLayout(self.find_bar)
        fb.setContentsMargins(8, 4, 8, 4)
        self.find_edit = QLineEdit()
        self.find_edit.setObjectName("Search")
        self.find_edit.setPlaceholderText(tr("Find in page…"))
        self.find_edit.textChanged.connect(lambda t: self.view().findText(t))
        self.find_edit.returnPressed.connect(lambda: self.view().findText(self.find_edit.text()))
        close_find = flat_button("window-close", tr("Close"))
        close_find.clicked.connect(self._close_find)
        fb.addWidget(self.find_edit, 1)
        fb.addWidget(close_find)
        self.find_bar.hide()
        lay.addWidget(self.find_bar)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.setIconSize(QSize(16, 16))
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._tab_changed)
        plus = QToolButton()
        plus.setIcon(icon("tab-new", "list-add"))
        plus.setAutoRaise(True)
        plus.setToolTip(tr("New tab") + " (Ctrl+T)")
        plus.clicked.connect(lambda: self.new_tab(HOME))
        self.tabs.setCornerWidget(plus)
        lay.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        self.toast = Toast(self)
        self._shortcuts()
        self.new_tab(url or self.store.get("home", HOME))

    # ------------------------------------------------------------ karty
    def view(self) -> QWebEngineView:
        return self.tabs.currentWidget()

    def new_tab(self, url: str | None = None, background: bool = False) -> QWebEngineView:
        v = QWebEngineView()
        v.setPage(Page(self.profile, self))
        v.setZoomFactor(self.store.get("zoom", 1.0))
        idx = self.tabs.addTab(v, tr("New tab"))
        v.titleChanged.connect(lambda t, v=v: self._title(v, t))
        v.iconChanged.connect(lambda ic, v=v: self.tabs.setTabIcon(self.tabs.indexOf(v), ic))
        v.urlChanged.connect(lambda u, v=v: self._url_changed(v, u))
        v.loadStarted.connect(lambda v=v: self._loading(v, True))
        v.loadProgress.connect(lambda p, v=v: v is self.view() and self.progress.setValue(p))
        v.loadFinished.connect(lambda ok, v=v: self._loading(v, False, ok))
        v.page().fullScreenRequested.connect(self._fullscreen)
        if url:
            self.load(url, v)
        if not background:
            self.tabs.setCurrentIndex(idx)
            if not url or url == HOME:
                self.url.setFocus()
        return v

    def close_tab(self, index: int) -> None:
        if self.tabs.count() == 1:
            self.close()
            return
        w = self.tabs.widget(index)
        self.tabs.removeTab(index)
        w.deleteLater()

    def load(self, text: str, view: QWebEngineView | None = None) -> None:
        view = view or self.view()
        url = to_url(text, self.store.get("engine"))
        if url == HOME:
            labels = {"title": tr("New tab"), "tagline": tr("Fast. Private. Yours."),
                      "search": tr("Search the web…")}
            engine = SEARCH_ENGINES.get(self.store.get("engine"), SEARCH_ENGINES["DuckDuckGo"])
            view.setHtml(newtab.render(self.bookmarks.items, engine, theme.is_dark(), labels), QUrl("about:blank"))
        else:
            view.load(QUrl(url))
        view.setFocus()

    def _title(self, v, title: str) -> None:
        i = self.tabs.indexOf(v)
        self.tabs.setTabText(i, title or tr("New tab"))
        self.tabs.setTabToolTip(i, title)
        if v is self.view():
            self.setWindowTitle(f"{title} — Nova Browser" if title else "Nova Browser")

    def _url_changed(self, v, u: QUrl) -> None:
        if v is self.view():
            s = u.toString()
            self.url.setText("" if s.startswith(("nova:", "about:blank", "data:")) else s)
            self.url.setCursorPosition(0)
            self.star.setChecked(self.bookmarks.has(s))
            self._nav_state()

    def _loading(self, v, started: bool, ok: bool = True) -> None:
        if v is self.view():
            self.progress.setVisible(started)
            self.reload.setIcon(icon("process-stop") if started else icon("view-refresh"))
        if not started and ok and not self.private:
            self.history.add(v.url().toString(), v.title())
        self._nav_state()

    def _nav_state(self) -> None:
        v = self.view()
        if v:
            self.back.setEnabled(v.history().canGoBack())
            self.fwd.setEnabled(v.history().canGoForward())

    def _tab_changed(self, _i: int) -> None:
        v = self.view()
        if v:
            self._url_changed(v, v.url())
            self._title(v, v.title())

    def _reload_or_stop(self) -> None:
        if self.progress.isVisible():
            self.view().stop()
        else:
            self.view().reload()

    def _suggest(self, text: str) -> None:
        if len(text) < 2:
            return
        items = [h["url"] for h in self.history.search(text)] + \
                [b["url"] for b in self.bookmarks.items if text.lower() in (b["url"] + b["title"]).lower()]
        self.completer_model.setStringList(list(dict.fromkeys(items)))

    # ------------------------------------------------------------ funkcje
    def toggle_bookmark(self) -> None:
        url = self.view().url().toString()
        if url.startswith(("nova:", "about:", "data:")):
            self.star.setChecked(False)
            return
        added = self.bookmarks.toggle(url, self.view().title())
        self.star.setChecked(added)
        self.toast.show_message(tr("Bookmark added") if added else tr("Bookmark removed"))

    def _download(self, req) -> None:
        folder = user_dir("DOWNLOAD", "Downloads")
        folder.mkdir(parents=True, exist_ok=True)
        req.setDownloadDirectory(str(folder))
        req.accept()
        name = req.downloadFileName()
        bar = QProgressBar()
        bar.setFormat(name + "  %p%")
        bar.setMinimumWidth(280)
        act = QWidgetAction(self.dl_menu)
        act.setDefaultWidget(bar)
        self.dl_menu.insertAction(self.dl_menu.actions()[0] if self.dl_menu.actions() else None, act)

        def prog():
            total = req.totalBytes()
            bar.setValue(int(req.receivedBytes() * 100 / total) if total > 0 else 0)

        def done():
            if req.state() == req.DownloadState.DownloadCompleted:
                bar.setValue(100)
                bar.setFormat("✔ " + name)
                notify(tr("Download complete"), name, "nova-browser", "Nova Browser")
            else:
                bar.setFormat("✘ " + name)

        req.receivedBytesChanged.connect(prog)
        req.isFinishedChanged.connect(done)
        self.toast.show_message(tr("Downloading {n}…", n=name))

    def _fullscreen(self, request) -> None:
        request.accept()
        if request.toggleOn():
            self.showFullScreen()
        else:
            self.showNormal()

    def zoom(self, delta: float) -> None:
        z = 1.0 if delta == 0 else max(0.3, min(3.0, self.view().zoomFactor() + delta))
        self.view().setZoomFactor(z)
        self.store.set("zoom", z)
        self.toast.show_message(tr("Zoom {z}%", z=int(z * 100)), 1000)

    def _show_find(self) -> None:
        self.find_bar.show()
        self.find_edit.setFocus()
        self.find_edit.selectAll()

    def _close_find(self) -> None:
        self.view().findText("")
        self.find_bar.hide()

    def open_private(self) -> None:
        w = Browser(private=True)
        self.children_windows.append(w)
        w.show()

    def _build_menu(self) -> QMenu:
        m = QMenu(self)
        m.addAction(icon("tab-new"), tr("New tab") + "\tCtrl+T", lambda: self.new_tab(HOME))
        m.addAction(icon("view-private", "security-high"), tr("New private window") + "\tCtrl+Shift+N", self.open_private)
        m.addSeparator()
        self.bm_menu = m.addMenu(icon("bookmarks"), tr("Bookmarks"))
        self.bm_menu.aboutToShow.connect(self._fill_bookmarks)
        self.hist_menu = m.addMenu(icon("view-history", "document-open-recent"), tr("History"))
        self.hist_menu.aboutToShow.connect(self._fill_history)
        m.addSeparator()
        m.addAction(icon("zoom-in"), tr("Zoom in") + "\tCtrl++", lambda: self.zoom(0.1))
        m.addAction(icon("zoom-out"), tr("Zoom out") + "\tCtrl+-", lambda: self.zoom(-0.1))
        m.addAction(icon("zoom-original"), tr("Reset zoom") + "\tCtrl+0", lambda: self.zoom(0))
        m.addAction(icon("edit-find"), tr("Find in page") + "\tCtrl+F", self._show_find)
        m.addAction(icon("document-print"), tr("Save as PDF…"), self._pdf)
        m.addSeparator()
        eng = m.addMenu(icon("search"), tr("Search engine"))
        for name in SEARCH_ENGINES:
            a = eng.addAction(name, lambda n=name: self.store.set("engine", n))
            a.setCheckable(True)
            a.setChecked(name == self.store.get("engine"))
        m.addAction(icon("edit-clear-history"), tr("Clear browsing data"), self._clear_data)
        return m

    def _fill_bookmarks(self) -> None:
        self.bm_menu.clear()
        for b in self.bookmarks.items:
            self.bm_menu.addAction(b["title"], lambda u=b["url"]: self.load(u))

    def _fill_history(self) -> None:
        self.hist_menu.clear()
        for h in self.history.search("", 20):
            self.hist_menu.addAction(h.get("title") or h["url"], lambda u=h["url"]: self.load(u))
        self.hist_menu.addSeparator()
        self.hist_menu.addAction(tr("Clear history"), self.history.clear)

    def _pdf(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        name = (self.view().title() or "strona").replace("/", "-")[:80] + ".pdf"
        path, _ = QFileDialog.getSaveFileName(self, tr("Save as PDF…"), str(user_dir("DOWNLOAD", "Downloads") / name), "PDF (*.pdf)")
        if path:
            self.view().page().printToPdf(path)
            self.toast.show_message(tr("Saved: {p}", p=Path(path).name))

    def _clear_data(self) -> None:
        if QMessageBox.question(self, tr("Clear browsing data"),
                                tr("Delete history, cookies and cache?")) == QMessageBox.Yes:
            self.history.clear()
            self.profile.clearHttpCache()
            self.profile.cookieStore().deleteAllCookies()
            self.toast.show_message(tr("Browsing data cleared"))

    def _shortcuts(self) -> None:
        for seq, fn in [("Ctrl+T", lambda: self.new_tab(HOME)), ("Ctrl+W", lambda: self.close_tab(self.tabs.currentIndex())),
                        ("Ctrl+L", lambda: (self.url.setFocus(), self.url.selectAll())), ("F6", lambda: (self.url.setFocus(), self.url.selectAll())),
                        ("F5", lambda: self.view().reload()), ("Ctrl+R", lambda: self.view().reload()),
                        ("Alt+Left", lambda: self.view().back()), ("Alt+Right", lambda: self.view().forward()),
                        ("Ctrl+D", self.star.click), ("Ctrl+F", self._show_find), ("Escape", self._close_find),
                        ("Ctrl++", lambda: self.zoom(0.1)), ("Ctrl+=", lambda: self.zoom(0.1)),
                        ("Ctrl+-", lambda: self.zoom(-0.1)), ("Ctrl+0", lambda: self.zoom(0)),
                        ("Ctrl+Shift+N", self.open_private), ("F11", lambda: self.showNormal() if self.isFullScreen() else self.showFullScreen()),
                        ("Ctrl+Tab", lambda: self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % self.tabs.count()))]:
            QShortcut(QKeySequence(seq), self, activated=fn)


def main() -> int:
    url = next((a for a in sys.argv[1:] if not a.startswith("-")), None)
    private = "--private" in sys.argv
    return novaapp.run(lambda: Browser(private=private, url=url), "nova-browser", "Nova Browser")


if __name__ == "__main__":
    sys.exit(main())
