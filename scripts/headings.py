#!/usr/bin/env python3
"""
headings.py — draw lowercase section headings as SVGs (hd-<slug>.svg).

GitHub strips CSS and inline SVG from README markdown, so the only way to put
your own typeface on a heading is to ship it as an image. Each heading is the
label in JetBrains Mono followed by a hairline rule running to the right edge.

No API calls, no arguments — edit LABELS to change the set.
"""
import re

LABELS = ["about", "stack", "projects", "stats", "about this page"]

W = 760                 # content width
H = 30
FS = 15                 # heading font-size
CHAR_W = FS * 0.6       # JetBrains Mono advance
GAP = 14                # gap between label and rule
FONT = "'JetBrains Mono', ui-monospace, SFMono-Regular, monospace"

STYLE = ("<style>.s{fill:#1f2328}.r{stroke:#d0d7de}"
         "@media(prefers-color-scheme:dark){.s{fill:#e6edf3}.r{stroke:#30363d}}</style>")


def slug(label):
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def build(label):
    text_w = len(label) * CHAR_W
    line_x = text_w + GAP
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
            f'width="{W}" font-family="{FONT}">{STYLE}'
            f'<text class="s" x="0" y="20" font-size="{FS}" font-weight="600" '
            f'letter-spacing="0.5">{label}</text>'
            f'<line class="r" x1="{line_x:.1f}" y1="14" x2="{W}" y2="14" '
            f'stroke-width="1"/></svg>')


def main():
    for label in LABELS:
        name = f"hd-{slug(label)}.svg"
        with open(name, "w") as f:
            f.write(build(label))
        print(f"wrote {name}")


if __name__ == "__main__":
    main()
