import math
import re
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
import lib

PINS_FILE     = "../input/pins.csv"
COMP_FILE     = "../input/components.csv"
OUTPUT_FILE   = "../kicad/output.kicad_sch"

GRID          = 2.54
FONT_SZ       = 1.27
MAX_PART_PINS = 32
SPACING       = 0.30
COL_H         = 1000.0

BODY_HW_G  = 4
PIN_INNER_G = 3
STUB_G     = 4
LABEL_W_G  = 12
MARGIN_G   = 8

BODY_HW    = round(BODY_HW_G   * GRID, 3)
PIN_INNER  = round(PIN_INNER_G * GRID, 3)
STUB_LEN   = round(STUB_G      * GRID, 3)
LABEL_W    = round(LABEL_W_G   * GRID, 3)
MARGIN     = round(MARGIN_G    * GRID, 3)

WIRE_START_X = BODY_HW
WIRE_END_X   = round((BODY_HW_G + STUB_G) * GRID, 3)

_CELL_SPAN_G = BODY_HW_G + BODY_HW_G + STUB_G + LABEL_W_G
_COL_GAP_G   = round(_CELL_SPAN_G * (1.0 + SPACING))
COL_GAP      = round(_COL_GAP_G * GRID, 3)


def sname(s):
    return re.sub(r'[^A-Za-z0-9_.\-]', '_', s)

def _row_gap(h):
    g = max(GRID, h * SPACING)
    return round(round(g / GRID) * GRID, 3)


def _load_data():
    print(f"[load] Reading {PINS_FILE} ...")
    raw  = lib.read_pins(PINS_FILE)
    pins = {ref: [(p, n) for p, _x, _y, n in plist] for ref, plist in raw.items()}
    print(f"[load]   {len(pins)} components, {sum(len(v) for v in pins.values())} unique pins")

    print(f"[load] Reading {COMP_FILE} ...")
    comp_data = lib.read_components(COMP_FILE)
    devices   = {ref: c['device'] for ref, c in comp_data.items()}
    print(f"[load]   {len(devices)} device names loaded")
    return pins, devices


def _build_draws(pins, devices):
    draws = []
    for ref in sorted(pins.keys()):
        plist   = pins[ref]
        dev     = devices.get(ref, ref)
        base    = sname(ref)
        n_parts = max(1, math.ceil(len(plist) / MAX_PART_PINS))
        for p in range(n_parts):
            chunk = plist[p * MAX_PART_PINS : (p + 1) * MAX_PART_PINS]
            key   = base + (f'_P{p + 1}' if n_parts > 1 else '')
            draws.append({'ref': ref, 'sym': base, 'key': key,
                          'unit': p + 1, 'plist': chunk, 'dev': dev, 'first': p == 0})
    draws.sort(key=lambda d: (d['ref'], d['unit']))
    return draws


def _col_layout(items, col_h, col_gap, start_cx, start_y):
    placed, columns, col_items = {}, [], []
    cx, cy = round(start_cx, 3), round(start_y, 3)
    for h, key in items:
        gap = _row_gap(h)
        if cy + h > start_y + col_h and cy > start_y:
            columns.append({'cx': cx, 'heights': list(col_items), 'used_mm': round(cy - start_y, 1)})
            cx, cy, col_items = round(cx + col_gap, 3), round(start_y, 3), []
        placed[key] = (round(cx, 3), round(cy, 3))
        col_items.append(h)
        cy = round(cy + h + gap, 3)
    if col_items:
        columns.append({'cx': cx, 'heights': list(col_items), 'used_mm': round(cy - start_y, 1)})
    return placed, columns


def _compute_layout(draws):
    items = [(round((len(d['plist']) + 1) * GRID, 3), d['key']) for d in draws]
    placed_raw, columns = _col_layout(items, COL_H, COL_GAP, 0.0, 0.0)

    xs      = [placed_raw[k][0] for _, k in items]
    ys      = [placed_raw[k][1] for _, k in items]
    heights = {k: h for h, k in items}

    shift_x = round(MARGIN - (min(xs) - BODY_HW), 3)
    shift_y = round(MARGIN - min(ys), 3)
    placed  = {k: (round(x + shift_x, 3), round(y + shift_y, 3))
               for k, (x, y) in placed_raw.items()}

    sheet_w = round((max(xs) + WIRE_END_X + LABEL_W) - (min(xs) - BODY_HW) + 2 * MARGIN, 0)
    sheet_h = round((max(ys) + max(heights.values())) - min(ys) + 2 * MARGIN, 0)

    print(f"[layout] {len(draws)} blocks -> {len(columns)} columns")
    for i, col in enumerate(columns, 1):
        pct = 100.0 * col['used_mm'] / COL_H
        print(f"[layout]   col {i:3d}: {len(col['heights']):4d} blocks  "
              f"{col['used_mm']:7.1f}/{COL_H:.0f} mm = {pct:5.1f}%")
    print(f"[layout] sheet: {sheet_w:.0f} x {sheet_h:.0f} mm")
    return placed, sheet_w, sheet_h


