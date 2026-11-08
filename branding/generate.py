#!/usr/bin/env python3
"""
NovaOS – generator brandingu.

Tworzy z kodu (bez zewnętrznych plików graficznych):
  * logo NovaOS (symbol + napis) w SVG i PNG,
  * ikony wszystkich aplikacji Nova (spójny styl "squircle" + glif),
  * tapety (ciemna i jasna) w kilku rozdzielczościach,
  * grafiki dla Plymouth, GRUB, SDDM, Calamares i motywu Plasma.

Użycie:  python3 branding/generate.py <katalog_wyjściowy>
Wymaga:  rsvg-convert (librsvg) oraz fontu Inter (fonts-inter).
"""
from __future__ import annotations

import json
import math
import random
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------- paleta
VIOLET = "#A855F7"
INDIGO = "#7B61FF"   # kolor akcentu NovaOS (fioletowo-niebieski)
BLUE = "#3B82F6"
CYAN = "#22D3EE"
NIGHT = "#0B0B1A"

# Ikony: (id, nazwa, gradient_od, gradient_do, funkcja_glifu)
APPS = [
    ("nova-browser", "Nova Browser", "#3B82F6", "#22D3EE"),
    ("nova-files", "Nova Files", "#7B61FF", "#3B82F6"),
    ("nova-terminal", "Nova Terminal", "#312E81", "#1E1B4B"),
    ("nova-settings", "Nova Settings", "#6366F1", "#8B5CF6"),
    ("nova-store", "Nova Store", "#8B5CF6", "#EC4899"),
    ("nova-music", "Nova Music", "#EC4899", "#8B5CF6"),
    ("nova-gallery", "Nova Gallery", "#06B6D4", "#7B61FF"),
    ("nova-calculator", "Nova Calculator", "#475569", "#1E293B"),
    ("nova-notes", "Nova Notes", "#F59E0B", "#F97316"),
    ("nova-monitor", "Nova Monitor", "#10B981", "#3B82F6"),
    ("novaos-installer", "Zainstaluj NovaOS", "#A855F7", "#3B82F6"),
]


# ---------------------------------------------------------------- symbol
def star_path(cx: float, cy: float, r: float, waist: float = 0.16) -> str:
    """Czteroramienna gwiazda 'nova' z wklęsłymi bokami (krzywe Béziera)."""
    w = r * waist
    pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    d = f"M{pts[0][0]:.2f},{pts[0][1]:.2f} "
    for i in range(4):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % 4]
        # punkt kontrolny przyciągnięty do środka => wklęsły bok
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        kx = cx + (mx - cx) * (w / r) * 1.4
        ky = cy + (my - cy) * (w / r) * 1.4
        d += f"Q{kx:.2f},{ky:.2f} {x1:.2f},{y1:.2f} "
    return d + "Z"


def logo_symbol(size: int = 512, mono: str | None = None) -> str:
    """Symbol NovaOS: gwiazda nova na orbicie, gradient fiolet→niebieski."""
    c = size / 2
    fill = mono or "url(#nvG)"
    stroke = mono or "url(#nvR)"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">
  <defs>
    <linearGradient id="nvG" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{VIOLET}"/><stop offset=".5" stop-color="{INDIGO}"/><stop offset="1" stop-color="{BLUE}"/>
    </linearGradient>
    <linearGradient id="nvR" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{VIOLET}"/>
    </linearGradient>
    <radialGradient id="nvGlow"><stop offset="0" stop-color="#fff" stop-opacity=".95"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
  </defs>
  <g transform="rotate(-28 {c} {c})">
    <ellipse cx="{c}" cy="{c}" rx="{size*0.44:.1f}" ry="{size*0.17:.1f}" fill="none" stroke="{stroke}" stroke-width="{size*0.035:.1f}" opacity=".9"/>
  </g>
  <path d="{star_path(c, c, size*0.36)}" fill="{fill}"/>
  {'' if mono else f'<circle cx="{c}" cy="{c}" r="{size*0.07:.1f}" fill="url(#nvGlow)"/>'}
  <circle cx="{c + size*0.37:.1f}" cy="{c - size*0.205:.1f}" r="{size*0.035:.1f}" fill="{mono or CYAN}"/>
