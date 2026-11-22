"""Report every place where bus-side copper comes within LIMIT mm of ESP32-side copper.

Run with KiCad's Python after build_pcb.py. DRC only checks the 0.15 mm minimum; this checks
the isolation gap. The DC-DC's own pins 2-3 (2.54 mm pitch) are the one expected exception.
"""
import sys

import pcbnew

LIMIT = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
BUS_NETS = {'BUS_P', 'BGND', 'RX_A', 'RX_K', 'TX_O', 'Q5_B', 'Q5_C', 'Q6_B', 'Q6_C', 'V5I'}

B = pcbnew.LoadBoard('panasonic_rd_v3.kicad_pcb')
items = []   # (domain, description, layer set, shape)
for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
    lname = B.GetLayerName(layer)
    for t in B.GetTracks():
        if t.IsOnLayer(layer):
            items.append((t.GetNetname() in BUS_NETS, '%s %s' % (t.GetClass(), t.GetNetname()), lname, t.GetEffectiveShape(layer)))
    for p in B.GetPads():
        if p.IsOnLayer(layer) and p.GetNetname():
            items.append((p.GetNetname() in BUS_NETS, 'pad %s.%s %s' % (p.GetParentFootprint().GetReference(), p.GetNumber(), p.GetNetname()),
                          lname, p.GetEffectiveShape(layer)))
    for z in B.Zones():
        if z.IsOnLayer(layer):
            poly = z.GetFilledPolysList(layer)
            for i in range(poly.OutlineCount()):
                items.append((z.GetNetname() in BUS_NETS, 'zone %s' % z.GetNetname(), lname,
                              pcbnew.SHAPE_POLY_SET(poly.Outline(i))))

bus = [i for i in items if i[0]]
esp = [i for i in items if not i[0]]
lim = pcbnew.FromMM(LIMIT)
close = set()
for _, da, la, sa in bus:
    for _, db, lb, sb in esp:
        if la == lb and sa.Collide(sb, lim):
            close.add('%s  <->  %s  (%s)' % (da, db, la))
print('bus/ESP copper closer than %.1f mm: %d' % (LIMIT, len(close)))
for c in sorted(close):
    print('  ', c)
