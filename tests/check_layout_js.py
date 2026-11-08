#!/usr/bin/env python3
"""Uruchamia layout.js motywu globalnego z atrapą API skryptowego Plasma 6
i sprawdza, że powstaje panel z oczekiwanymi widżetami i tapetą."""
import json
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtQml import QJSEngine

app = QCoreApplication(sys.argv)

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "packages/novaos-desktop/usr/share/plasma/look-and-feel/org.novaos.desktop/contents/layouts/org.kde.plasma.desktop-layout.js"

MOCK = r"""
var __log = {panels: [], desktops: []};
function __Applet(type) { this.type = type; this.config = {}; this.group = []; }
__Applet.prototype.writeConfig = function(k, v) { this.config[this.group.join("/") + "/" + k] = v; };
Object.defineProperty(__Applet.prototype, "currentConfigGroup", {
    set: function(g) { this.group = g; }, get: function() { return this.group; } });
function Panel() { this.widgets = []; __log.panels.push(this); }
Panel.prototype.addWidget = function(t) { var a = new __Applet(t); this.widgets.push(a); return a; };
function desktops() { var d = new __Applet("org.kde.plasma.folder"); __log.desktops.push(d); return [d]; }
var gridUnit = 18;
"""

eng = QJSEngine()
eng.installExtensions(QJSEngine.ConsoleExtension)
r = eng.evaluate(MOCK + JS.read_text(), str(JS))
if r.isError():
    print("JS ERROR:", r.toString(), "line", r.property("lineNumber").toInt())
    sys.exit(1)
res = json.loads(eng.evaluate("JSON.stringify({p: __log.panels.map(function(p){return {loc:p.location, float:p.floating, len:p.lengthMode, w:p.widgets.map(function(w){return w.type})}}), d: __log.desktops.map(function(d){return d.config})})").toString())
print(json.dumps(res, indent=1, ensure_ascii=False))
w = res["p"][0]["w"]
assert res["p"][0]["loc"] == "bottom" and res["p"][0]["float"] is True
for need in ("org.kde.plasma.kickoff", "org.kde.plasma.icontasks", "org.kde.plasma.systemtray",
             "org.novaos.controlcenter", "org.kde.plasma.digitalclock"):
    assert need in w, need
assert res["d"][0]["Wallpaper/org.kde.image/General/Image"].endswith("/usr/share/wallpapers/NovaOS/")
print("layout.js OK")
