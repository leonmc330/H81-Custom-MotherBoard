import csv
import math
import os
import re
from collections import defaultdict

# =========================
# CONFIG
# =========================

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MOBO_DIR    = os.path.normpath(os.path.join(_SCRIPT_DIR, '..', '..'))
SRC_DIR     = os.path.join(MOBO_DIR, 'src')

PINS_FILE   = os.path.join(SRC_DIR, "pins.csv")
COMP_FILE   = os.path.join(SRC_DIR, "components.csv")
OUTPUT_DIR  = os.path.join(MOBO_DIR, "footprint.pretty")

PIN_SCALE   = 2.54 * 0.0001   # TVW units → mm (same as pintokicad.py)
FLIP_X      = True
FLIP_Y      = True

PAD_SIZE    = 0.3              # smd pad diameter (mm)
CYD_W       = 0.05             # courtyard line width (mm)

# =========================
# HELPERS
# =========================

def qesc(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

def safe_fp_name(device):
    """Sanitise device name for use as footprint name and filename."""
    s = re.sub(r'[^\w.\-]', '_', device)
    s = re.sub(r'_+', '_', s).strip('_')
    return s[:96]          # leave room for the .kicad_mod extension

def world_to_fp_local(pin_x, pin_y, chip_x, chip_y, rot_deg):
    """
    Convert world-space TVW pin position to footprint-local KiCad coordinates.

    The viewer exports pins in world space using the standard 2-D CCW rotation:
        wx = chip_x + lx*cos(rot) - ly*sin(rot)
        wy = chip_y + lx*sin(rot) + ly*cos(rot)

    Inverting gives local coords (rotate the delta by -rot), then we scale and
    apply the same FLIP_X / FLIP_Y convention as pintokicad.py.
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

# =========================
# READ PINS
# =========================

print(f"Reading {PINS_FILE} ...")
pins = defaultdict(list)
seen = set()
with open(PINS_FILE, newline='', encoding='utf-8', errors='replace') as f:
    for row in csv.reader(f):
        if len(row) != 5 or row[0].lower() == 'refdes':
            continue
        ref, pin, x, y, net = row
        k = (ref, pin)
        if k not in seen:
            seen.add(k)
            pins[ref].append((pin.strip(), float(x), float(y)))

total_pins = sum(len(p) for p in pins.values())
print(f"  {len(pins)} components, {total_pins} unique pins")

# =========================
# READ COMPONENTS
# =========================

print(f"Reading {COMP_FILE} ...")
components = {}
with open(COMP_FILE, newline='', encoding='utf-8', errors='replace') as f:
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
        ref    = row[0]
        device = ','.join(row[1:-tail])
        components[ref] = dict(device=device, x=x, y=y, sx=sx, sy=sy, rotation=rotation)

print(f"  {len(components)} component outlines")

# =========================
# DEDUPLICATE — one footprint per unique device name.
# When multiple refdes share the same device, use the one with the most pins.
# =========================

device_best = {}   # device_name → (ref, comp)
for ref, comp in components.items():
    if ref not in pins:
        continue
    dev = comp['device']
    cur = device_best.get(dev)
    if cur is None or len(pins[ref]) > len(pins[cur[0]]):
        device_best[dev] = (ref, comp)

print(f"  {len(device_best)} unique device types have pin data")

# =========================
# GENERATE .kicad_mod FILES
# =========================

os.makedirs(OUTPUT_DIR, exist_ok=True)

written    = 0
skipped    = 0
collisions = 0
used_files = set()    # sanitised filenames already written this run

for device in sorted(device_best.keys()):
    ref, comp = device_best[device]
    fp_name  = safe_fp_name(device)
    filename = fp_name + '.kicad_mod'

    if filename in used_files:
        print(f"  COLLISION: {device!r} → {filename} already written, skipping")
        collisions += 1
        continue
    used_files.add(filename)

    path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(path):
        skipped += 1
        continue

    plist   = pins[ref]
    rot_deg = comp['rotation']

    # Courtyard half-extents from component-local size (unrotated)
    hx = comp['sx'] * PIN_SCALE / 2
    hy = comp['sy'] * PIN_SCALE / 2

    lines = []
    lines.append(f'(footprint {qesc(fp_name)} (version 20211014) (generator python)')
    lines.append( '  (layer "F.Cu")')
    lines.append(f'  (fp_text reference "REF**" (at 0 {-(hy + 1.0):.3f}) (layer "F.SilkS")')
    lines.append( '    (effects (font (size 1 1) (thickness 0.15)))')
    lines.append( '  )')
    lines.append(f'  (fp_text value {qesc(fp_name)} (at 0 {hy + 1.0:.3f}) (layer "F.Fab")')
    lines.append( '    (effects (font (size 1 1) (thickness 0.15)))')
    lines.append( '  )')
    # Courtyard rectangle centred at origin, component-local dimensions
    lines.append(f'  (fp_line (start {-hx:.3f} {-hy:.3f}) (end  {hx:.3f} {-hy:.3f}) (layer "F.CrtYd") (width {CYD_W}))')
    lines.append(f'  (fp_line (start  {hx:.3f} {-hy:.3f}) (end  {hx:.3f}  {hy:.3f}) (layer "F.CrtYd") (width {CYD_W}))')
    lines.append(f'  (fp_line (start  {hx:.3f}  {hy:.3f}) (end {-hx:.3f}  {hy:.3f}) (layer "F.CrtYd") (width {CYD_W}))')
    lines.append(f'  (fp_line (start {-hx:.3f}  {hy:.3f}) (end {-hx:.3f} {-hy:.3f}) (layer "F.CrtYd") (width {CYD_W}))')
    # Pads — un-rotate world coords into footprint-local space
    for pin_name, px, py in plist:
        lx, ly = world_to_fp_local(px, py, comp['x'], comp['y'], rot_deg)
        lines.append(f'  (pad {qesc(pin_name)} smd circle'
                     f' (at {lx:.4f} {ly:.4f})'
                     f' (size {PAD_SIZE} {PAD_SIZE})'
                     f' (layers "F.Cu" "F.Mask"))')
    lines.append(')')

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    written += 1

print()
print("=" * 52)
print("  SUMMARY")
print("=" * 52)
print(f"  Footprints written   : {written}")
print(f"  Skipped (existing)   : {skipped}")
print(f"  Name collisions      : {collisions}")
print(f"  Output directory     : {OUTPUT_DIR}")
print("=" * 52)
print()
print("  Add the library to KiCad:")
print("  Preferences > Manage Footprint Libraries > Global/Project tab")
print(f'  Nickname: footprint    Path: .../footprint.pretty')
print("=" * 52)
