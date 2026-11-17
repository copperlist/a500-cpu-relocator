#!/usr/bin/env python3
"""Turn LinuxJedi's Open68000Relocator v2c board into CopperList CPU-01.

Reads cpu01/upstream/68000Relocator.kicad_pcb (upstream v2c, unchanged) and writes the repo's
68000Relocator.kicad_pcb. Run from anywhere; needs KiCad 7 (pcbnew Python, footprint libraries) and shapely.

Changes, all listed in cpu01/README.md:
  1. C1 and C2: 0603 -> 0805 hand-solder footprint, same positions, same nets.
  2. Silkscreen: a full outline with a large filled pin-1 notch for the original CPU position (top and
     underside) and for the relocated socket (top). Replaces upstream's thin outlines.
  3. DRC clean-up: A8/A11 spacing on In1.Cu, four dangling track stubs, silkscreen over pads.
  4. CopperList branding on the underside: bare-copper wordmark, URL, part number and version, licence.
     LinuxJedi's own text and logos on the top are kept as they are.
"""
import math
import re
import shutil
import sys
from pathlib import Path

import pcbnew
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

PRODUCT, REV = "CPU-01", "0.1"

CPU01 = Path(__file__).resolve().parent.parent
REPO = CPU01.parent
SRC = CPU01 / "upstream" / "68000Relocator.kicad_pcb"
DST = REPO / "68000Relocator.kicad_pcb"
FP_LIB = "/usr/share/kicad/footprints/Capacitor_SMD.pretty"
CAP_FP = "C_0805_2012Metric_Pad1.18x1.45mm_HandSolder"

# Load the upstream board through the repo's project, so its net classes and rules apply.
shutil.copyfile(SRC, DST)
board = pcbnew.LoadBoard(str(DST))
MM, mm = pcbnew.FromMM, pcbnew.ToMM


def V(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


REMOVED = []

# ------------------------------------------------------------------ 1. capacitors to 0805
plugin = pcbnew.PCB_PLUGIN()
for ref in ("C1", "C2"):
    old = board.FindFootprintByReference(ref)
    new = plugin.FootprintLoad(FP_LIB, CAP_FP)
    new.SetFPID(pcbnew.LIB_ID("Capacitor_SMD", CAP_FP))
    new.SetReference(ref)
    new.SetValue(old.GetValue())
    new.SetPath(old.GetPath())
    board.Add(new)
    if old.IsFlipped():
        new.Flip(new.GetPosition(), False)
    new.SetPosition(old.GetPosition())
    new.SetOrientation(old.GetOrientation())
    nets = {p.GetNumber(): p.GetNet() for p in old.Pads()}
    for p in new.Pads():
        p.SetNet(nets[p.GetNumber()])
    new.Reference().SetPosition(old.Reference().GetPosition())
    new.Reference().SetTextAngle(old.Reference().GetTextAngle())
    board.Remove(old)
    REMOVED.append(old)

# ------------------------------------------------------------------ 3a. A8/A11 on In1.Cu
# Upstream's A11 meander has a 0.05 mm hump at y 75.23 that comes 0.13 mm from A8 (rule 0.15 mm).
# Flatten it: one straight track replaces the five pieces. A11 gets about 0.16 mm shorter.
HUMP = [(97.0765, 75.3295), (97.0765, 75.2795), (97.1265, 75.2295), (97.5265, 75.2295), (97.5765, 75.2795),
        (97.5765, 75.3295)]


def near(p, q, tol=0.002):
    return abs(mm(p.x) - q[0]) < tol and abs(mm(p.y) - q[1]) < tol


hump = []
for t in list(board.GetTracks()):
    if t.GetClass() == "PCB_VIA" or t.GetNetname() != "/A11" or t.GetLayer() != pcbnew.In1_Cu:
        continue
    for a, b_ in zip(HUMP, HUMP[1:]):
        if near(t.GetStart(), a) and near(t.GetEnd(), b_) or near(t.GetStart(), b_) and near(t.GetEnd(), a):
            hump.append(t)
assert len(hump) == 5, f"A11 hump: found {len(hump)} of 5 pieces"
for t in hump:
    board.Remove(t)
REMOVED += hump        # keep the Python wrappers of removed items alive (pcbnew misbehaves otherwise)
tr = pcbnew.PCB_TRACK(board)
tr.SetStart(V(*HUMP[0])); tr.SetEnd(V(*HUMP[-1])); tr.SetWidth(MM(0.25)); tr.SetLayer(pcbnew.In1_Cu)
tr.SetNet(board.FindNet("/A11"))
board.Add(tr)

# ------------------------------------------------------------------ 3b. dangling stubs
# Upstream leaves four short dead-end pieces (D1, DTACK, BG, BERR). Every net is complete without them.
STUBS = [("/D1", pcbnew.F_Cu, 170.0098, 81.0260, 0.6592), ("/DTACK", pcbnew.F_Cu, 162.0520, 52.7070, 1.1450),
         ("/BG", pcbnew.In1_Cu, 161.8705, 56.0615, 0.2822), ("/BERR", pcbnew.B_Cu, 130.4475, 80.3725, 0.2057)]
stubs = []
for net, layer, x, y, length in STUBS:
    hits = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetNetname() == net
            and t.GetLayer() == layer and abs(mm(t.GetLength()) - length) < 0.001
            and (near(t.GetStart(), (x, y), 0.001) or near(t.GetEnd(), (x, y), 0.001))]
    assert len(hits) == 1, f"stub {net}: {len(hits)} matches"
    stubs += hits
