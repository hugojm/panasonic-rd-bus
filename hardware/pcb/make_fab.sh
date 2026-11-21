#!/bin/zsh
# Build the board, check it, and write the JLCPCB order files into fab/.
#   KICAD=/path/to/KiCad.app/Contents ./make_fab.sh
set -e
cd "$(dirname "$0")"
K=${KICAD:-/Volumes/KiCad/KiCad/KiCad.app/Contents}
CLI=$K/MacOS/kicad-cli
PY=$K/Frameworks/Python.framework/Versions/3.9/bin/python3

"$PY" build_pcb.py 2>&1 | grep -v "wxApp\|traits\|memory leak" || true
"$CLI" pcb drc --format json --severity-error -o fab_drc.json --exit-code-violations panasonic_rd.kicad_pcb >/dev/null
echo "DRC: 0 errors, 0 unconnected"

rm -rf fab && mkdir -p fab/gerber
"$CLI" pcb export gerbers --layers "F.Cu,B.Cu,F.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts" -o fab/gerber/ panasonic_rd.kicad_pcb >/dev/null
"$CLI" pcb export drill --format excellon --drill-origin absolute -o fab/gerber/ panasonic_rd.kicad_pcb >/dev/null
(cd fab/gerber && zip -q ../panasonic_rd_gerbers.zip *)
"$CLI" pcb export pos --format csv --units mm --side front -o fab/pos_kicad.csv panasonic_rd.kicad_pcb >/dev/null
"$CLI" pcb render --side top --width 1800 --height 1400 --quality basic -o fab/preview_top.png panasonic_rd.kicad_pcb >/dev/null
"$CLI" pcb render --side bottom --width 1800 --height 1400 --quality basic -o fab/preview_bottom.png panasonic_rd.kicad_pcb >/dev/null

# JLCPCB BOM (Comment, Designator, Footprint, LCSC Part #) and CPL (Designator, Mid X, Mid Y, Layer, Rotation)
"$PY" bom_cpl.py
rm fab/pos_kicad.csv
ls -la fab