</svg>"""


def text_wordmark(width: int = 760, height: int = 200, text_color: str = "#FFFFFF") -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <text x="{width/2:.0f}" y="{height*0.72:.0f}" text-anchor="middle" font-family="Inter" font-weight="700" font-size="{height*0.7:.0f}" fill="{text_color}" letter-spacing="-4">Nova<tspan fill="{INDIGO}" font-weight="300">OS</tspan></text>
</svg>"""


def logo_wordmark(width: int = 1200, height: int = 360, text_color: str = "#FFFFFF") -> str:
    sym = logo_symbol(height).split("\n", 1)[1].rsplit("</svg>", 1)[0]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <svg x="0" y="0" width="{height}" height="{height}" viewBox="0 0 {height} {height}">{sym}</svg>
  <text x="{height*1.05:.0f}" y="{height*0.66:.0f}" font-family="Inter" font-weight="700" font-size="{height*0.42:.0f}" fill="{text_color}" letter-spacing="-4">Nova<tspan fill="{INDIGO}" font-weight="300">OS</tspan></text>
</svg>"""


# ---------------------------------------------------------------- ikony
def gear_path(cx, cy, r_out, r_in, teeth=8):
    pts = []
    for i in range(teeth * 4):
        a = (i / (teeth * 4)) * 2 * math.pi
        r = r_out if (i % 4) in (0, 1) else r_in
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"


GLYPHS = {
    "nova-browser": """<circle cx="50" cy="50" r="24" fill="none" stroke="#fff" stroke-width="5"/>
      <ellipse cx="50" cy="50" rx="11" ry="24" fill="none" stroke="#fff" stroke-width="4"/>
      <path d="M27 42h46M27 58h46" stroke="#fff" stroke-width="4" stroke-linecap="round"/>""",
    "nova-files": """<path d="M24 34a5 5 0 0 1 5-5h14l6 6h22a5 5 0 0 1 5 5v26a5 5 0 0 1-5 5H29a5 5 0 0 1-5-5z" fill="#fff" opacity=".95"/>
      <path d="M24 44h52" stroke="url(#bg)" stroke-width="4"/>""",
    "nova-terminal": """<path d="M28 36l14 14-14 14" fill="none" stroke="#A5B4FC" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M48 66h24" stroke="#fff" stroke-width="7" stroke-linecap="round"/>""",
    "nova-settings": f"""<path d="{gear_path(50, 50, 26, 20, 8)}" fill="#fff"/>
      <circle cx="50" cy="50" r="9" fill="url(#bg)"/>""",
    "nova-store": """<path d="M30 40h40l-3 30a5 5 0 0 1-5 4H38a5 5 0 0 1-5-4z" fill="#fff"/>
      <path d="M40 42v-6a10 10 0 0 1 20 0v6" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round"/>
      <path d="M50 50l2.4 5 5.6.8-4 3.9.9 5.5-4.9-2.6-4.9 2.6.9-5.5-4-3.9 5.6-.8z" fill="url(#bg)"/>""",
    "nova-music": """<path d="M42 66V34l26-6v32" fill="none" stroke="#fff" stroke-width="5" stroke-linejoin="round"/>
      <circle cx="36" cy="66" r="8" fill="#fff"/><circle cx="62" cy="60" r="8" fill="#fff"/>""",
    "nova-gallery": """<rect x="25" y="30" width="50" height="40" rx="7" fill="#fff"/>
      <path d="M29 66l14-16 10 11 7-7 11 12z" fill="url(#bg)"/>
      <circle cx="62" cy="42" r="5" fill="url(#bg)"/>""",
    "nova-calculator": """<rect x="30" y="24" width="40" height="52" rx="7" fill="#fff"/>
      <rect x="35" y="29" width="30" height="11" rx="3" fill="#7B61FF"/>
      <g fill="#334155"><circle cx="40" cy="49" r="3.5"/><circle cx="50" cy="49" r="3.5"/><circle cx="60" cy="49" r="3.5"/>
      <circle cx="40" cy="59" r="3.5"/><circle cx="50" cy="59" r="3.5"/><circle cx="60" cy="59" r="3.5"/>
      <circle cx="40" cy="69" r="3.5"/><circle cx="50" cy="69" r="3.5"/></g><circle cx="60" cy="69" r="3.5" fill="#7B61FF"/>""",
    "nova-notes": """<rect x="29" y="24" width="38" height="52" rx="6" fill="#fff"/>
      <path d="M36 38h24M36 47h24M36 56h15" stroke="#F59E0B" stroke-width="4" stroke-linecap="round"/>
      <path d="M58 70l16-16 5 5-16 16h-5z" fill="#7B61FF"/>""",
    "nova-monitor": """<rect x="24" y="28" width="52" height="40" rx="6" fill="none" stroke="#fff" stroke-width="5"/>
      <path d="M30 52h9l5-11 8 20 6-13h12" fill="none" stroke="#fff" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M40 76h20" stroke="#fff" stroke-width="5" stroke-linecap="round"/>""",
    "novaos-installer": """<path d="M50 24v30M38 43l12 12 12-12" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
      <rect x="26" y="60" width="48" height="16" rx="5" fill="#fff"/><circle cx="66" cy="68" r="3" fill="url(#bg)"/>""",
}