for t in stubs:
    board.Remove(t)
REMOVED += stubs

# ------------------------------------------------------------------ outline of the board, keep-outs
_ps = pcbnew.SHAPE_POLY_SET()
board.GetBoardPolygonOutlines(_ps)
_o = _ps.Outline(0)
OUTLINE = Polygon([(mm(_o.CPoint(i).x), mm(_o.CPoint(i).y)) for i in range(_o.PointCount())])
for h in range(_ps.HoleCount(0)):
    _h = _ps.Hole(0, h)
    OUTLINE = OUTLINE.difference(Polygon([(mm(_h.CPoint(i).x), mm(_h.CPoint(i).y)) for i in range(_h.PointCount())]))
SILK_IN = OUTLINE.buffer(-0.3)


def pad_poly(pad, layer):
    ps = pcbnew.SHAPE_POLY_SET()
    pad.TransformShapeToPolygon(ps, layer, 0, MM(0.005))
    o = ps.Outline(0)
    return Polygon([(mm(o.CPoint(i).x), mm(o.CPoint(i).y)) for i in range(o.PointCount())])


def keepouts(silk, mask):
    k = [pad_poly(p, mask).buffer(0.15) for f in board.GetFootprints() for p in f.Pads() if p.IsOnLayer(mask)]
    for d in board.GetDrawings():
        if d.GetClass() == "PCB_TEXT" and d.GetLayer() == silk:
            bb = d.GetBoundingBox()
            k.append(box(mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())).buffer(0.15))
    return unary_union(k)


def poly(shape, layer):
    for g in getattr(shape, "geoms", [shape]):
        if g.is_empty or g.area < 0.005:
            continue
        assert not g.interiors, "silkscreen piece with a hole"
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_POLY)
        s.SetPolyPoints([V(x, y) for x, y in list(g.exterior.coords)[:-1]])
        s.SetFilled(True); s.SetWidth(0); s.SetLayer(layer)
        board.Add(s)


def text(t, at, layer, size=1.0, thick=0.15, mirror=False, angle=0):
    x = pcbnew.PCB_TEXT(board)
    x.SetText(t); x.SetPosition(V(*at)); x.SetLayer(layer)
    x.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size))); x.SetTextThickness(MM(thick))
    x.SetMirrored(mirror)
    x.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    x.SetTextAngleDegrees(angle)
    board.Add(x)
    return x


# ------------------------------------------------------------------ 2. CPU outlines and notches
F, B = pcbnew.F_SilkS, pcbnew.B_SilkS
for ref in ("U1", "U2"):                     # upstream's thin outlines and row boxes
    fp = board.FindFootprintByReference(ref)
    old_silk = [it for it in fp.GraphicalItems() if it.GetClass() == "MGRAPHIC" and it.GetLayer() in (F, B)]
    for it in old_silk:
        fp.Remove(it)
    REMOVED.extend(old_silk)

