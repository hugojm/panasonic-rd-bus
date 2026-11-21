"""Generate the Panasonic R1/R2 bus board (ESP32-C3-WROOM-02) with KiCad's pcbnew API.

Run with KiCad's own Python (KiCad 10):
  .../KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 build_pcb.py

Writes panasonic_rd.kicad_pcb next to this script. The circuit is the one proven
on the breadboard (docs/hardware.md) plus what a bare ESP32-C3 module needs:
USB-C (power + flashing over native USB), 3.3 V LDO, RESET/BOOT buttons and the
EN / strapping parts. Coordinates are mm, origin at the board's top-left corner.
"""
import os
import sys

import pcbnew

LIB = os.environ.get('KICAD_FP', '/Volumes/KiCad/KiCad/KiCad.app/Contents/SharedSupport/footprints/')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'panasonic_rd.kicad_pcb')
BOARD_W, BOARD_H = 60.0, 46.0

B = pcbnew.BOARD()


def mm(v):
    return pcbnew.FromMM(v)


def V(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


NETS = {}


def net(name):
    if name not in NETS:
        n = pcbnew.NETINFO_ITEM(B, name)
        B.Add(n)
        NETS[name] = n
    return NETS[name]


# ---------------------------------------------------------------- design rules (within JLCPCB 2-layer limits)
ds = B.GetDesignSettings()
ds.m_MinClearance = mm(0.15)
ds.m_TrackMinWidth = mm(0.15)
ds.m_ViasMinSize = mm(0.5)
ds.m_MinThroughDrill = mm(0.3)
ds.m_HoleClearance = mm(0.25)
ds.m_CopperEdgeClearance = mm(0.3)
nc = ds.m_NetSettings.GetDefaultNetclass()
nc.SetClearance(mm(0.15))
nc.SetTrackWidth(mm(0.25))
nc.SetViaDiameter(mm(0.5))
nc.SetViaDrill(mm(0.3))

# ---------------------------------------------------------------- parts
# ref, library, footprint, value, LCSC, x, y, rotation, {pad: net}
# For a rotated 0603/0805 (90 deg) pad 1 is the lower one (larger y), pad 2 the upper one.
PARTS = [
    ('U1', 'RF_Module', 'ESP32-C3-WROOM-02', 'ESP32-C3-WROOM-02-N4', 'C2934560', 30, 15, 0,
     {'1': '+3V3', '2': 'EN', '3': 'RX', '4': 'TX', '7': 'IO8', '8': 'IO9', '9': 'GND', '19': 'GND',
      '16': 'IO2', '13': 'USB_DN', '14': 'USB_DP'}),
    # USB-C, mouth on the right edge. The plug ties its VBUS (and GND) contacts together,
    # so one VBUS pad is enough; the other pair (A4/B9) is left unconnected.
    ('J1', 'Connector_USB', 'USB_C_Receptacle_HRO_TYPE-C-31-M-12', 'TYPE-C-31-M-12', 'C165948', 56, 17, 90,
     {'A4': 'VBUS_ALT', 'B9': 'VBUS_ALT', 'A9': 'VBUS', 'B4': 'VBUS', 'A1': 'GND', 'A12': 'GND', 'B1': 'GND', 'B12': 'GND',
      'SH': 'GND', 'A5': 'CC1', 'B5': 'CC2', 'A6': 'USB_DP', 'B6': 'USB_DP', 'A7': 'USB_DN', 'B7': 'USB_DN'}),
    ('U2', 'Package_TO_SOT_SMD', 'SOT-23-6', 'USBLC6-2SC6', 'C7519', 46.5, 16, 0,
     {'1': 'USB_DP', '6': 'USB_DP', '3': 'USB_DN', '4': 'USB_DN', '2': 'GND'}),
    ('R11', 'Resistor_SMD', 'R_0603_1608Metric', '5.1k', 'C23186', 47.8, 19.6, 0, {'1': 'GND', '2': 'CC1'}),
    ('R12', 'Resistor_SMD', 'R_0603_1608Metric', '5.1k', 'C23186', 48.4, 12.4, 0, {'1': 'GND', '2': 'CC2'}),
    ('U3', 'Package_TO_SOT_SMD', 'SOT-223-3_TabPin2', 'AMS1117-3.3', 'C6186', 52.5, 5.5, 0,
     {'1': 'GND', '2': '+3V3', '3': 'VBUS'}),
    ('C1', 'Capacitor_SMD', 'C_0805_2012Metric', '10uF', 'C15850', 48.2, 10.2, 0, {'1': 'GND', '2': 'VBUS'}),
    ('C2', 'Capacitor_SMD', 'C_0805_2012Metric', '10uF', 'C15850', 55.4, 10.2, 0, {'1': '+3V3', '2': 'GND'}),
    ('D2', 'LED_SMD', 'LED_0603_1608Metric', 'LED', 'C2286', 51.9, 1.0, 0, {'1': 'GND', '2': 'LED_A'}),
    ('R13', 'Resistor_SMD', 'R_0603_1608Metric', '1k', 'C21190', 55.6, 1.0, 0, {'1': 'LED_A', '2': '+3V3'}),
    # module support
    ('C4', 'Capacitor_SMD', 'C_0805_2012Metric', '10uF', 'C15850', 15.6, 9.3, 0, {'1': 'GND', '2': '+3V3'}),
    ('R7', 'Resistor_SMD', 'R_0603_1608Metric', '10k', 'C25804', 18.2, 9.75, 90, {'1': 'EN', '2': '+3V3'}),
    ('C5', 'Capacitor_SMD', 'C_0603_1608Metric', '1uF', 'C15849', 1.72, 10.6, 90, {'1': 'GND', '2': 'EN'}),
    ('R9', 'Resistor_SMD', 'R_0603_1608Metric', '10k', 'C25804', 19.4, 17.2, 90, {'1': 'IO8', '2': '+3V3'}),
    ('R10', 'Resistor_SMD', 'R_0603_1608Metric', '10k', 'C25804', 41.4, 12.0, 0, {'1': 'IO2', '2': '+3V3'}),
    ('SW1', 'Button_Switch_SMD', 'SW_Push_1P1T_XKB_TS-1187A', 'RESET', 'C318884', 3.6, 5.2, 90, {'1': 'EN', '2': 'GND'}),
    ('SW2', 'Button_Switch_SMD', 'SW_Push_1P1T_XKB_TS-1187A', 'BOOT', 'C318884', 10.6, 5.2, 90, {'1': 'IO9', '2': 'GND'}),
    # AC bus interface (proven on the breadboard)
    ('J2', 'TerminalBlock_Phoenix', 'TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal', 'KF301-5.0-2P', 'C474881', 4.0, 40.0, 0,
     {'1': 'BUS_P', '2': 'GND'}),
    ('D1', 'Diode_SMD', 'D_SMA', 'SMAJ24A', 'C90510', 7.0, 27.0, 0, {'1': 'BUS_P', '2': 'GND'}),
    ('Q1', 'Package_TO_SOT_SMD', 'SOT-23', 'MMBT2222A', 'C8512', 12.5, 12.0, 0, {'1': 'Q1_B', '2': 'GND', '3': 'Q1_C'}),
    ('R1', 'Resistor_SMD', 'R_0603_1608Metric', '10k', 'C25804', 8.6, 11.05, 0, {'1': 'BUS_P', '2': 'Q1_B'}),
    ('R2', 'Resistor_SMD', 'R_0603_1608Metric', '680', 'C23228', 8.6, 12.6, 0, {'1': 'GND', '2': 'Q1_B'}),
    ('R3', 'Resistor_SMD', 'R_0603_1608Metric', '1k', 'C21190', 16.2, 12.0, 0, {'1': 'Q1_C', '2': 'RX'}),
    ('Q2', 'Package_TO_SOT_SMD', 'SOT-23', 'MMBT2222A', 'C8512', 13.0, 18.0, 0, {'1': 'Q2_B', '2': 'GND', '3': 'Q2_C'}),
    ('R4', 'Resistor_SMD', 'R_0603_1608Metric', '1k', 'C21190', 16.2, 13.5, 0, {'1': 'Q2_B', '2': 'TX'}),
    ('R5', 'Resistor_SMD', 'R_0603_1608Metric', '10k', 'C25804', 9.2, 17.05, 0, {'1': 'GND', '2': 'Q2_B'}),
    ('R6', 'Resistor_SMD', 'R_0603_1608Metric', '220', 'C22962', 13.94, 21.2, 90, {'1': 'BUS_P', '2': 'Q2_C'}),
]

FP = {}
REMOVED = []  # keep removed pads alive so SWIG doesn't free them twice
for ref, lib, name, value, lcsc, x, y, rot, pads in PARTS:
    f = pcbnew.FootprintLoad(LIB + lib + '.pretty', name)
    if f is None:
        sys.exit('missing footprint ' + lib + ':' + name)
    if ref == 'U1':
        # The footprint's 0.2 mm thermal vias are below JLCPCB's 2-layer minimum (0.3 mm): drop them
        # before the module joins the board; its ground pad connects through the plane and pin 9.
        for p in [p for p in f.Pads() if p.GetNumber() == '19' and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]:
            f.Remove(p)
            REMOVED.append(p)
    f.SetReference(ref)
    f.SetValue(value)
    f.SetField('LCSC', lcsc)
    f.GetField('LCSC').SetVisible(False)
    B.Add(f)
    f.SetPosition(V(x, y))
    f.SetOrientationDegrees(rot)
    for p in f.Pads():
        if p.GetNumber() in pads:
            p.SetNet(net(pads[p.GetNumber()]))
    FP[ref] = f
    f.Reference().SetVisible(False)  # dense board: no designators on the silkscreen

# M3 mounting holes in the empty bottom area
for i, (x, y) in enumerate([(20.0, 42.0), (55.5, 42.0)]):
    h = pcbnew.FootprintLoad(LIB + 'MountingHole.pretty', 'MountingHole_3.2mm_M3')
    h.SetReference('H%d' % (i + 1))
    h.Reference().SetVisible(False)
    h.Value().SetVisible(False)
    B.Add(h)
    h.SetPosition(V(x, y))

# ---------------------------------------------------------------- copper
W = {'USB': 0.18, 'CC': 0.15, 'SIG': 0.25, '3V3': 0.4, 'VBUS': 0.4, 'BUS': 0.5, 'GND': 0.3}


def track(netname, pts, width, layer=pcbnew.F_Cu):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(B)
        t.SetStart(V(x1, y1))
        t.SetEnd(V(x2, y2))
        t.SetWidth(mm(width))
        t.SetLayer(layer)
        t.SetNet(net(netname))
        B.Add(t)


def via(netname, x, y):
    v = pcbnew.PCB_VIA(B)
    v.SetPosition(V(x, y))
    v.SetWidth(mm(0.5))
    v.SetDrill(mm(0.3))
    v.SetNet(net(netname))
    B.Add(v)


BCU = pcbnew.B_Cu

# USB data: D+ joined on top; D- pads drop through vias and join on the bottom.
track('USB_DP', [(51.95, 16.25), (49.9, 16.25)], W['USB'])
track('USB_DP', [(51.95, 17.25), (49.9, 17.25), (49.9, 16.25), (48.9, 15.25), (47.64, 15.05)], W['USB'])
track('USB_DN', [(51.95, 16.75), (50.5, 16.75)], W['USB'])
track('USB_DN', [(51.95, 17.75), (50.5, 17.75)], W['USB'])
via('USB_DN', 50.5, 16.75)
via('USB_DN', 50.5, 17.75)
via('USB_DN', 48.8, 16.95)
track('USB_DN', [(50.5, 17.75), (50.5, 16.75), (50.3, 16.95), (48.8, 16.95)], W['USB'], BCU)
track('USB_DN', [(48.8, 16.95), (47.64, 16.95)], W['USB'])
track('USB_DP', [(45.36, 15.05), (39.6, 15.05), (38.75, 15.0)], 0.2)
track('USB_DN', [(45.36, 16.95), (43.8, 16.95), (43.35, 16.5), (38.75, 16.5)], 0.2)
track('USB_DP', [(47.64, 15.05), (45.36, 15.05)], 0.2)   # USBLC6 pass-through (pins 6-1)
track('USB_DN', [(47.64, 16.95), (45.36, 16.95)], 0.2)   # (pins 4-3)
track('GND', [(52.5, 13.6), (52.87, 12.68)], 0.3)       # USB-C GND pads to the shield
track('GND', [(52.5, 20.4), (52.87, 21.32)], 0.3)
track('CC2', [(51.95, 15.25), (50.0, 15.25), (50.0, 12.4), (49.175, 12.4)], W['CC'])
track('CC1', [(51.95, 18.25), (49.4, 18.25), (49.4, 19.6), (48.575, 19.6)], W['CC'])

# VBUS -> LDO input and its capacitor
track('VBUS', [(51.95, 14.55), (50.75, 14.55), (50.75, 8.65)], W['VBUS'])
track('VBUS', [(50.75, 10.2), (49.15, 10.2)], W['VBUS'])
track('VBUS', [(50.75, 8.65), (50.75, 7.8), (49.35, 7.8)], W['VBUS'])

# 3.3 V: LDO pin 2 to its tab, out to C2 and the LED, then on the bottom layer to the module.
track('+3V3', [(49.35, 5.5), (55.65, 5.5)], 0.5)
track('+3V3', [(55.65, 5.5), (55.0, 7.2), (54.45, 10.2)], W['3V3'])
track('+3V3', [(56.375, 1.0), (56.375, 3.9)], 0.3)
track('+3V3', [(49.35, 5.5), (47.4, 5.5)], W['3V3'])
via('+3V3', 47.4, 5.5)
track('+3V3', [(47.4, 5.5), (47.4, 8.5), (19.9, 8.5), (19.4, 9.0)], W['3V3'], BCU)
via('+3V3', 19.4, 9.0)
track('+3V3', [(19.4, 9.0), (21.25, 9.0)], W['3V3'])
track('+3V3', [(19.4, 9.0), (18.2, 8.975), (16.55, 9.3)], 0.3)
track('+3V3', [(19.4, 9.0), (19.4, 15.5)], 0.3, BCU)
via('+3V3', 19.4, 15.5)
track('+3V3', [(19.4, 15.5), (19.4, 16.425)], 0.3)
via('+3V3', 43.1, 12.0)
track('+3V3', [(43.1, 12.0), (43.1, 8.5)], 0.3, BCU)
track('+3V3', [(42.175, 12.0), (43.1, 12.0)], W['SIG'])
track('IO2', [(38.75, 12.0), (40.625, 12.0)], W['SIG'])
track('LED_A', [(52.69, 1.0), (54.825, 1.0)], W['SIG'])

# EN: module -> pull-up R7 -> around the buttons -> C5 and RESET
track('EN', [(21.25, 10.5), (14.2, 10.5), (13.5, 9.8), (13.5, 7.0), (2.4, 7.0), (1.72, 8.2), (1.72, 2.2)], W['SIG'])
track('EN', [(1.72, 8.2), (1.72, 9.825)], W['SIG'])           # down to C5
# IO8 pull-up, IO9 to BOOT (bottom layer, under the receive/transmit parts)
track('IO8', [(21.25, 18.0), (19.4, 17.975)], W['SIG'])
track('IO9', [(21.25, 19.5), (18.6, 19.6)], W['SIG'])
via('IO9', 18.6, 19.6)
track('IO9', [(18.6, 19.6), (18.0, 19.0), (18.0, 10.0), (8.72, 10.0), (8.72, 9.7)], W['SIG'], BCU)
via('IO9', 8.72, 9.7)
track('IO9', [(8.72, 9.7), (8.72, 8.2)], W['SIG'])
# BOOT's second pin-1 pad: under the EN line on the bottom layer
track('IO9', [(8.72, 9.7), (7.7, 8.7), (7.7, 2.2)], W['SIG'], BCU)
via('IO9', 7.7, 2.2)
track('IO9', [(7.7, 2.2), (8.72, 2.2)], W['SIG'])

# Receive: bus -> 10k/680 divider -> Q1 -> 1k -> IO4 (RX)
track('RX', [(21.25, 12.0), (16.975, 12.0)], W['SIG'])
track('Q1_C', [(15.425, 12.0), (13.44, 12.0)], W['SIG'])
track('Q1_B', [(9.375, 11.05), (11.56, 11.05)], W['SIG'])
track('Q1_B', [(9.375, 12.6), (9.375, 11.05)], W['SIG'])
# Transmit: IO5 (TX) -> 1k -> Q2 (10k to GND) -> 220 -> bus+
track('TX', [(21.25, 13.5), (16.975, 13.5)], W['SIG'])
track('Q2_B', [(15.425, 13.5), (14.6, 13.5), (14.6, 16.2), (12.06, 16.2), (12.06, 17.05)], W['SIG'])
track('Q2_B', [(12.06, 17.05), (9.975, 17.05)], W['SIG'])
track('Q2_C', [(13.94, 18.0), (13.94, 20.425)], 0.4)
# Bus+ (15 V): terminal -> TVS -> R1 and R6, kept on the left, far from the module
track('BUS_P', [(4.0, 40.0), (4.0, 11.05), (7.825, 11.05)], W['BUS'])
track('BUS_P', [(13.94, 21.975), (13.94, 22.8), (4.0, 22.8)], W['BUS'])

# Ground: short stubs from each ground pad to a via into the ground planes
for netname, pad_xy, v_xy in [
    ('GND', (45.36, 16.0), (44.2, 16.0)),
    ('GND', (47.625, 12.4), (46.8, 12.4)),
    ('GND', (47.025, 19.6), (46.2, 19.6)),
    ('GND', (47.25, 10.2), (46.4, 10.2)),
    ('GND', (56.35, 10.2), (57.6, 10.2)),
    ('GND', (49.35, 3.2), (47.6, 3.0)),
    ('GND', (7.825, 12.6), (6.9, 13.4)),
    ('GND', (11.56, 12.95), (10.6, 13.7)),
    ('GND', (8.425, 17.05), (7.3, 17.05)),
    ('GND', (12.06, 18.95), (11.0, 19.7)),
    ('GND', (1.72, 11.375), (1.72, 12.3)),
    ('GND', (5.48, 8.2), (5.48, 9.3)),
    ('GND', (5.48, 2.2), (6.4, 2.6)),
    ('GND', (12.48, 8.2), (12.48, 9.2)),
    ('GND', (12.48, 2.2), (13.4, 2.6)),
    ('GND', (21.25, 21.0), (19.8, 21.0)),
    ('GND', (9.0, 27.0), (10.7, 27.0)),
]:
    track(netname, [pad_xy, v_xy], W['GND'])
    via(netname, *v_xy)
track('GND', [(51.11, 1.0), (50.0, 2.6), (49.35, 3.2)], 0.3)  # LED cathode to LDO ground
# stitching vias tie the two ground planes together
for xy in [(25, 30), (35, 30), (45, 30), (55, 32), (25, 38), (32, 44), (45, 42), (50, 44), (16, 30), (13, 29.5),
           (58, 18), (42, 22), (30, 24), (40, 26), (2, 30), (14, 44)]:
    via('GND', *xy)

# ---------------------------------------------------------------- outline and ground planes
rect = pcbnew.PCB_SHAPE(B)
rect.SetShape(pcbnew.SHAPE_T_RECTANGLE)
rect.SetStart(V(0, 0))
rect.SetEnd(V(BOARD_W, BOARD_H))
rect.SetLayer(pcbnew.Edge_Cuts)
rect.SetWidth(mm(0.1))
B.Add(rect)

for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
    z = pcbnew.ZONE(B)
    z.SetLayer(layer)
    z.SetNet(net('GND'))
    z.SetLocalClearance(mm(0.25))
    z.SetMinThickness(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in [(0.2, 0.2), (BOARD_W - 0.2, 0.2), (BOARD_W - 0.2, BOARD_H - 0.2), (0.2, BOARD_H - 0.2)]:
        ol.Append(mm(x), mm(y))
    B.Add(z)

# ---------------------------------------------------------------- silkscreen


def silk(text, x, y, size=1.0, layer=pcbnew.F_SilkS, bold=False):
    t = pcbnew.PCB_TEXT(B)
    t.SetText(text)
    t.SetPosition(V(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * (0.2 if bold else 0.15)))
    B.Add(t)


silk('AIRE PANASONIC  R1/R2', 30.0, 33.0, 1.4, bold=True)
silk('ESP32-C3  v1  2026-11', 30.0, 35.4, 0.9)
silk('+ ROJO', 3.4, 32.0, 0.9, bold=True)
silk('- MARRON', 10.4, 33.6, 0.9, bold=True)
silk('BUS AIRE', 6.6, 30.4, 0.7)
silk('RST', 3.6, 0.9, 0.7)
silk('BOOT', 10.6, 0.9, 0.7)
silk('USB-C 5V', 55.0, 24.5, 0.8)
silk('PWR', 49.5, 0.75, 0.6)

# ---------------------------------------------------------------- fill zones and save
filler = pcbnew.ZONE_FILLER(B)
filler.Fill(B.Zones())
B.Save(OUT)
import json
json.dump({
    'meta': {'filename': 'panasonic_rd.kicad_pro', 'version': 1},
    'board': {'design_settings': {'rules': {
        'min_clearance': 0.15, 'min_track_width': 0.15, 'min_via_diameter': 0.5, 'min_via_annular_width': 0.1,
        'min_through_hole_diameter': 0.3, 'min_hole_clearance': 0.25, 'min_hole_to_hole': 0.25,
        'min_copper_edge_clearance': 0.3, 'min_silk_clearance': 0.0, 'min_text_height': 0.6, 'min_text_thickness': 0.1}}},
    'net_settings': {'classes': [{'name': 'Default', 'clearance': 0.15, 'track_width': 0.25, 'via_diameter': 0.5,
                                  'via_drill': 0.3, 'microvia_diameter': 0.3, 'microvia_drill': 0.1}], 'meta': {'version': 3}},
}, open(OUT.replace('.kicad_pcb', '.kicad_pro'), 'w'), indent=2)
print('wrote', OUT)
