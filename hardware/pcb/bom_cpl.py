"""Write JLCPCB's BOM and CPL files from the board (run with KiCad's Python, from make_fab.sh)."""
import collections
import csv

import pcbnew

B = pcbnew.LoadBoard('panasonic_rd.kicad_pcb')


def ref_key(r):
    letters = ''.join(c for c in r if c.isalpha())
    digits = ''.join(c for c in r if c.isdigit())
    return letters, int(digits or 0)


groups = collections.OrderedDict()
for f in B.GetFootprints():
    if not f.HasField('LCSC'):
        continue  # mounting holes are not parts
    key = (f.GetValue(), str(f.GetFPID().GetLibItemName()), f.GetFieldText('LCSC'))
    groups.setdefault(key, []).append(f.GetReference())

with open('fab/panasonic_rd_bom.csv', 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #'])
    for (val, fp, lcsc), refs in groups.items():
        w.writerow([val, ','.join(sorted(refs, key=ref_key)), fp, lcsc])

keep = {r for refs in groups.values() for r in refs}
with open('fab/pos_kicad.csv') as fh, open('fab/panasonic_rd_cpl.csv', 'w', newline='') as out:
    w = csv.writer(out)
    w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
    for row in csv.DictReader(fh):
        if row['Ref'] in keep:
            w.writerow([row['Ref'], row['PosX'] + 'mm', row['PosY'] + 'mm', 'Top', row['Rot']])

print('BOM lines', len(groups), '- placed parts', len(keep))