def _check_overlaps(draws, placed):
    boxes = []
    for d in draws:
        sx, sy = placed[d['key']]
        h = (len(d['plist']) + 1) * GRID
        boxes.append((d['key'], sx - BODY_HW, sx + BODY_HW, sy, sy + h))

    count, shown = 0, 0
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            ka, la, ra, ta, ba = boxes[i]
            kb, lb, rb, tb, bb = boxes[j]
            if la < rb and ra > lb and ta < bb and ba > tb:
                count += 1
                if shown < 10:
                    print(f"[overlap] OVERLAP: {ka} <-> {kb}  "
                          f"dx={round(min(ra,rb)-max(la,lb),2):.2f}  "
                          f"dy={round(min(ba,bb)-max(ta,tb),2):.2f}")
                    shown += 1
    if count == 0:
        print("[overlap] OK: no overlaps")
    else:
        print(f"[overlap] TOTAL: {count}")


def _generate(draws, placed, sheet_w, sheet_h):
    o = []
    o.append('(kicad_sch (version 20211123) (generator python_schematic_exporter)')
    o.append(f'  (uuid "{lib.uid()}")')
    o.append(f'  (paper "User" {sheet_w:.0f} {sheet_h:.0f})')
    o.append('')
    o.append('  (lib_symbols')

    syms = {}
    for d in draws:
        syms.setdefault(d['sym'], []).append(d)

    for sym, parts in syms.items():
        o.append(f'    (symbol {lib.qesc(sym)}')
        for unit_num, d in enumerate(parts, 1):
            n   = len(d['plist'])
            bh  = round((n + 1) * GRID, 3)
            sub = sym + f'_{unit_num}_1'
            o.append(f'      (symbol {lib.qesc(sub)}')
            # lib_symbols use Y-up; schematic renders with Y negated.
            # Negative y here cancels the flip, aligning pins with wire stubs.
            o.append(f'        (rectangle (start {-BODY_HW:.3f} 0.000) (end {BODY_HW:.3f} {-bh:.3f})')
            o.append( '          (stroke (width 0) (type default)) (fill (type background)))')
            for i, (pname, _) in enumerate(d['plist']):
                py = round((i + 1) * GRID, 3)
                o.append(f'        (pin passive line (at {BODY_HW:.3f} {-py:.3f} 180) (length {PIN_INNER:.3f})')
                o.append(f'          (name {lib.qesc(pname)} (effects (font (size {FONT_SZ} {FONT_SZ}))))')
                o.append(f'          (number {lib.qesc(pname)} (effects (font (size {FONT_SZ} {FONT_SZ}))))')
                o.append( '        )')
            o.append('      )')
        o.append('    )')

    o.append('  )')
    o.append('')

    print(f"[gen] Emitting {len(draws)} instances ...")
    for d in draws:
        sx, sy = placed[d['key']]
        n  = len(d['plist'])
        bh = round((n + 1) * GRID, 3)
        o.append(f'  (symbol (lib_id {lib.qesc(d["sym"])}) (at {sx:.3f} {sy:.3f} 0) (unit {d["unit"]})')
        o.append( '    (in_bom yes) (on_board yes)')
        o.append(f'    (uuid "{lib.uid()}")')
        o.append(f'    (property "Reference" {lib.qesc(d["ref"])} (id 0)')
        o.append(f'      (at {sx:.3f} {round(sy - 1.27, 3):.3f} 0)')
        o.append(f'      (effects (font (size {FONT_SZ} {FONT_SZ})))')
        o.append( '    )')
        o.append(f'    (property "Value" {lib.qesc(d["dev"])} (id 1)')
        o.append(f'      (at {sx:.3f} {round(sy + bh + 1.27, 3):.3f} 0)')
        o.append(f'      (effects (font (size {FONT_SZ} {FONT_SZ})))')
        o.append( '    )')
        fp = ('reforming:' + lib.safe_fp_name(d['dev'])) if d['first'] else ''
        o.append(f'    (property "Footprint" {lib.qesc(fp)} (id 2)')
        o.append(f'      (at {sx:.3f} {sy:.3f} 0)')
        o.append(f'      (effects (font (size {FONT_SZ} {FONT_SZ})) (hide yes))')
        o.append( '    )')
        o.append(f'    (property "Datasheet" "" (id 3)')
        o.append(f'      (at {sx:.3f} {sy:.3f} 0)')
        o.append(f'      (effects (font (size {FONT_SZ} {FONT_SZ})) (hide yes))')
        o.append( '    )')
        for pname, _ in d['plist']:
            o.append(f'    (pin {lib.qesc(pname)} (uuid "{lib.uid()}"))')
        o.append('  )')
        o.append('')

    print(f"[gen] Emitting wires + labels ...")
    wire_count = 0
    for d in draws:
        sx, sy  = placed[d['key']]
        x_start = round(sx + WIRE_START_X, 3)
        x_end   = round(sx + WIRE_END_X, 3)
        for i, (_, net) in enumerate(d['plist']):
            py = round(sy + (i + 1) * GRID, 3)
            o.append(f'  (wire (pts (xy {x_start:.3f} {py:.3f}) (xy {x_end:.3f} {py:.3f}))')
            o.append( '    (stroke (width 0) (type default))')
            o.append(f'    (uuid "{lib.uid()}")')
            o.append( '  )')
            o.append(f'  (label {lib.qesc(net)} (at {x_end:.3f} {py:.3f} 0)')
            o.append(f'    (effects (font (size {FONT_SZ} {FONT_SZ})))')
            o.append(f'    (uuid "{lib.uid()}")')
            o.append( '  )')
            wire_count += 1
    print(f"[gen]   {wire_count} wires + labels")

    o.append('  (sheet_instances')
    o.append('    (path "/" (page "1"))')
    o.append('  )')
    o.append(')')
    return o


