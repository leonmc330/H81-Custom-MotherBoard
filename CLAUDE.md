# Mobo — Project Context for Claude

Motherboard boardview analysis and PCB regeneration toolchain.
Primary board in use: **Gigabyte GA-H81M-S1**.

---

## Directory Layout

```
Mobo/
  boardview/            Python boardview tool (Thermetery Technology)
  boards/GA-H81M-S1/   TVW board files + EAGLEview binary
  reforming/            KiCad PCB regen workspace (pintokicad.py runs here)
  reforming.pretty/     KiCad footprint library (LGA_40x40_0p9144.kicad_mod)
  Playground/           KiCad scratch project
  docs/                 GA-H81M-S1-schematic.pdf
  launch_viewer.bat     Opens boardview viewer (cd boardview && python viewer.py)
  regen_pcb.bat         Runs pintokicad.py in reforming/ then pauses
```

---

## Pipeline

```
boards/GA-H81M-S1/*.tvw
        │
        ▼  (boardview/viewer.py — GUI, Cycle mode)
  reforming/components.csv   refdes, device, x, y, sizex, sizey, rotation
  reforming/pins.csv         refdes, pin, x, y, net
        │
        ▼  (reforming/pintokicad.py)
  reforming/output.kicad_pcb
```

**Viewer export flow:** open a TVW in the viewer, set Export mode to "Components" or "Pins", press Cycle. Components export to `<board>.comps.csv` (adjacent to TVW) or to `components.csv` in CWD. Pin world positions have rotation **baked in** at export time.

---

## Key Files

### `boardview/viewer.py`
Main GUI. Relevant export methods:
- `_set_comp_export_path` (line ~5083) — writes CSV header `refdes,device,x,y,sizex,sizey,rotation`
- `_export_component` (line ~5133) — appends one row per component click/cycle; includes `comp.rotation`
- `_export_pin` (line ~5107) — writes world-space pin position with rotation applied via standard CCW matrix

### `boardview/tvw_parser.py`
Gigabyte/Compal TVW decoder. Key functions:
- `_decode_position` — reads 8×i32 pre-header; fields are `[y_alt, chip_y, chip_x, rot, ...]`. Rotation snapped with `round((rot % 360) / 90) * 90 % 360` (handles negatives and >360).
- `_decode_layer` — trailer byte 9: `0x02`=TOP, else BOTTOM
- `_decode_refdes` — Pascal string 32-60 bytes before marker
- `_find_chip_headers` — 0x01 + Pascal + 0-4 zero pad + Pascal footprint
- `_find_net_table` — longest run of packed Pascal strings
- `_find_pad_runs` — 38-byte (TOP) and 54-byte (BOTTOM) pad records; net_id at +22/+38
- `_build_signals` — matches pad records to shape pins via spatial hash (TOL=50 file units)

**Coordinate convention (TVW):** 1 file unit ≈ 0.000325 mm (3077 units/mm). Rotation is stored in degrees, treated as standard CCW in the viewer.

**Variant detection:** Compal/Lenovo files have >100 occurrences of signature `b8 0b 00 00 2c 01 00 00`; dispatches to `tvw_compal.py`.

### `boardview/tvw_master_fp.py`
Master footprint table decoder. Pin transform formula (left-handed TVW convention):
```
wx = chip_x + ly * cos(-rot) - lx * sin(-rot)
wy = chip_y + ly * sin(-rot) + lx * cos(-rot)
```
The viewer re-applies standard CCW rotation instead for rendering/export.

### `reforming/pintokicad.py`
Converts exported CSVs to KiCad PCB. Config at top:
- `PIN_SCALE = 2.54 * 0.0001` (TVW units → mm)
- `FLIP_X = FLIP_Y = True` (both flips = orientation-preserving, so KiCad rotation = TVW rotation)

**Rotation:** Pin world positions from `pins.csv` are already in world-space — place them directly with no rotation math. Rotation only affects the **courtyard outline** (from `sizex`/`sizey` in `components.csv`, which are in component-local space). For 90°/270° rotations, swap `sx` and `sy` before calling `build_outline` so the rectangle matches the component's world orientation. No rotation is written to the KiCad `(at)` field.

### `boardview/notvwpwd.py`
Strips TVW password. Usage: `python notvwpwd.py in.tvw out.tvw`

---

## Board Files (`boards/GA-H81M-S1/`)

| File | Note |
|---|---|
| `GA-H81M-S1 r3.0.tvw` | Latest revision — use this |
| `GA-H81M-S1 r1.0` … `r2.2-3.0` | Earlier revisions |
| `in.tvw` | Working copy (encrypted input to notvwpwd) |
| `in1.tvw` | Decrypted working copy |
| `in1.tvw.topocache.pkl` | Trace topology cache for in1.tvw (speeds up viewer) |
| `out.json` | JSON export output |
| `eagleview.exe` + 3 DLLs | Native EAGLEview binary (opens TVW directly) |
| `GA-H81M-S1 r3.0.tvw.comps.csv` | Header-only stub (export was started, not completed) |
| `GA-H81M-S1 r3.0.tvw.pins.csv` | Header-only stub |

---

## Changes Made This Session

### `boardview/tvw_parser.py` — `_decode_position`
Fixed rotation snap that returned 0 for negative/large values:
```python
# OLD (broke on -90, 360, 450, etc.)
rot = (rot // 90 * 90) if 0 <= rot < 360 else 0
# NEW
rot = round((rot % 360) / 90) * 90 % 360
```

### `boardview/viewer.py`
- `_set_comp_export_path`: CSV header now includes `rotation` column
- `_export_component`: appends `{comp.rotation:.3f}` as 7th field

### `reforming/pintokicad.py`
- Added `import math`
- Component reader now accepts 6-field rows (old, rotation defaults to 0) or 7-field rows
- Added `unrotate_pad(kx, ky, rot_deg)` — converts world-relative KiCad pad to footprint-local
- `build_footprint` now accepts `rotation` and emits `(at x y rotation)` when non-zero
- Pad positions passed through `unrotate_pad` before being written to KiCad

---

## Gotchas

- `reforming/components.csv` and `reforming/pins.csv` are hardcoded relative paths in `pintokicad.py` — run it from inside `reforming/`.
- `boardview/_old_launch.bat` is a stale artifact (path was `thermetery-boardview-main/viewer.py`, now broken). Use `launch_viewer.bat` at the root instead.
- `shape.bbox()` returns **footprint-local** dimensions (unrotated). The `sizex`/`sizey` in components.csv are local, not world-space. KiCad handles the rotation via the `(at)` field.
- The `reforming.pretty/` directory must be adjacent to `reforming/` for KiCad to find the footprint library (KiCad resolves `${KIPRJMOD}/../reforming.pretty`).
- `boardview/tvw_to_json.py` is a wrapper that tries to import `from scripts import tvw_to_json` — the `scripts/` subpackage does not exist in this repo; this file is dead code.
- **Device names in components.csv contain commas** (e.g. `USB+LAN/1G/GO,Y/OS/RA/D/12C/ES`). Never parse the components CSV by counting columns from the left. `pintokicad.py` parses from the right: last 4 fields = x,y,sx,sy; if 5th-from-right is also a float it's rotation; everything between index 1 and the numeric tail is the device name joined back with `,`.
