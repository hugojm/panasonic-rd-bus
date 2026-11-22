"""Write JLCPCB's BOM and CPL files from the board (run with KiCad's Python, from make_fab.sh)."""
import collections
import csv

import pcbnew

B = pcbnew.LoadBoard('panasonic_rd_v2.kicad_pcb')


def ref_key(r):
    letters = ''.join(c for c in r if c.isalpha())
    digits = ''.join(c for c in r if c.isdigit())
    return letters, int(digits or 0)


groups = collections.OrderedDict()
for f in B.GetFootprints():
    if not f.HasField('LCSC'):
        continue  # mounting holes are not parts
    # One line per LCSC part: JLCPCB leaves a part unselected when it appears on
    # two lines (RESET and BOOT are the same switch).
    key = (str(f.GetFPID().GetLibItemName()), f.GetFieldText('LCSC'))
    groups.setdefault(key, []).append((f.GetReference(), f.GetValue()))

with open('fab/panasonic_rd_v2_bom.csv', 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #'])
    for (fp, lcsc), parts in groups.items():
        parts.sort(key=lambda p: ref_key(p[0]))
        vals = list(dict.fromkeys(v for _, v in parts))
        w.writerow(['/'.join(vals), ','.join(r for r, _ in parts), fp, lcsc])

keep = {r for parts in groups.values() for r, _ in parts}
fp_of = {f.GetReference(): str(f.GetFPID().GetLibItemName()) for f in B.GetFootprints()}

# JLCPCB's part models are oriented differently from KiCad's footprints for some
# packages; checked in JLCPCB's placement viewer on 2026-11-21.
ROT_FIX = {'SOT-23': 180, 'SOT-223-3_TabPin2': 180, 'SOT-23-6': 270}


def mid(ref, x, y):
    """KiCad puts a through-hole part's origin on pin 1; JLCPCB places the part's centre."""
    f = B.FindFootprintByReference(ref)
    if f.GetAttributes() & pcbnew.FP_THROUGH_HOLE:
        pads = list(f.Pads())
        x = '%.6f' % pcbnew.ToMM(sum(p.GetPosition().x for p in pads) // len(pads))
        y = '%.6f' % -pcbnew.ToMM(sum(p.GetPosition().y for p in pads) // len(pads))
    return x + 'mm', y + 'mm'


def rotation(ref, rot):
    return '%.6f' % ((float(rot) + ROT_FIX.get(fp_of[ref], 0)) % 360)


with open('fab/pos_kicad.csv') as fh, open('fab/panasonic_rd_v2_cpl.csv', 'w', newline='') as out:
    w = csv.writer(out)
    w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
    for row in csv.DictReader(fh):
        if row['Ref'] in keep:
            w.writerow([row['Ref'], *mid(row['Ref'], row['PosX'], row['PosY']), 'Top', rotation(row['Ref'], row['Rot'])])

print('BOM lines', len(groups), '- placed parts', len(keep))