def app_icon(icon_id: str, c1: str, c2: str) -> str:
    """Ikona 100x100: zaokrąglony kwadrat (squircle) z gradientem i glifem."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 100 100">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient>
    <linearGradient id="hl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".28"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/></linearGradient>
    <filter id="sh" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#000" flood-opacity=".35"/></filter>
  </defs>
  <rect x="6" y="6" width="88" height="88" rx="24" fill="url(#bg)" filter="url(#sh)"/>
  <rect x="6" y="6" width="88" height="88" rx="24" fill="url(#hl)"/>
  <rect x="6.5" y="6.5" width="87" height="87" rx="23.5" fill="none" stroke="#fff" stroke-opacity=".18"/>
  {GLYPHS[icon_id]}
</svg>"""


def start_icon() -> str:
    """Ikona przycisku menu Start – sam symbol na przezroczystym tle."""
    return logo_symbol(256)


# ---------------------------------------------------------------- tapety
def wallpaper(w: int, h: int, dark: bool, seed: int = 7) -> str:
    rnd = random.Random(seed)
    if dark:
        bg = ("#07071A", "#120B33", "#071833")
        blobs = [(0.22, 0.30, 0.55, VIOLET, 0.55), (0.80, 0.70, 0.60, BLUE, 0.50),
                 (0.55, 0.45, 0.35, INDIGO, 0.45), (0.92, 0.12, 0.25, CYAN, 0.18)]
        star_op = 0.85
    else:
        bg = ("#EEF0FF", "#E4DEFF", "#DCEBFF")
        blobs = [(0.20, 0.25, 0.55, "#C4B5FD", 0.75), (0.82, 0.75, 0.60, "#93C5FD", 0.70),
                 (0.55, 0.50, 0.35, "#A5B4FC", 0.55), (0.90, 0.10, 0.25, "#A5F3FC", 0.45)]
        star_op = 0.0
    defs, shapes = [], []
    for i, (x, y, r, col, op) in enumerate(blobs):
        defs.append(f'<radialGradient id="b{i}"><stop offset="0" stop-color="{col}" stop-opacity="{op}"/>'
                    f'<stop offset="1" stop-color="{col}" stop-opacity="0"/></radialGradient>')
        shapes.append(f'<ellipse cx="{x*w:.0f}" cy="{y*h:.0f}" rx="{r*w:.0f}" ry="{r*h*1.1:.0f}" fill="url(#b{i})"/>')
    # fale (aurora) – gładkie krzywe z gradientem
    waves = []
    for k in range(7):
        y0 = h * (0.58 + k * 0.035)
        amp = h * (0.10 - k * 0.008)
        p = f"M0,{y0:.0f} C{w*0.25:.0f},{y0-amp:.0f} {w*0.45:.0f},{y0+amp*1.4:.0f} {w*0.7:.0f},{y0-amp*0.4:.0f} S{w*0.95:.0f},{y0-amp*1.2:.0f} {w:.0f},{y0-amp*0.6:.0f}"
        waves.append(f'<path d="{p}" fill="none" stroke="url(#wv)" stroke-width="{max(2, w/900):.1f}" opacity="{0.55 - k*0.06:.2f}"/>')
    stars = []
    if star_op:
        for _ in range(int(w * h / 26000)):
            sx, sy = rnd.random() * w, rnd.random() * h * 0.8
            sr = rnd.choice([0.6, 0.8, 1.0, 1.4, 2.0]) * w / 1920
            stars.append(f'<circle cx="{sx:.0f}" cy="{sy:.0f}" r="{sr:.2f}" fill="#fff" opacity="{rnd.uniform(.2, star_op):.2f}"/>')
    # duża, bardzo subtelna gwiazda nova w tle
    nova = f'<path d="{star_path(w*0.68, h*0.40, h*0.20)}" fill="url(#nv)" opacity="{0.22 if dark else 0.35}"/>'
    wave_a, wave_b = (VIOLET, CYAN) if dark else ("#7C3AED", "#2563EB")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{bg[0]}"/><stop offset=".55" stop-color="{bg[1]}"/><stop offset="1" stop-color="{bg[2]}"/>
    </linearGradient>
    <linearGradient id="wv" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{wave_a}" stop-opacity="0"/><stop offset=".4" stop-color="{wave_a}"/>
      <stop offset=".75" stop-color="{wave_b}"/><stop offset="1" stop-color="{wave_b}" stop-opacity="0"/>
    </linearGradient>
    <radialGradient id="nv"><stop offset="0" stop-color="#fff"/><stop offset=".35" stop-color="{INDIGO}"/><stop offset="1" stop-color="{BLUE}" stop-opacity="0"/></radialGradient>
    {''.join(defs)}
  </defs>
  <rect width="{w}" height="{h}" fill="url(#sky)"/>
  {''.join(shapes)}
  {''.join(stars)}
  {nova}
  {''.join(waves)}
