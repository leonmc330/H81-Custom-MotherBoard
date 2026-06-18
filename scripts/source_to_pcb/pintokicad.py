import csv
import fnmatch
import hashlib
import os
import re
from collections import defaultdict, Counter, OrderedDict

# =========================
# CONFIG
# =========================

_SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
SRC_DIR         = os.path.normpath(os.path.join(_SCRIPT_DIR, '..', '..', 'src'))

PINS_FILE       = os.path.join(SRC_DIR, "pins.csv")
COMP_FILE       = os.path.join(SRC_DIR, "components.csv")
OUTPUT_FILE     = os.path.join(SRC_DIR, "H81-Custom-MotherBoard.kicad_pcb")
PININFO_FILE    = os.path.join(SRC_DIR, "pininfo.txt")

PIN_SCALE       = 2.54 * 0.0001   # micrometers → mm
FLIP_X          = True
FLIP_Y          = True

PAD_SIZE_DEFAULT  = 0.1
DRILL_SIZE_DEFAULT = 0.1

FP_LIBRARY        = "footprint"

GRID_MM         = 0.5
COPPER_LAYERS   = 4

# =========================
# NETS
# =========================

net_ids     = OrderedDict()
net_counter = 1

def get_net_id(net):
    global net_counter
    if net not in net_ids:
        net_ids[net] = net_counter
        net_counter += 1
    return net_ids[net]

def safe_fp_name(device):
    s = re.sub(r'[^\w.\-]', '_', device)
    s = re.sub(r'_+', '_', s).strip('_')
    return s[:96]

def normalize_refdes(ref):
    if not ref or ref[-1].isdigit():
        return ref
    return ref + '1'

