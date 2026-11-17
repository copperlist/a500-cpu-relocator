#!/usr/bin/env python3
"""JLCPCB production files: Gerber zip, BOM and CPL, named with part number and version."""
import csv
import re
import subprocess
import zipfile
from pathlib import Path

CPU01 = Path(__file__).resolve().parent.parent
REPO = CPU01.parent
src = (CPU01 / "tools" / "apply_cpu01.py").read_text()
PRODUCT = re.search(r'PRODUCT, REV = "([^"]+)", "([^"]+)"', src).group(1)
REV = re.search(r'PRODUCT, REV = "([^"]+)", "([^"]+)"', src).group(2)
NAME = f"{PRODUCT}_v{REV}"
OUT = CPU01 / "jlc"
OUT.mkdir(exist_ok=True)
for old in OUT.glob("*"):
    old.unlink()

# BOM: what JLC can place. The two 64-pin rows are hand-soldered round machined pin strips (see README).
BOM = {"100nF": ("100nF 50V X7R", "0805", "C49678")}
pos = subprocess.run(["kicad-cli", "pcb", "export", "pos", str(REPO / "68000Relocator.kicad_pcb"), "-o", "/dev/stdout",
                      "--format", "csv", "--units", "mm", "--side", "both", "--smd-only"],
                     capture_output=True, text=True, check=True).stdout
rows = list(csv.DictReader(pos.splitlines()))
rows = [r for r in rows if r.get("Side")]          # kicad-cli also prints "Loading board"
assert sorted(r["Ref"] for r in rows) == ["C1", "C2"], rows
with open(OUT / f"{NAME}_CPL.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for r in rows:
        w.writerow([r["Ref"], f"{float(r['PosX']):.4f}mm", f"{float(r['PosY']):.4f}mm",
                    "Bottom" if r["Side"] == "bottom" else "Top", f"{float(r['Rot']) % 360:.1f}"])
with open(OUT / f"{NAME}_BOM.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
    for val, (comment, pkg, lcsc) in BOM.items():
        refs = ",".join(sorted(r["Ref"] for r in rows if r["Val"] == val))
        w.writerow([comment, refs, pkg, lcsc])
with zipfile.ZipFile(OUT / f"{NAME}_gerbers.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for g in sorted((CPU01 / "gerbers").iterdir()):
        if g.suffix in (".gbrjob",) or "drl_map" in g.name:
            continue
        z.write(g, g.name)
print(f"JLC files written to {OUT}: {', '.join(sorted(p.name for p in OUT.iterdir()))}")
