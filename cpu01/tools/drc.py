#!/usr/bin/env python3
"""Run KiCad's DRC on the board and fail on anything but the one intended item.

The two 64-pin footprints (U1 into the motherboard socket, U2 the relocated socket) overlap at the corner where
they meet; that is the relocator's design. It is also listed as an exclusion in 68000Relocator.kicad_pro for
KiCad's own DRC window.
"""
import re
import sys
import tempfile
from pathlib import Path

import pcbnew

REPO = Path(__file__).resolve().parent.parent.parent
board = pcbnew.LoadBoard(str(REPO / "68000Relocator.kicad_pcb"))
with tempfile.TemporaryDirectory() as d:
    rpt = Path(d) / "drc.rpt"
    pcbnew.WriteDRCReport(board, str(rpt), pcbnew.EDA_UNITS_MILLIMETRES, True)
    text = rpt.read_text()
items = re.findall(r"^\[(\w+)\]: (.*?)\n((?:    .*\n)+)", text, re.M)
allowed = [it for it in items if it[0] == "courtyards_overlap" and "Footprint U1" in it[2] and "Footprint U2" in it[2]]
bad = [it for it in items if it not in allowed]
unconnected = int(re.search(r"Found (\d+) unconnected pads", text).group(1))
for code, msg, where in bad:
    print(f"[{code}] {msg}\n{where}")
print(f"DRC: {len(bad)} problems, {len(allowed)} intended (U1/U2 courtyard overlap), {unconnected} unconnected pads")
sys.exit(1 if bad or unconnected else 0)