W, R_NOTCH = 0.2, 1.5                        # outline width, notch radius (mm)
U1 = board.FindFootprintByReference("U1")    # pins into the motherboard's CPU socket (original position)
U2 = board.FindFootprintByReference("U2")    # the relocated CPU socket
p1o, p1r = U1.FindPadByNumber("1").GetPosition(), U2.FindPadByNumber("1").GetPosition()
# Original position: rows x 92.202 / 115.062, pins y 61.214 .. 139.954, pin 1 at the bottom right.
ORIG = (mm(p1o.x) - 22.86 - 1.5, 59.8, mm(p1o.x) + 1.5, mm(p1o.y) + 1.35)
# Relocated: rows y 49.784 / 72.644, pins x 106.172 .. 184.912, pin 1 at the top right.
RELO = (mm(p1r.x) - 78.74 - 1.1, mm(p1r.y) - 1.5, mm(p1r.x) + 1.1, mm(p1r.y) + 22.86 + 1.5)


def ring(r):
    x0, y0, x1, y1 = r
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    return unary_union([LineString([a, b_]).buffer(W / 2, cap_style=3, join_style=2) for a, b_ in zip(pts, pts[1:])])


def half_disc(c, toward):
    """Filled half disc on the outline's end at c, bulging toward the inside (unit vector)."""
    disc = Point(c).buffer(R_NOTCH, 64)
    tx, ty = toward
    half = box(c[0] + min(0, tx) * R_NOTCH - (R_NOTCH if tx == 0 else 0), c[1] + min(0, ty) * R_NOTCH - (R_NOTCH if ty == 0 else 0),
               c[0] + max(0, tx) * R_NOTCH + (R_NOTCH if tx == 0 else 0), c[1] + max(0, ty) * R_NOTCH + (R_NOTCH if ty == 0 else 0))
    return disc.intersection(half)


orig_notch = half_disc(((ORIG[0] + ORIG[2]) / 2, ORIG[3]), (0, -1))
relo_notch = half_disc((RELO[2], (RELO[1] + RELO[3]) / 2), (-1, 0))
relo_area = box(*RELO).buffer(0.5, join_style=2)

KF, KB = keepouts(F, pcbnew.F_Mask), keepouts(B, pcbnew.B_Mask)
top = unary_union([ring(RELO), relo_notch, ring(ORIG).difference(relo_area), orig_notch])
bot = unary_union([ring(ORIG), orig_notch])
poly(top.difference(KF).intersection(SILK_IN), F)
poly(bot.difference(KB).intersection(SILK_IN), B)
for name, notch, k in (("original", orig_notch, KF), ("original (underside)", orig_notch, KB), ("relocated", relo_notch, KF)):
    assert notch.difference(k).area > 0.95 * notch.area, f"{name} notch is clipped"

# ------------------------------------------------------------------ 4. CopperList branding (underside)
# In the arm to the right of the original position (x 117 .. 129, y 100 .. 133): nothing on B.Cu there.
# Read from below with the arm upright, the text runs bottom to top, like LinuxJedi's line on the top.
LOGO = (CPU01 / "assets" / "logo_seattle_web.txt").read_text().strip()


def rings_of(d):
    out = []
    for sp in re.findall(r"M[^M]*", d):
        n = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", sp)]
        out.append(list(zip(n[0::2], n[1::2])))
    return out


def split3(d):
    mark, url = [], []
    for sp in re.findall(r"M[^M]*", d):
        ys = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", sp)][1::2]
        if max(ys) <= 4.5:
            mark.append(sp)
        elif min(ys) >= 14:
            url.append(sp)
    return "".join(mark), "".join(url)


def winding(pt, rs):
    x, y = pt
    w = 0
    for r in rs:
        for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]):
            if y0 <= y < y1 and (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0) > 0:
                w += 1
            elif y1 <= y < y0 and (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0) < 0:
                w -= 1
    return w


