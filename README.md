# Mobo — Boardview → KiCad PCB Toolchain

Reverse-engineering toolchain for the **Gigabyte GA-H81M-S1** motherboard.
Reads a `.tvw` boardview file, exports component/pin data as CSV, and regenerates
a full KiCad 6 project (PCB layout + schematic + footprint library).

---

## Directory Structure

```
Mobo/
  boardview/              Python boardview viewer (Thermetery Technology)
  boards/GA-H81M-S1/     TVW board files
  pipeline/
    input/                components.csv + pins.csv (exported from viewer)
    scripts/              Python export scripts
      lib.py              Shared utilities
      export_pcb.py       CSV → output.kicad_pcb
      export_sch.py       CSV → output.kicad_sch
      export_footprints.py CSV → footprints.pretty/*.kicad_mod
    kicad/                KiCad project files (output.kicad_pro, .kicad_pcb, .kicad_sch)
    footprints.pretty/    Generated KiCad footprint library
    router/               Specctra DSN file for autorouter
  docs/                   GA-H81M-S1-schematic.pdf
  launch_viewer.bat       Opens boardview viewer
  export_pcb.bat          Runs export_pcb.py
  export_sch.bat          Runs export_sch.py
  export_footprints.bat   Runs export_footprints.py
```

---

## Pipeline

```
boards/GA-H81M-S1/GA-H81M-S1 r3.0.tvw
        │
        ▼  boardview viewer (launch_viewer.bat)
           Export mode: Components → pipeline/input/components.csv
           Export mode: Pins      → pipeline/input/pins.csv
        │
        ├─▶  export_pcb.bat          → pipeline/kicad/output.kicad_pcb
        ├─▶  export_sch.bat          → pipeline/kicad/output.kicad_sch
        └─▶  export_footprints.bat   → pipeline/footprints.pretty/
```

---

## Quick Start

1. **View board:** double-click `launch_viewer.bat`
2. **Export CSVs:** in the viewer, use Cycle/Export mode to export components and pins into `pipeline/input/`
3. **Generate PCB:** double-click `export_pcb.bat`
4. **Generate schematic:** double-click `export_sch.bat`
5. **Generate footprints:** double-click `export_footprints.bat`
6. **Open in KiCad:** open `pipeline/kicad/output.kicad_pro`

---

## Coordinate System

- TVW file units: 1 unit ≈ 0.000325 mm (3077 units/mm)
- `PIN_SCALE = 2.54 × 0.0001` in export_pcb.py converts TVW units to mm
- `FLIP_X = FLIP_Y = True` — both flips cancel out, preserving orientation
- Pin world positions in `pins.csv` have rotation baked in at export time

## Notes

- `export_pcb.py` is stable — do not edit its logic
- Device names in `components.csv` may contain commas; `lib.read_components()` parses from the right
- KiCad footprint library `reforming` is declared in `pipeline/kicad/fp-lib-table`
