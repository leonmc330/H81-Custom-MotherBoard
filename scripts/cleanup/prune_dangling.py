"""Remove 2-pad footprints where only one pad is wired to a shared net.

A pad is "wired" if its net is used by at least one other footprint.
If a 2-pad component has at most one wired pad, it's dangling and gets removed.

Usage:  python prune_dangling.py [input.kicad_pcb] [output.kicad_pcb]
        Defaults: input = output.kicad_pcb, output = output_pruned.kicad_pcb
"""
import os
import re
import sys
from collections import defaultdict

_SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
SRC_DIR        = os.path.normpath(os.path.join(_SCRIPT_DIR, '..', '..', 'src'))

INPUT  = sys.argv[1] if len(sys.argv) > 1 else os.path.join(SRC_DIR, "H81-Custom-MotherBoard.kicad_pcb")
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SRC_DIR, "H81-Custom-MotherBoard_pruned.kicad_pcb")

pcb = open(INPUT, encoding="utf-8").read()

# ── parse footprint blocks ──────────────────────────────────────────────────

footprints = []

for m in re.finditer(r'[\t ]+\(footprint ', pcb):
    i = m.start()
    while i < len(pcb) and pcb[i] in ' \t':
        i += 1
    depth = 0
    j = i
    while j < len(pcb):
        if pcb[j] == '(':
            depth += 1
        elif pcb[j] == ')':
            depth -= 1
            if depth == 0:
                break
        j += 1
    block = pcb[i:j + 1]
    ref_m = re.search(r'\(property "Reference" "([^"]+)"', block)
    ref = ref_m.group(1) if ref_m else "?"
    pad_nets = re.findall(r'\(net "([^"]+)"\)', block)
    footprints.append((ref, pad_nets, m.start(), j + 1))

print(f"Parsed {len(footprints)} footprints")

# ── build net usage map ─────────────────────────────────────────────────────

net_users = defaultdict(set)
for ref, nets, _, _ in footprints:
    for n in nets:
        net_users[n].add(ref)

# ── find dangling 2-pad footprints ──────────────────────────────────────────

to_remove = set()
for ref, nets, start, end in footprints:
    if len(nets) != 2:
        continue
    shared = sum(1 for n in nets if len(net_users[n]) > 1)
    if shared <= 1:
        to_remove.add(ref)

print(f"2-pad footprints: {sum(1 for _, n, _, _ in footprints if len(n) == 2)}")
print(f"Dangling (removing): {len(to_remove)}")

if not to_remove:
    print("Nothing to prune.")
    sys.exit(0)

# ── remove footprint blocks (back-to-front to preserve offsets) ─────────────

cuts = sorted(
    [(start, end) for ref, _, start, end in footprints if ref in to_remove],
    reverse=True,
)

out = pcb
for start, end in cuts:
    while end < len(out) and out[end] in '\r\n':
        end += 1
    out = out[:start] + out[end:]

with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write(out)

print(f"Wrote {OUTPUT}")
print(f"Removed: {', '.join(sorted(to_remove)[:20])}"
      + (" ..." if len(to_remove) > 20 else ""))