def component_uid(refdes):
    h = hashlib.md5(f"mobo:{refdes}".encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"

# =========================
# READ PINS
# =========================

print(f"Reading pins from {PINS_FILE} ...")

pins = defaultdict(list)
seen_pins = set()
pins_raw_rows = 0
pins_skipped_malformed = 0
pins_skipped_duplicate = 0

with open(PINS_FILE, newline="") as f:
    for row in csv.reader(f):
        if len(row) != 5:
            if row and row[0].lower() != "refdes":
                pins_skipped_malformed += 1
            continue
        refdes, pin, x, y, net = row
        if refdes.lower() == "refdes":
            continue
        refdes = normalize_refdes(refdes)
        pins_raw_rows += 1
        key = (refdes, pin)
        if key in seen_pins:
            pins_skipped_duplicate += 1
            continue
        seen_pins.add(key)
        pins[refdes].append((pin, float(x), float(y), net))

total_pins = sum(len(p) for p in pins.values())
print(f"  {pins_raw_rows} data rows  ->  {len(pins)} components, {total_pins} unique pins")
if pins_skipped_duplicate:
    print(f"  WARNING: {pins_skipped_duplicate} duplicate (refdes,pin) pairs skipped")
if pins_skipped_malformed:
    print(f"  WARNING: {pins_skipped_malformed} malformed rows skipped (wrong column count)")

# Pin-count distribution
pin_counts = Counter(len(p) for p in pins.values())
print(f"  Pin count distribution: " + "  ".join(
    f"{n}pin×{c}" for n, c in sorted(pin_counts.items())))

# =========================
# READ COMPONENTS
# =========================

print(f"\nReading components from {COMP_FILE} ...")

components = {}
comps_raw_rows = 0
comps_skipped = 0
comps_with_rotation = 0
rotation_dist = Counter()

with open(COMP_FILE, newline="") as f:
    for row in csv.reader(f):
        if len(row) < 6:
            continue
        if row[0].lower() == "refdes":
            continue
        comps_raw_rows += 1
        # New format (viewer with rotation column):
        #   refdes, [device…], x, y, sizex, sizey, rotation   (7+ CSV columns)
        # Old format (no rotation column):
        #   refdes, [device…], x, y, sizex, sizey              (6+ CSV columns)
        # Device name may contain commas → parse from the RIGHT.
        # Try 5 numeric tail first (new); fall back to 4 (old).
        rotation = 0.0
        tail = 4
        try:
            rotation = float(row[-1])
            sy       = float(row[-2])
            sx       = float(row[-3])
            y        = float(row[-4])
            x        = float(row[-5])
            tail = 5
        except (ValueError, IndexError):
            try:
                sy = float(row[-1])
                sx = float(row[-2])
                y  = float(row[-3])
                x  = float(row[-4])
            except (ValueError, IndexError):
                comps_skipped += 1
                continue
        refdes = normalize_refdes(row[0])
        device = ",".join(row[1:-tail])
        components[refdes] = {
            "device": device,
            "x": x,
            "y": y,
            "sx": sx,
            "sy": sy,
            "rotation": rotation,
        }
        if rotation != 0.0:
            comps_with_rotation += 1
        rotation_dist[int(rotation) % 360] += 1

print(f"  {comps_raw_rows} data rows  ->  {len(components)} components loaded")
if comps_skipped:
    print(f"  WARNING: {comps_skipped} rows skipped (could not parse numeric fields)")
print(f"  Rotation distribution: " + "  ".join(
    f"{r}°×{c}" for r, c in sorted(rotation_dist.items())))

# Cross-reference pins ↔ components
pins_only  = sorted(set(pins.keys()) - set(components.keys()))
comps_only = sorted(set(components.keys()) - set(pins.keys()))
in_both    = set(pins.keys()) & set(components.keys())
print(f"  Matched: {len(in_both)} have both pins+outline")
if pins_only:
    print(f"  WARNING: {len(pins_only)} refdes in pins but missing from components "
          f"(no outline): {', '.join(pins_only[:10])}"
          + (" ..." if len(pins_only) > 10 else ""))
if comps_only:
    print(f"  INFO: {len(comps_only)} refdes in components but have no pins "
          f"(not exported?): {', '.join(comps_only[:10])}"
          + (" ..." if len(comps_only) > 10 else ""))

# =========================
# BOUNDING BOX + CENTER
# =========================

all_x = [x for plist in pins.values() for _, x, _, _ in plist]
all_y = [y for plist in pins.values() for _, _, y, _ in plist]

if all_x:
    center_x = (min(all_x) + max(all_x)) / 2.0
    center_y = (min(all_y) + max(all_y)) / 2.0
    board_w = (max(all_x) - min(all_x)) * PIN_SCALE
    board_h = (max(all_y) - min(all_y)) * PIN_SCALE
    print(f"\nBoard extents: {board_w:.1f} × {board_h:.1f} mm  "
          f"(center at {center_x:.0f}, {center_y:.0f} TVW units)")
else:
    center_x = center_y = 0.0
    print("\nWARNING: no pin data — board extents unknown")

# =========================
# COORDINATE TRANSFORM
# =========================

def transform(x, y):
    x = (x - center_x) * PIN_SCALE
    y = (y - center_y) * PIN_SCALE
    if FLIP_X: x = -x
    if FLIP_Y: y = -y
    return x, y

# =========================
# PIN INFO RULES
# =========================

pininfo_rules = []

def load_pininfo():
    global pininfo_rules
    try:
        with open(PININFO_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 3:
                    continue
                try:
                    pininfo_rules.append((parts[0], float(parts[1]), float(parts[2])))
                except ValueError:
                    continue
        print(f"\nLoaded {len(pininfo_rules)} pad-size rules from {PININFO_FILE}")
    except FileNotFoundError:
        print(f"\nINFO: {PININFO_FILE} not found — using default pad size {PAD_SIZE_DEFAULT} mm for all pads")

def find_pad_info(name):
    for pattern, pad_size, drill in pininfo_rules:
        if fnmatch.fnmatch(name, pattern):
            return pad_size, drill
    return PAD_SIZE_DEFAULT, DRILL_SIZE_DEFAULT

load_pininfo()

# =========================
# BUILDERS
# =========================

def build_pad(name, x, y, net):
    pad_size, _ = find_pad_info(name)
    net_id = get_net_id(net)
    return (
        f'    (pad "{name}" smd circle\n'
        f'      (at {x:.3f} {y:.3f})\n'
        f'      (size {pad_size:.3f} {pad_size:.3f})\n'
        f'      (layers "F.Cu" "F.Mask")\n'
        f'      (net {net_id} "{net}")\n'
        f'    )\n'
    )

def build_outline(sx, sy):
    hx, hy = sx / 2.0, sy / 2.0
    lines = [
        f'    (fp_line (start {-hx:.3f} {-hy:.3f}) (end {hx:.3f} {-hy:.3f}) (layer "F.CrtYd") (width 0.05))',
        f'    (fp_line (start {hx:.3f} {-hy:.3f}) (end {hx:.3f} {hy:.3f}) (layer "F.CrtYd") (width 0.05))',
        f'    (fp_line (start {hx:.3f} {hy:.3f}) (end {-hx:.3f} {hy:.3f}) (layer "F.CrtYd") (width 0.05))',
        f'    (fp_line (start {-hx:.3f} {hy:.3f}) (end {-hx:.3f} {-hy:.3f}) (layer "F.CrtYd") (width 0.05))',
    ]
    return "\n".join(lines) + "\n"

def build_footprint(refdes, device, at_x, at_y, pads_str, outline_str=""):
    fp_id = f"{FP_LIBRARY}:{safe_fp_name(device)}"
    sym_uid = component_uid(refdes)
    return (
        f'  (footprint "{fp_id}" (layer "F.Cu")\n'
        f'    (tstamp "{sym_uid}")\n'
        f'    (at {at_x:.3f} {at_y:.3f})\n'
        f'    (path "/{sym_uid}")\n'
        f'    (property "Reference" "{refdes}")\n'
        f'    (property "Value" "{device}")\n'
        f'{outline_str}'
        f'{pads_str}'
        f'  )\n'
    )

def build_layers(n_copper):
    lines = ["  (layers"]
    lines.append('    (0 "F.Cu" signal)')
    for i in range(1, n_copper - 1):
        lines.append(f'    ({i} "In{i}.Cu" signal)')
    lines.append('    (31 "B.Cu" signal)')
    lines += [
        '    (32 "B.Adhes" user "B.Adhesive")',
        '    (33 "F.Adhes" user "F.Adhesive")',
        '    (34 "B.Paste" user)',
        '    (35 "F.Paste" user)',
        '    (36 "B.SilkS" user "B.Silkscreen")',
        '    (37 "F.SilkS" user "F.Silkscreen")',
        '    (38 "B.Mask" user)',
        '    (39 "F.Mask" user)',
        '    (44 "Edge.Cuts" user)',
        '    (47 "F.CrtYd" user "F.Courtyard")',
        '    (46 "B.CrtYd" user "B.Courtyard")',
        '    (49 "F.Fab" user)',
        '    (48 "B.Fab" user)',
    ]
    lines.append("  )")
    return "\n".join(lines) + "\n"

# =========================
# PASS 1 — PIN FOOTPRINTS (pads only, no outlines)
# Positioned at the centroid of the component's own pins.
# =========================

print(f"\nPass 1: building pin footprints (with courtyard where available) ...")

footprint_blocks = ""
n_without_outline = 0
total_pads_written = 0
nets_per_comp = []
largest_comps = []
pin_centroids = {}  # refdes → (at_x, at_y) in mm — reused by pass 2 for logging

for refdes, plist in pins.items():
    xs = [x for _, x, _, _ in plist]
    ys = [y for _, _, y, _ in plist]
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    at_x, at_y = transform(cx, cy)
    pin_centroids[refdes] = (at_x, at_y)

    pads_str = ""
    comp_nets = set()
    for pin, x, y, net in plist:
        px, py = transform(x, y)
        px -= at_x
        py -= at_y
        pads_str += build_pad(pin, px, py, net)
        comp_nets.add(net)
        total_pads_written += 1
    nets_per_comp.append(len(comp_nets))
    largest_comps.append((len(plist), refdes))

    device = components[refdes]["device"] if refdes in components else refdes
    # Embed courtyard outline directly in the pin footprint if outline data exists.
    # This avoids creating a separate _box footprint (which has no pads and confuses
    # KiCad's inspector with "zero connections").
    outline_str = ""
    if refdes in components:
        comp = components[refdes]
        rot  = comp["rotation"]
        sx   = comp["sx"] * PIN_SCALE
        sy   = comp["sy"] * PIN_SCALE
        if rot % 180 != 0:
            sx, sy = sy, sx
        outline_str = build_outline(sx, sy)
    else:
        n_without_outline += 1
    footprint_blocks += build_footprint(refdes, device, at_x, at_y, pads_str, outline_str)

print(f"  {len(pins)} pin footprints, {total_pads_written} pads total")

# =========================
# PASS 2 — OUTLINE FOOTPRINTS (courtyard only, no pads)
# Positioned at the component's anchor from components.csv, NOT the pin centroid.
# sizex/sizey are component-local — swap for 90°/270° to match world orientation.
# =========================

print(f"Pass 2: skipped — courtyard outlines are now embedded in pass-1 pin footprints")

# =========================
# WRITE PCB
# =========================

print(f"Writing {OUTPUT_FILE} ...")

with open(OUTPUT_FILE, "w") as f:
    f.write("(kicad_pcb (version 20211014) (generator python)\n")
    f.write(build_layers(COPPER_LAYERS))

    f.write('  (net 0 "")\n')
    for net, nid in net_ids.items():
        f.write(f'  (net {nid} "{net}")\n')

    f.write(f'\n  (general (grid mm {GRID_MM}))\n  (paper A4)\n\n')
    f.write(footprint_blocks)
    f.write("\n)\n")

# =========================
# SUMMARY
# =========================

largest_comps.sort(reverse=True)

print()
print("=" * 52)
print("  SUMMARY")
print("=" * 52)
print(f"  Pin footprints     : {len(pins)}  (courtyard embedded where available)")
print(f"  Total pads         : {total_pads_written}")
print(f"  Total nets         : {len(net_ids)}")
print(f"  No outline data    : {n_without_outline}  (not in components.csv)")
if nets_per_comp:
    print(f"  Nets/comp (avg)    : {sum(nets_per_comp)/len(nets_per_comp):.1f}  "
          f"max={max(nets_per_comp)}  min={min(nets_per_comp)}")
print(f"  Output             : {OUTPUT_FILE}")
print("=" * 52)
print(f"  Top 10 by pin count:")
for n_pins, ref in largest_comps[:10]:
    dev = components[ref]["device"] if ref in components else "—"
    print(f"    {ref:<12} {n_pins:>4} pins   {dev[:35]}")
print("=" * 52)