def _sanity_check(draws, placed, output_file):
    from collections import defaultdict

    with open(output_file, encoding='utf-8') as f:
        content = f.read()

    known = {}
    for d in draws:
        sx, sy  = placed[d['key']]
        xs = round(sx + WIRE_START_X, 3)
        xe = round(sx + WIRE_END_X, 3)
        for i, (_, net) in enumerate(d['plist']):
            py = round(sy + (i + 1) * GRID, 3)
            known[(xs, py)] = (d['ref'], net, xe)

    wire_map = {}
    for m in re.finditer(r'\(wire \(pts \(xy ([\d.-]+) ([\d.-]+)\) \(xy ([\d.-]+) ([\d.-]+)\)\)', content):
        p1 = (round(float(m.group(1)), 3), round(float(m.group(2)), 3))
        p2 = (round(float(m.group(3)), 3), round(float(m.group(4)), 3))
        wire_map[p1] = p2; wire_map[p2] = p1

    label_at = {}
    for m in re.finditer(r'\(label "([^"]*)" \(at ([\d.-]+) ([\d.-]+)', content):
        label_at[(round(float(m.group(2)), 3), round(float(m.group(3)), 3))] = \
            m.group(1).replace('\\"', '"').replace('\\\\', '\\')

    ok, bad, bad_refs = 0, 0, defaultdict(list)
    for (xs, py), (ref, exp_net, xe) in known.items():
        if (xs, py) not in wire_map:
            bad += 1; bad_refs[ref].append(f"no wire at ({xs},{py})"); continue
        end = wire_map[(xs, py)]
        if end != (xe, py):
            bad += 1; bad_refs[ref].append(f"wire end {end} != ({xe},{py})"); continue
        got = label_at.get((xe, py))
        if got is None:
            bad += 1; bad_refs[ref].append(f"no label at ({xe},{py})")
        elif got != exp_net:
            bad += 1; bad_refs[ref].append(f"net {got!r} != {exp_net!r}")
        else:
            ok += 1

    orphans = sum(1 for p1, p2 in wire_map.items() if p1 < p2 and p1 not in known and p2 not in known)

    off_grid = sum(
        1 for (xs, py), (_, _, xe) in known.items()
        for c in (xs, xe, py)
        if min(abs(c % GRID), abs(c % GRID - GRID)) > 1e-6
    )

    print(f"[sanity] pins={ok+bad}  ok={ok}  bad={bad}  orphan_wires={orphans}  off_grid={off_grid}")
    for ref, reasons in sorted(bad_refs.items()):
        for r in reasons[:3]:
            print(f"  {ref}: {r}")


def main():
    pins, devices = _load_data()
    draws = _build_draws(pins, devices)
    print(f"[build] {len(draws)} blocks")

    placed, sheet_w, sheet_h = _compute_layout(draws)
    _check_overlaps(draws, placed)

    o = _generate(draws, placed, sheet_w, sheet_h)

    print(f"[write] {OUTPUT_FILE}")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(o) + '\n')

    _sanity_check(draws, placed, OUTPUT_FILE)


if __name__ == '__main__':
    main()
