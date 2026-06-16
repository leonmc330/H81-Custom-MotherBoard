"""Shared utilities for the Mobo reforming pipeline.

Imported by pintokicad.py, pintokicad_sch.py, and gen_footprints.py.
"""
import csv
import math
import re
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Tuple

# ── coordinate constants ─────────────────────────────────────────────────────

PIN_SCALE = 2.54 * 0.0001   # TVW file units → mm  (1 unit ≈ 0.000325 mm)
FLIP_X    = True             # both flips together = orientation-preserving
FLIP_Y    = True

# ── CSV readers ──────────────────────────────────────────────────────────────

PinList = List[Tuple[str, float, float, str]]   # (pin, x, y, net)

def read_pins(path: str) -> Dict[str, PinList]:
    """Read pins.csv → {refdes: [(pin, x, y, net), ...]}. Duplicates dropped."""
    pins: Dict[str, PinList] = defaultdict(list)
    seen: set = set()
    with open(path, newline='', encoding='utf-8', errors='replace') as f:
        for row in csv.reader(f):
            if len(row) != 5 or row[0].lower() == 'refdes':
                continue
            refdes, pin, x, y, net = row
            k = (refdes, pin)
            if k in seen:
                continue
            seen.add(k)
            try:
                pins[refdes].append((pin.strip(), float(x), float(y), net.strip()))
            except ValueError:
                pass
    return dict(pins)


CompInfo = Dict[str, object]   # keys: device, x, y, sx, sy, rotation

def read_components(path: str) -> Dict[str, CompInfo]:
    """Read components.csv → {refdes: {device, x, y, sx, sy, rotation}}.

    Device names may contain commas, so fields are parsed from the RIGHT:
    last 4 numeric fields = x, y, sx, sy; if the 5th-from-right is also
    numeric it is the rotation angle.
    """
    components: Dict[str, CompInfo] = {}
    with open(path, newline='', encoding='utf-8', errors='replace') as f:
        for row in csv.reader(f):
            if len(row) < 6 or row[0].lower() == 'refdes':
                continue
            rotation = 0.0
            tail = 4
            try:
                rotation = float(row[-1])
                sy = float(row[-2]); sx = float(row[-3])
                y  = float(row[-4]); x  = float(row[-5])
                tail = 5
            except (ValueError, IndexError):
                try:
                    sy = float(row[-1]); sx = float(row[-2])
                    y  = float(row[-3]); x  = float(row[-4])
                except (ValueError, IndexError):
                    continue
            refdes = row[0]
            device = ','.join(row[1:-tail])
            components[refdes] = dict(
                device=device, x=x, y=y, sx=sx, sy=sy, rotation=rotation
            )
    return components

# ── board-level coordinate transform ─────────────────────────────────────────

def make_board_transform(
    pins: Dict[str, PinList]
) -> Tuple[Callable[[float, float], Tuple[float, float]], float, float]:
    """Compute board centre from all pin positions.

    Returns (transform, center_x_tvw, center_y_tvw).
    transform(x, y) converts TVW file units → mm, centred and flipped.
    """
    all_x = [x for plist in pins.values() for _, x, _, _ in plist]
    all_y = [y for plist in pins.values() for _, _, y, _ in plist]
    if not all_x:
        return lambda x, y: (0.0, 0.0), 0.0, 0.0
    cx = (min(all_x) + max(all_x)) / 2.0
    cy = (min(all_y) + max(all_y)) / 2.0

    def transform(x: float, y: float) -> Tuple[float, float]:
        tx = (x - cx) * PIN_SCALE
        ty = (y - cy) * PIN_SCALE
        if FLIP_X: tx = -tx
        if FLIP_Y: ty = -ty
        return tx, ty

    return transform, cx, cy


def fp_local_coords(
    pin_x: float, pin_y: float,
    chip_x: float, chip_y: float,
    rot_deg: float
) -> Tuple[float, float]:
    """Convert world-space TVW pin position to footprint-local KiCad coords.

    The viewer exports pins in world space using standard CCW rotation:
        wx = chip_x + lx*cos(rot) - ly*sin(rot)
        wy = chip_y + lx*sin(rot) + ly*cos(rot)
    Inverting gives local coords (rotate the delta by -rot), then scale
    and apply FLIP_X / FLIP_Y identical to the board transform.
    """
    dx  = pin_x - chip_x
    dy  = pin_y - chip_y
    rot = math.radians(rot_deg)
    lx  =  dx * math.cos(rot) + dy * math.sin(rot)
    ly  = -dx * math.sin(rot) + dy * math.cos(rot)
    lx *= PIN_SCALE
    ly *= PIN_SCALE
    if FLIP_X: lx = -lx
    if FLIP_Y: ly = -ly
    return round(lx, 4), round(ly, 4)

# ── KiCad string helpers ─────────────────────────────────────────────────────

def qesc(s: str) -> str:
    """Wrap s in KiCad double-quotes, escaping backslash and quote."""
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def safe_fp_name(device: str) -> str:
    """Sanitise a device name for use as a footprint name / filename."""
    s = re.sub(r'[^\w.\-]', '_', device)
    s = re.sub(r'_+', '_', s).strip('_')
    return s[:96]


_uid_counter = 0

def uid() -> str:
    """Return a deterministic pseudo-UUID suitable for KiCad schematic UUIDs."""
    global _uid_counter
    _uid_counter += 1
    n = _uid_counter
    return f"{n:08x}-0000-0000-0000-{n:012x}"

# ── MST trace generation ─────────────────────────────────────────────────────

Point2D = Tuple[float, float]

def mst_edges(points: List[Point2D]) -> List[Tuple[int, int]]:
    """Kruskal MST over (x, y) points using squared-Euclidean edge weights.

    Returns a list of (i, j) index pairs into `points` — exactly n-1 edges
    for n points.  O(n² log n) time; fast enough for typical net sizes.
    """
    n = len(points)
    if n < 2:
        return []

    edges = sorted(
        (
            (points[i][0] - points[j][0]) ** 2 +
            (points[i][1] - points[j][1]) ** 2,
            i, j
        )
        for i in range(n)
        for j in range(i + 1, n)
    )

    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    result: List[Tuple[int, int]] = []
    target = n - 1
    for _, i, j in edges:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
            result.append((i, j))
            if len(result) == target:
                break
    return result
