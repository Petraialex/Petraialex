#!/usr/bin/env python3
"""
portrait.py — turn a headshot into a self-typing ASCII-portrait SVG.

Pipeline (see the guide):
  rembg cut-out -> composite on white -> grayscale
  -> bilateral filter (smooth skin, keep edges)
  -> CLAHE (local contrast, clip 3.0)
  -> darkening curve (v/255)**gamma   <- the main tuning dial
  -> map to the 13-char ramp
  -> emit SVG where each row wipes in left-to-right (SMIL), printing ONCE.

Usage:
  python3 scripts/portrait.py portrait_src.jpg -o portrait.svg
  # then tune if it looks flat/washed out:
  python3 scripts/portrait.py portrait_src.jpg -o portrait.svg --gamma 2.0
  python3 scripts/portrait.py portrait_src.jpg -o portrait.svg --cols 90 --clip 3.0

  # preview the raw ASCII in your terminal without writing an SVG:
  python3 scripts/portrait.py portrait_src.jpg --print

Deps: pillow numpy opencv-python-headless rembg onnxruntime
"""
import argparse
import sys
import numpy as np
import cv2
from PIL import Image

# --- the 13-level ramp: lightest (blank) -> darkest ------------------------
# Must match the font subset in Part 4:  ' .`:-=+*cs#%@'
RAMP = " .`:-=+*cs#%@"

# --- geometry the grid bakes in (Part 4: the 0.600em advance trap) ---------
FONT_SIZE = 12.9          # px
CHAR_W    = 7.74          # px  == 0.600 em at FONT_SIZE  (JetBrains/Liberation/DejaVu Mono)
LINE_H    = CHAR_W * 2.0  # monospace cells are ~2x tall as wide
ROW_ASPECT = 0.48         # rows = cols * (h/w) * 0.48

# --- typing animation ------------------------------------------------------
ROW_STAGGER = 0.09        # s between successive rows starting
ROW_DUR     = 0.55        # s for one row to finish wiping in


def load_gray(path, use_rembg=True):
    """Load image, cut out the subject onto white, return an 8-bit grayscale array."""
    img = Image.open(path).convert("RGBA")
    if use_rembg:
        from rembg import remove
        cut = remove(img)                       # RGBA with alpha
        bg = Image.new("RGBA", cut.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, cut)    # everything outside subject -> white
    else:
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img)
    return np.array(img.convert("L"))


def enhance(gray, clip=3.0):
    """Bilateral smooth + CLAHE local contrast."""
    g = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
    return clahe.apply(g)


def to_grid(gray, cols, gamma):
    """Downscale to the char grid, apply the darkening curve, map to ramp indices."""
    h, w = gray.shape
    rows = max(1, round(cols * (h / w) * ROW_ASPECT))
    small = cv2.resize(gray, (cols, rows), interpolation=cv2.INTER_AREA).astype(np.float32)
    # darkening curve: pushes mid-tones down so brows/glasses/lips survive
    curved = (small / 255.0) ** gamma * 255.0
    # bright -> ramp[0] (blank), dark -> ramp[-1] ('@')
    idx = np.round((255.0 - curved) / 255.0 * (len(RAMP) - 1)).astype(int)
    idx = np.clip(idx, 0, len(RAMP) - 1)
    return ["".join(RAMP[i] for i in row) for row in idx]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_svg(lines, display_w=460):
    ncols = max((len(r) for r in lines), default=0)
    nrows = len(lines)
    vb_w = ncols * CHAR_W
    vb_h = nrows * LINE_H
    full_w = ncols * CHAR_W

    out = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb_w:.2f} {vb_h:.2f}" '
        f'width="{display_w}" font-family="\'JetBrains Mono\', ui-monospace, monospace" '
        f'font-size="{FONT_SIZE}" xml:space="preserve">'
    )
    # Static, fully-visible text. GitHub embeds README graphics via <img>, and
    # browsers render <img> SVGs as STATIC images — no SMIL and no CSS animation
    # advances there. So the portrait must read correctly with zero animation:
    # every row is simply drawn. Theme colour is CSS (that IS honoured, since the
    # .svg is a separate resource GitHub's markdown sanitiser never touches).
    out.append(
        '<style>'
        'text{fill:#1f2328}'
        '@media(prefers-color-scheme:dark){text{fill:#e6edf3}}'
        '</style>'
    )
    for i, line in enumerate(lines):
        y = i * LINE_H + FONT_SIZE
        out.append(f'<text x="0" y="{y:.2f}">{esc(line)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="path to the (tightly cropped) source photo")
    ap.add_argument("-o", "--out", default="portrait.svg")
    ap.add_argument("--cols", type=int, default=90, help="grid width in characters")
    ap.add_argument("--gamma", type=float, default=1.7, help="darkening curve; raise to 1.9-2.1 if flat")
    ap.add_argument("--clip", type=float, default=3.0, help="CLAHE clip limit")
    ap.add_argument("--width", type=int, default=460, help="displayed px width")
    ap.add_argument("--no-rembg", action="store_true", help="skip background removal")
    ap.add_argument("--print", dest="do_print", action="store_true", help="print ASCII to terminal, don't write SVG")
    args = ap.parse_args()

    gray = load_gray(args.input, use_rembg=not args.no_rembg)
    gray = enhance(gray, clip=args.clip)
    lines = to_grid(gray, cols=args.cols, gamma=args.gamma)

    if args.do_print:
        print("\n".join(lines))
        print(f"\n[{len(lines)} rows x {args.cols} cols  gamma={args.gamma}  clip={args.clip}]", file=sys.stderr)
        return

    svg = to_svg(lines, display_w=args.width)
    with open(args.out, "w") as f:
        f.write(svg)
    print(f"wrote {args.out}  ({len(lines)} rows x {args.cols} cols, gamma={args.gamma})")


if __name__ == "__main__":
    main()
