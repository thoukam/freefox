"""Generate the FreeFox brand assets from images/brand/icon.svg.

All text is converted to vector paths, so the SVGs render the same everywhere,
whatever fonts the viewer has installed.

Outputs (in images/brand/): banner.svg, banner.fr.svg, wordmark.svg, wordmark-dark.svg

Requirements (not project dependencies): pip install fonttools
Fonts: Ubuntu Sans and Ubuntu Sans Mono (SIL Open Font License), installed on Ubuntu.

Usage: python scripts/make_brand_assets.py
"""

import re
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

SANS = "/usr/share/fonts/truetype/ubuntu/UbuntuSans[wdth,wght].ttf"
MONO = "/usr/share/fonts/truetype/ubuntu/UbuntuSansMono[wght].ttf"

COLORS = {
    "bg": "#170D06",
    "bg2": "#24140A",
    "border": "#3A2210",
    "cream": "#F5F0E8",
    "muted": "#C9B8A6",
    "orange": "#FF6B00",
    "chip_bg": "#2A170B",
    "chip_border": "#4A2C14",
    "chip_text": "#F0C9A0",
}


class Font:
    def __init__(self, path, axes):
        font = TTFont(path)
        self.font = instancer.instantiateVariableFont(font, axes)
        self.glyphs = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.upm = self.font["head"].unitsPerEm

    def width(self, text, size):
        return sum(self.glyphs[self.cmap[ord(c)]].width for c in text) * size / self.upm

    def path(self, text, x, baseline, size):
        scale = size / self.upm
        pen = SVGPathPen(self.glyphs)
        for ch in text:
            name = self.cmap[ord(ch)]
            self.glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
            x += self.glyphs[name].width * scale
        # One decimal is plenty at banner scale and keeps the files small.
        return re.sub(r"-?\d+\.\d+", lambda m: f"{float(m.group()):.1f}", pen.getCommands())

    def cap_height(self, size):
        bp = BoundsPen(self.glyphs)
        self.glyphs[self.cmap[ord("H")]].draw(bp)
        return bp.bounds[3] * size / self.upm


def banner(icon_inner, tagline, chips, out):
    width, height = 1280, 340
    bold = Font(SANS, {"wght": 800, "wdth": 100})
    regular = Font(SANS, {"wght": 400, "wdth": 100})
    mono = Font(MONO, {"wght": 500})

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="FreeFox: {tagline}">',
        "<title>FreeFox</title>",
        "<defs>",
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">',
        f'<stop offset="0" stop-color="{COLORS["bg2"]}"/>',
        f'<stop offset="1" stop-color="{COLORS["bg"]}"/>',
        "</linearGradient>",
        "</defs>",
        f'<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="28" '
        f'fill="url(#bg)" stroke="{COLORS["border"]}" stroke-width="2"/>',
        # icon: 256 viewBox scaled to 210 px
        f'<g transform="translate(70 62) scale(0.84)">{icon_inner}</g>',
    ]

    x0 = 330
    title_size = 104
    free = bold.path("Free", x0, 150, title_size)
    fox_x = x0 + bold.width("Free", title_size)
    fox = bold.path("Fox", fox_x, 150, title_size)
    parts.append(f'<path d="{free}" fill="{COLORS["cream"]}"/>')
    parts.append(f'<path d="{fox}" fill="{COLORS["orange"]}"/>')

    parts.append(f'<path d="{regular.path(tagline, x0 + 4, 208, 32)}" fill="{COLORS["muted"]}"/>')

    chip_size, pad_x, chip_h, gap = 22, 16, 40, 12
    cx, cy = x0 + 2, 238
    cap = mono.cap_height(chip_size)
    for label in chips:
        w = mono.width(label, chip_size) + 2 * pad_x
        parts.append(
            f'<rect x="{cx:.1f}" y="{cy}" width="{w:.1f}" height="{chip_h}" rx="20" '
            f'fill="{COLORS["chip_bg"]}" stroke="{COLORS["chip_border"]}" stroke-width="1.5"/>'
        )
        baseline = cy + chip_h / 2 + cap / 2
        parts.append(
            f'<path d="{mono.path(label, cx + pad_x, baseline, chip_size)}" '
            f'fill="{COLORS["chip_text"]}"/>'
        )
        cx += w + gap

    parts.append("</svg>")
    Path(out).write_text("\n".join(parts) + "\n")
    return cx


def wordmark(icon_inner, free_color, out):
    bold = Font(SANS, {"wght": 800, "wdth": 100})
    size, x0, baseline = 150, 280, 188
    free = bold.path("Free", x0, baseline, size)
    fox_x = x0 + bold.width("Free", size)
    fox = bold.path("Fox", fox_x, baseline, size)
    width = int(fox_x + bold.width("Fox", size) + 24)
    Path(out).write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 256" '
        'role="img" aria-label="FreeFox">\n'
        "<title>FreeFox</title>\n"
        f"<g>{icon_inner}</g>\n"
        f'<path d="{free}" fill="{free_color}"/>\n'
        f'<path d="{fox}" fill="{COLORS["orange"]}"/>\n'
        "</svg>\n"
    )


def main():
    out_dir = Path(__file__).resolve().parents[1] / "images" / "brand"
    icon_svg = (out_dir / "icon.svg").read_text()
    inner = re.search(r"<title>FreeFox</title>(.*)</svg>", icon_svg, re.S).group(1)
    wordmark(inner, "#1A0A00", out_dir / "wordmark.svg")
    wordmark(inner, COLORS["cream"], out_dir / "wordmark-dark.svg")
    chips = ["ROS 2", "MCAP · db3", "Google Drive", "rsync / NAS", "S3 · MinIO"]
    end_en = banner(
        inner, "Reliable rosbag offloading for ROS 2 robots", chips, out_dir / "banner.svg"
    )
    end_fr = banner(
        inner,
        "Récupération fiable des rosbags pour robots ROS 2",
        chips,
        out_dir / "banner.fr.svg",
    )
    print(f"chips end x: en={end_en:.0f} fr={end_fr:.0f} (banner width 1280)")


if __name__ == "__main__":
    main()