def raster_rects(rs, step=0.5):
    """The pixel-grid wordmark as merged rectangles (same method as VID-01, SER-01 and ATK-01)."""
    us = [p[0] for r in rs for p in r]
    vs = [p[1] for r in rs for p in r]
    u0, u1 = step * int(min(us) // step) - step, max(us) + step
    v0, v1 = step * int(min(vs) // step) - step, max(vs) + step
    nu, nv = int((u1 - u0) / step) + 1, int((v1 - v0) / step) + 1
    runs_by_row = []
    for j in range(nv):
        vc = v0 + (j + 0.5) * step
        row, start = [], None
        for i in range(nu + 1):
            filled = i < nu and winding((u0 + (i + 0.5) * step, vc), rs) != 0
            if filled and start is None:
                start = i
            if not filled and start is not None:
                row.append((start, i)); start = None
        runs_by_row.append(row)
    rects, open_ = [], {}
    for j, row in enumerate(runs_by_row + [[]]):
        nxt = {}
        for run in row:
            nxt[run] = open_.pop(run, j)
        for run, jstart in open_.items():
            rects.append((u0 + run[0] * step, u0 + run[1] * step, v0 + jstart * step, v0 + j * step))
        open_ = nxt
    return rects


MARK, URL = split3(LOGO)
CY = 116.5                                    # middle of the free stretch of the arm
K = 22.0 / 79.0                               # wordmark 22 mm long
KU = 0.22                                     # URL scale
X_MARK = 128.3                                # board x of the wordmark's top line (v = -12)
X_URL = X_MARK - 16 * K - 0.7                 # board x of the URL's top (v = 15)


def mark_xy(u, v):                            # logo units -> board mm (mirrored, rotated to read upward)
    return X_MARK - K * (v + 12), CY - K * (u - 39.5)


def url_xy(u, v):
    return X_URL - KU * (v - 15), CY - KU * (u - 28.0)


def to_boxes(rects, f):
    out = []
    for ua, ub, va, vb in rects:
        (xa, ya), (xb, yb) = f(ua, va), f(ub, vb)
        out.append((min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb)))
    return out


MARK_RECTS = to_boxes(raster_rects(rings_of(MARK)), mark_xy)
LOGO_SHAPE = unary_union([box(a, c, b_, d) for a, b_, c, d in MARK_RECTS])
# The wordmark: one footprint (LOGO1, kept in the project library) whose custom pads are the letters on B.Cu,
# each filled solid, so the counters of o, p, e have copper under the mask and match the pour around them.
# The solder-mask openings (board graphics on B.Mask) are the letters only, so just the letters come out bare
# (silver with HASL). Letters that touch share a pad.
LC = LOGO_SHAPE.centroid
logo_fp = pcbnew.FOOTPRINT(board)
logo_fp.SetFPID(pcbnew.LIB_ID("Open68000Relocator", "CopperList_Wordmark_CPU01"))
logo_fp.SetReference("LOGO1"); logo_fp.SetValue("CopperList wordmark")
logo_fp.SetAttributes(pcbnew.FP_EXCLUDE_FROM_POS_FILES | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_BOARD_ONLY)
logo_fp.Reference().SetVisible(False); logo_fp.Value().SetVisible(False)
logo_fp.Reference().SetLayer(pcbnew.B_Fab); logo_fp.Value().SetLayer(pcbnew.B_Fab)
_lset = pcbnew.LSET(); _lset.AddLayer(pcbnew.B_Cu)
_groups = LOGO_SHAPE.buffer(0.01, join_style=2)
for comp in getattr(_groups, "geoms", [_groups]):
    solid = Polygon(comp.exterior)               # the letter(s), 0.01 mm grown, with counters filled in
    c = solid.representative_point()
    pad = pcbnew.PAD(logo_fp)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    pad.SetAnchorPadShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetSize(pcbnew.VECTOR2I(MM(0.05), MM(0.05)))
    pad.SetLayerSet(_lset)
    pad.SetNumber("")
    pad.SetPos0(V(c.x - LC.x, c.y - LC.y))
    pad.SetPosition(V(c.x - LC.x, c.y - LC.y))
    logo_fp.Add(pad)
    pts = pcbnew.VECTOR_VECTOR2I()
    for x, y in list(solid.exterior.coords)[:-1]:
        pts.append(V(x - c.x, y - c.y))
    pad.AddPrimitivePoly(pts, 0, True)
for x0, x1, y0, y1 in MARK_RECTS:              # mask openings: the letters only
    poly(box(x0, y0, x1, y1), pcbnew.B_Mask)
LOGO_LIB_COPY = pcbnew.FOOTPRINT(logo_fp)    # at the origin, for the project library
board.Add(logo_fp)
logo_fp.SetPosition(V(LC.x, LC.y))

url_boxes = [box(a, c, b_, d) for a, b_, c, d in to_boxes(raster_rects(rings_of(URL)), url_xy)]
for bx in url_boxes:                          # one filled rectangle each (merged shapes would have holes)
    poly(bx, B)
url_shape = unary_union(url_boxes)

X_PROD = X_URL - 8 * KU - 1.15
X_LIC = X_PROD - 1.55
t_prod = text(f"{PRODUCT} v{REV}  68000 CPU relocator", (X_PROD, CY), B, size=0.9, thick=0.15, mirror=True, angle=270)
t_lic = text("License: GPL-3.0", (X_LIC, CY), B, size=0.8, thick=0.15, mirror=True, angle=270)

# everything in the branding block must be on the board, clear of underside copper and the outline
brand = [LOGO_SHAPE, url_shape]
for t in (t_prod, t_lic):
    bb = t.GetBoundingBox()
    brand.append(box(mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())))
