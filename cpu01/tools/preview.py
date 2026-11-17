#!/usr/bin/env python3
"""Top and underside previews from the Gerbers (the underside is mirrored, as seen from below)."""
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

CPU01 = Path(__file__).resolve().parent.parent
G = CPU01 / "gerbers"
IMG = CPU01 / "images"
IMG.mkdir(exist_ok=True)
n = "68000Relocator"
SIDES = {
    "top": [("F_Mask.gts", "#1f6f3a"), ("F_Cu.gtl", "#2e8b4e"), ("F_Silkscreen.gto", "#ffffff"),
            ("Edge_Cuts.gm1", "#ffd54f"), ("PTH.drl", "#111111")],
    "bottom": [("B_Mask.gbs", "#1f6f3a"), ("B_Cu.gbl", "#2e8b4e"), ("B_Silkscreen.gbo", "#ffffff"),
               ("Edge_Cuts.gm1", "#ffd54f"), ("PTH.drl", "#111111")],
}
for side, layers in SIDES.items():
    args = ["gerbv", "-x", "png", "-D", "500", "-B", "0", "-b", "#0d3b1e", "-o", str(IMG / f"{side}.png")]
    for f, col in reversed(layers):        # gerbv draws the first file on top
        args += [f"--foreground={col}", str(G / f"{n}-{f}")]
    subprocess.run(args, check=True, capture_output=True)
    if side == "bottom":
        im = Image.open(IMG / "bottom.png")
        ImageOps.mirror(im).save(IMG / "bottom.png")
print(f"previews in {IMG}")