</svg>"""


# ---------------------------------------------------------------- render
def write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def render(svg: Path, png: Path, w: int, h: int | None = None) -> None:
    png.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["rsvg-convert", "-w", str(w)]
    if h:
        cmd += ["-h", str(h)]
    subprocess.run(cmd + ["-o", str(png), str(svg)], check=True)


def simple_svg(w, h, body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{body}</svg>'


def main(out: Path) -> None:
    if not shutil.which("rsvg-convert"):
        sys.exit("Brak rsvg-convert (zainstaluj librsvg2-bin / librsvg)")
    src = out / "svg"

    # --- logo
    logo = write(src / "novaos-logo.svg", logo_symbol(512))
    logo_mono = write(src / "novaos-logo-symbolic.svg", logo_symbol(512, mono="#FFFFFF"))
    word = write(src / "novaos-wordmark.svg", logo_wordmark())
    word_dark = write(src / "novaos-wordmark-dark.svg", logo_wordmark(text_color="#14112B"))
    for s in (64, 128, 256, 512):
        render(logo, out / "logo" / f"novaos-logo-{s}.png", s)
    render(word, out / "logo" / "novaos-wordmark.png", 1200)
    render(word_dark, out / "logo" / "novaos-wordmark-dark.png", 1200)

    # --- ikony (hicolor)
    icons = out / "icons" / "hicolor"
    for icon_id, _name, c1, c2 in APPS:
        svg = write(icons / "scalable" / "apps" / f"{icon_id}.svg", app_icon(icon_id, c1, c2))
        for s in (32, 48, 64, 128, 256):
            render(svg, icons / f"{s}x{s}" / "apps" / f"{icon_id}.png", s)
    for name in ("novaos-logo", "novaos-start", "start-here-novaos"):
        svg = write(icons / "scalable" / "apps" / f"{name}.svg", start_icon())
        for s in (32, 48, 64, 128, 256):
            render(svg, icons / f"{s}x{s}" / "apps" / f"{name}.png", s)
    shutil.copy(logo_mono, icons / "scalable" / "apps" / "novaos-logo-symbolic.svg")

    # --- tapety: pakiet Plasma z wariantem jasnym (images) i ciemnym (images_dark)
    wp = out / "wallpapers" / "NovaOS"
    for (w, h) in ((1920, 1080), (2560, 1440), (3840, 2160)):
        for dark, sub in ((False, "images"), (True, "images_dark")):
            svg = write(src / f"wallpaper-{'dark' if dark else 'light'}-{w}x{h}.svg", wallpaper(w, h, dark))
            render(svg, wp / "contents" / sub / f"{w}x{h}.png", w, h)
    write(wp / "metadata.json", json.dumps({
        "KPlugin": {"Id": "NovaOS", "Name": "NovaOS Aurora", "Name[pl]": "NovaOS Zorza",
                    "Authors": [{"Name": "NovaOS Team"}], "License": "CC-BY-SA-4.0"}}, indent=2, ensure_ascii=False))
    render(src / "wallpaper-dark-1920x1080.svg", wp / "contents" / "screenshot.png", 400, 225)

    # --- Plymouth
    ply = out / "plymouth"
    render(logo, ply / "logo.png", 160)
    render(write(src / "novaos-text.svg", text_wordmark()), ply / "wordmark.png", 240)
    write(src / "pb.svg", simple_svg(300, 6, '<rect width="300" height="6" rx="3" fill="#ffffff" fill-opacity=".14"/>'))
    write(src / "pf.svg", simple_svg(300, 6, f'<defs><linearGradient id="g"><stop offset="0" stop-color="{VIOLET}"/><stop offset="1" stop-color="{BLUE}"/></linearGradient></defs><rect width="300" height="6" rx="3" fill="url(#g)"/>'))
    write(src / "entry.svg", simple_svg(320, 44, '<rect x="1" y="1" width="318" height="42" rx="21" fill="#ffffff" fill-opacity=".08" stroke="#ffffff" stroke-opacity=".3"/>'))
    write(src / "bullet.svg", simple_svg(14, 14, '<circle cx="7" cy="7" r="5" fill="#fff"/>'))
    write(src / "lock.svg", simple_svg(24, 24, '<rect x="5" y="10" width="14" height="10" rx="2" fill="#fff"/><path d="M8 10V7a4 4 0 0 1 8 0v3" fill="none" stroke="#fff" stroke-width="2"/>'))
    for n, w in (("pb", 300), ("pf", 300), ("entry", 320), ("bullet", 14), ("lock", 24)):
        render(src / f"{n}.svg", ply / f"{ {'pb': 'progress_bg', 'pf': 'progress_fg'}.get(n, n)}.png", w)

    # --- GRUB (tło 1920x1080 + zaznaczenie)
    grub = out / "grub"
    render(src / "wallpaper-dark-1920x1080.svg", grub / "background.png", 1920, 1080)
    render(logo, grub / "logo.png", 128)
    write(src / "sel.svg", simple_svg(64, 48, f'<rect x="0" y="0" width="64" height="48" rx="10" fill="{INDIGO}" fill-opacity=".55"/>'))
    for part, (x, y, w, h) in {"c": (16, 16, 32, 16), "n": (16, 0, 32, 16), "s": (16, 32, 32, 16),
                               "w": (0, 16, 16, 16), "e": (48, 16, 16, 16), "nw": (0, 0, 16, 16),
                               "ne": (48, 0, 16, 16), "sw": (0, 32, 16, 16), "se": (48, 32, 16, 16)}.items():
        frag = write(src / f"sel_{part}.svg", simple_svg(w, h,
                     f'<svg x="{-x}" y="{-y}" width="64" height="48"><rect width="64" height="48" rx="10" fill="{INDIGO}" fill-opacity=".55"/></svg>'))
        render(frag, grub / f"select_{part}.png", w, h)

    # --- SDDM / Calamares / Plasma look-and-feel
    render(src / "wallpaper-dark-1920x1080.svg", out / "sddm" / "background.png", 1920, 1080)
    render(logo, out / "sddm" / "logo.png", 128)
    cal = out / "calamares"
    render(logo, cal / "logo.png", 128)
    render(word, cal / "welcome.png", 600)
    render(word_dark, cal / "welcome-light.png", 600)
    render(logo, cal / "languages.png", 96)
    lnf = out / "lookandfeel"
    render(src / "wallpaper-dark-1920x1080.svg", lnf / "fullscreenpreview.jpg.png", 1920, 1080)
    render(src / "wallpaper-dark-1920x1080.svg", lnf / "preview.png", 480, 270)
    render(logo, lnf / "splash-logo.png", 192)
    print(f"Branding wygenerowany w {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]).resolve())