BRAND = unary_union(brand)
assert SILK_IN.buffer(-0.5).contains(BRAND), f"branding off the board: {BRAND.bounds}"
assert not BRAND.intersects(box(*ORIG).buffer(0.6)), "branding touches the CPU outline"
for t in board.GetTracks():
    if t.IsOnLayer(pcbnew.B_Cu):
        seg = Point(mm(t.GetPosition().x), mm(t.GetPosition().y)) if t.GetClass() == "PCB_VIA" else \
            LineString([(mm(t.GetStart().x), mm(t.GetStart().y)), (mm(t.GetEnd().x), mm(t.GetEnd().y))])
        assert seg.distance(BRAND) > 0.5, f"branding over a {t.GetNetname()} track"
for f in board.GetFootprints():
    if f.GetReference() == "LOGO1":
        continue
    for p in f.Pads():
        if p.IsOnLayer(pcbnew.B_Cu):
            assert pad_poly(p, pcbnew.B_Cu).distance(BRAND) > 0.5, f"branding over {f.GetReference()} pad"

# ------------------------------------------------------------------ zones, save
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.Save(str(DST))

# keep the project's footprint library in step with the board (U1, U2 without the old silkscreen)
LIB = str(REPO / "Open68000Relocator.pretty")
for ref, name in (("U1", "DIP-64_W22.86mm_Socket_LongPads_Socket"), ("U2", "DIP-64_W22.86mm_Socket_LongPads_IC")):
    fp = pcbnew.FOOTPRINT(board.FindFootprintByReference(ref))
    fp.SetParent(None)
    fp.SetOrientationDegrees(0)
    fp.SetPosition(V(0, 0))
    fp.SetFPID(pcbnew.LIB_ID("", name))
    plugin.FootprintSave(LIB, fp)
LOGO_LIB_COPY.SetParent(None)
plugin.FootprintSave(LIB, LOGO_LIB_COPY)
# KiCad's DRC window: the U1/U2 courtyard overlap is the design, so mark it as an exclusion
import json
PRO = REPO / "68000Relocator.kicad_pro"
pro = json.loads(PRO.read_text())
u1, u2 = (board.FindFootprintByReference(r).m_Uuid.AsString() for r in ("U1", "U2"))
pro["board"]["design_settings"]["drc_exclusions"] = [f"courtyards_overlap|{p1o.x}|{p1o.y}|{u1}|{u2}"]
PRO.write_text(json.dumps(pro, indent=2) + "\n")
print(f"{PRODUCT} v{REV} board written to {DST}")
