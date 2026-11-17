#!/bin/sh
# Rebuild CPU-01 from upstream/68000Relocator.kicad_pcb (LinuxJedi's v2c): board, DRC, Gerbers, JLC files, previews.
# Needs KiCad 7 (kicad-cli, pcbnew Python, footprint libraries), gerbv, and Python with shapely and Pillow.
set -e
cd "$(dirname "$0")"
python3 tools/apply_cpu01.py
python3 tools/drc.py
rm -rf gerbers && mkdir gerbers
kicad-cli pcb export gerbers --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts \
    --subtract-soldermask --no-x2 --no-netlist -o gerbers/ ../68000Relocator.kicad_pcb >/dev/null
kicad-cli pcb export drill --format excellon --excellon-units mm --excellon-zeros-format decimal \
    --excellon-separate-th -o gerbers/ ../68000Relocator.kicad_pcb >/dev/null
rm -f gerbers/*NPTH.drl gerbers/*.gbrjob     # no unplated holes on this board
python3 tools/jlc.py
python3 tools/preview.py
echo "CPU-01 built: DRC passed, files in jlc/"
