#!/usr/bin/env python3
"""Top and underside previews from the Gerbers, in roughly the colours of a green HASL board.

Copper under solder mask is lighter green, bare board under mask darker green, mask openings over copper silver
(HASL), mask openings over bare board tan, silkscreen white, holes black. The underside is mirrored, as seen
from below. Each layer is rendered on its own with the board outline, so all the images line up.
"""
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

CPU01 = Path(__file__).resolve().parent.parent
G = CPU01 / "gerbers"
IMG = CPU01 / "images"
IMG.mkdir(exist_ok=True)
N = "68000Relocator"
DPI = "500"
EDGE = G / f"{N}-Edge_Cuts.gm1"
COL = {
    "outside": (12, 40, 24), "fr4_mask": (24, 92, 48), "cu_mask": (46, 139, 78), "cu_bare": (205, 205, 200),
    "fr4_bare": (196, 172, 112), "silk": (245, 245, 240), "hole": (10, 10, 10), "edge": (230, 190, 70),
}


def layer(path, tmp):
    """Boolean image of one Gerber layer (the board outline drawn in red fixes the window)."""
    out = Path(tmp) / (path.name + ".png")
    subprocess.run(["gerbv", "-x", "png", "-D", DPI, "-B", "0", "-b", "#000000", "-o", str(out),
                    "--foreground=#ff0000", str(EDGE), "--foreground=#ffffff", str(path)],
                   check=True, capture_output=True)
    a = np.asarray(Image.open(out).convert("RGB")).astype(int)
    return (a[:, :, 1] > 128), (a[:, :, 0] > 128) & (a[:, :, 1] < 100)


def board_area(edge):
    im = Image.fromarray(np.where(edge, 255, 0).astype("uint8"))
    ImageDraw.floodfill(im, (0, 0), 128)
    return np.asarray(im) != 128


for side, (cu, mask, silk) in {"top": ("F_Cu.gtl", "F_Mask.gts", "F_Silkscreen.gto"),
                               "bottom": ("B_Cu.gbl", "B_Mask.gbs", "B_Silkscreen.gbo")}.items():
    with tempfile.TemporaryDirectory() as tmp:
        c, edge = layer(G / f"{N}-{cu}", tmp)
        m, _ = layer(G / f"{N}-{mask}", tmp)
        s, _ = layer(G / f"{N}-{silk}", tmp)
        h, _ = layer(G / f"{N}-PTH.drl", tmp)
    on = board_area(edge)
    out = np.zeros(c.shape + (3,), "uint8")
    out[:] = COL["outside"]
    for sel, col in ((on & ~c, "fr4_mask"), (on & c, "cu_mask"), (on & m & ~c, "fr4_bare"), (on & m & c, "cu_bare"),
                     (on & s & ~m, "silk"), (on & h, "hole"), (edge, "edge")):
        out[sel] = COL[col]
    im = Image.fromarray(out)
    if side == "bottom":
        im = ImageOps.mirror(im)
    im.save(IMG / f"{side}.png")
print(f"previews in {IMG}")
