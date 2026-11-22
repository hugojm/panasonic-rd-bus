"""Generate the isolated Panasonic R1/R2 board, v3 (ESP32-C3-WROOM-02), with KiCad's pcbnew API.

Run with KiCad's own Python (KiCad 10):
  .../KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 build_pcb.py

Writes panasonic_rd_v3.kicad_pcb next to this script. Same ESP32 side as v1 (../pcb:
ESP32-C3 module, USB-C, AMS1117, buttons), but the AC bus is galvanically isolated:

  ESP32 side (GND)                       |  bus side (BGND = BUS-, floating)
  RX  <- H11L1 U5 output, 4.7k to 3V3    |  BUS+ -> 2k -> 7.5 V zener -> U5 LED -> BUS-
  TX  -> 680R -> H11L1 U6 LED            |  U6 output (V5I) -> 4.7k -> MMBT3906 -> 1k -> MMBT2222A
                                         |     -> 220R pulls BUS+ down (same as the proven circuit)
  VBUS (USB) -> B0505S-1WR3 isolated DC-DC -> V5I powers U6 and the inverter on the bus side

The U5 LED only lights while the bus is above ~11 V (idle 15.2 V, carrier dips 7.6 V), so
its output follows the carrier like Q1 did in v1. With the ESP32 off or idle, U6 is dark,
its output is pulled high, the PNP is off and nothing pulls the bus. Copper on the two
sides is >= 2 mm apart; only the optocouplers and the DC-DC cross the gap.
Coordinates are mm, origin at the board's top-left corner.
"""
import os
import sys

import pcbnew

LIB = os.environ.get('KICAD_FP', '/Volumes/KiCad/KiCad/KiCad.app/Contents/SharedSupport/footprints/')
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'panasonic_rd_v3.kicad_pcb')
BOARD_W, BOARD_H = 60.0, 54.0
BARRIER_Y = 28.6   # left part: ESP32 above, bus below
BARRIER_X = 36.2   # lower part: bus left, ESP32 right

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
    # ---- ESP32 side: identical to v1
    ('U1', 'RF_Module', 'ESP32-C3-WROOM-02', 'ESP32-C3-WROOM-02-N4', 'C2934560', 30, 15, 0,
     {'1': '+3V3', '2': 'EN', '3': 'RX', '4': 'TX', '7': 'IO8', '8': 'IO9', '9': 'GND', '19': 'GND',
      '16': 'IO2', '13': 'USB_DN', '14': 'USB_DP'}),
    ('J1', 'Connector_USB', 'USB_C_Receptacle_HRO_TYPE-C-31-M-12', 'TYPE-C-31-M-12', 'C165948', 56, 17, 90,
     {'A4': 'VBUS2', 'B9': 'VBUS2', 'A9': 'VBUS', 'B4': 'VBUS', 'A1': 'GND', 'A12': 'GND', 'B1': 'GND', 'B12': 'GND',
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
    ('C4', 'Capacitor_SMD', 'C_0805_2012Metric', '10uF', 'C15850', 15.6, 9.3, 0, {'1': 'GND', '2': '+3V3'}),
    ('R7', 'Resistor_SMD', 'R_0603_1608Metric', '10k', 'C25804', 18.2, 9.75, 90, {'1': 'EN', '2': '+3V3'}),
    ('C5', 'Capacitor_SMD', 'C_0603_1608Metric', '1uF', 'C15849', 1.72, 10.6, 90, {'1': 'GND', '2': 'EN'}),
    ('R9', 'Resistor_SMD', 'R_0603_1608Metric', '10k', 'C25804', 19.4, 17.2, 90, {'1': 'IO8', '2': '+3V3'}),
    ('R10', 'Resistor_SMD', 'R_0603_1608Metric', '10k', 'C25804', 41.4, 12.0, 0, {'1': 'IO2', '2': '+3V3'}),
    ('SW1', 'Button_Switch_SMD', 'SW_Push_1P1T_XKB_TS-1187A', 'RESET', 'C318884', 3.6, 5.2, 90, {'1': 'EN', '2': 'GND'}),
    ('SW2', 'Button_Switch_SMD', 'SW_Push_1P1T_XKB_TS-1187A', 'BOOT', 'C318884', 10.6, 5.2, 90, {'1': 'IO9', '2': 'GND'}),
    # ---- the isolation barrier: two optocouplers and the isolated DC-DC
    # U5 (receive): LED row (pins 1-3) on the bus side (down), output row (4-6) on the ESP32 side.
    ('U5', 'Package_DIP', 'SMDIP-6_W9.53mm', 'H11L1S', 'C78589', 5.0, BARRIER_Y, 90,
     {'1': 'RX_A', '2': 'BGND', '4': 'RX', '5': 'GND', '6': '+3V3'}),
    # U6 (transmit): LED row on the ESP32 side (up), output row on the bus side.
    ('U6', 'Package_DIP', 'SMDIP-6_W9.53mm', 'H11L1S', 'C78589', 14.0, BARRIER_Y, 270,
     {'1': 'TX_A', '2': 'GND', '4': 'TX_O', '5': 'BGND', '6': 'V5I'}),
    # B0505S-1WR3 (SIP-4, pin 1 = -Vin, 2 = +Vin, 3 = 0V out, 4 = +5V out), pins 1-2 on the ESP32 side.
    ('PS1', 'Connector_PinHeader_2.54mm', 'PinHeader_1x04_P2.54mm_Vertical', 'B0505S-1WR3', 'C7465178', 40.0, 33.0, 270,
     {'1': 'GND', '2': 'VBUS2', '3': 'BGND', '4': 'V5I'}),
    # ---- ESP32 side of the optocouplers
    ('C23', 'Capacitor_SMD', 'C_0603_1608Metric', '100nF', 'C14663', 3.8, 19.4, 0, {'1': '+3V3', '2': 'GND'}),
    ('R37', 'Resistor_SMD', 'R_0603_1608Metric', '4.7k', 'C23162', 9.0, 18.0, 90, {'1': '+3V3', '2': 'RX'}),
    ('R38', 'Resistor_SMD', 'R_0603_1608Metric', '680', 'C23228', 17.2, 16.0, 90, {'1': 'TX_A', '2': 'TX'}),
    ('C25', 'Capacitor_SMD', 'C_0805_2012Metric', '10uF', 'C15850', 39.0, 38.0, 90, {'1': 'GND', '2': 'VBUS2'}),
    # ---- bus side (BGND = BUS-)
    ('J2', 'TerminalBlock_Phoenix', 'TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal', 'KF301-5.0-2P', 'C474881', 4.0, 48.0, 0,
     {'1': 'BUS_P', '2': 'BGND'}),
    ('D1', 'Diode_SMD', 'D_SMA', 'SMAJ24A', 'C90510', 19.0, 49.5, 0, {'1': 'BUS_P', '2': 'BGND'}),
    # receive: BUS+ -> R30 -> DZ1 (7.5 V) -> U5 LED
    ('DZ1', 'Diode_SMD', 'D_SOD-123', 'BZT52C7V5', 'C707137', 2.46, 37.2, 90, {'1': 'RX_K', '2': 'RX_A'}),
    ('R30', 'Resistor_SMD', 'R_0603_1608Metric', '2k', 'C22975', 5.4, 38.85, 0, {'1': 'RX_K', '2': 'BUS_P'}),
    # transmit: U6 output (low = send) -> PNP Q5 -> NPN Q6 -> 220 ohm onto BUS+
    ('R32', 'Resistor_SMD', 'R_0603_1608Metric', '4.7k', 'C23162', 15.0, 37.25, 0, {'1': 'TX_O', '2': 'Q5_B'}),
    ('R33', 'Resistor_SMD', 'R_0603_1608Metric', '10k', 'C25804', 13.0, 39.4, 0, {'1': 'TX_O', '2': 'V5I'}),
    ('Q5', 'Package_TO_SOT_SMD', 'SOT-23', 'MMBT3906', 'C7420354', 19.5, 38.2, 0, {'1': 'Q5_B', '2': 'V5I', '3': 'Q5_C'}),
    ('R34', 'Resistor_SMD', 'R_0603_1608Metric', '1k', 'C21190', 23.0, 38.2, 0, {'1': 'Q5_C', '2': 'Q6_B'}),
    ('R35', 'Resistor_SMD', 'R_0603_1608Metric', '10k', 'C25804', 26.06, 34.9, 90, {'1': 'Q6_B', '2': 'BGND'}),
    ('Q6', 'Package_TO_SOT_SMD', 'SOT-23', 'MMBT2222A', 'C8512', 27.0, 38.2, 0, {'1': 'Q6_B', '2': 'BGND', '3': 'Q6_C'}),
    ('R31', 'Resistor_SMD', 'R_0805_2012Metric', '220', 'C17557', 30.8, 38.2, 0, {'1': 'Q6_C', '2': 'BUS_P'}),
    ('C24', 'Capacitor_SMD', 'C_0805_2012Metric', '10uF', 'C15850', 33.8, 41.5, 90, {'1': 'BGND', '2': 'V5I'}),
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

# M3 mounting holes: one on each side of the barrier
for i, (x, y) in enumerate([(31.5, 50.5), (55.5, 50.5)]):
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

# ---- ESP32 side, as v1
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
track('USB_DP', [(47.64, 15.05), (45.36, 15.05)], 0.2)
track('USB_DN', [(47.64, 16.95), (45.36, 16.95)], 0.2)
track('GND', [(52.5, 13.6), (52.87, 12.68)], 0.3)
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
track('EN', [(1.72, 8.2), (1.72, 9.825)], W['SIG'])
# IO8 pull-up, IO9 to BOOT (bottom layer)
track('IO8', [(21.25, 18.0), (19.4, 17.975)], W['SIG'])
track('IO9', [(21.25, 19.5), (18.6, 19.6)], W['SIG'])
via('IO9', 18.6, 19.6)
track('IO9', [(18.6, 19.6), (18.0, 19.0), (18.0, 10.0), (8.72, 10.0), (8.72, 9.7)], W['SIG'], BCU)
via('IO9', 8.72, 9.7)
track('IO9', [(8.72, 9.7), (8.72, 8.2)], W['SIG'])
track('IO9', [(8.72, 9.7), (7.7, 8.7), (7.7, 2.2)], W['SIG'], BCU)
via('IO9', 7.7, 2.2)
track('IO9', [(7.7, 2.2), (8.72, 2.2)], W['SIG'])

# ---- ESP32 side of the optocouplers
# 3.3 V for U5 and the RX pull-up: bottom layer from the R9 via, under the module edge
track('+3V3', [(19.4, 15.5), (19.4, 20.4), (2.46, 20.4), (2.46, 21.6)], 0.3, BCU)
via('+3V3', 2.46, 21.6)
track('+3V3', [(2.46, 21.6), (2.46, 23.84)], 0.4)                 # U5 pin 6
track('+3V3', [(3.025, 19.4), (2.46, 20.0), (2.46, 21.6)], 0.3)    # C23
via('+3V3', 9.0, 20.4)
track('+3V3', [(9.0, 20.4), (9.0, 18.775)], 0.3)                   # R37
# RX: U5 pin 4 -> module pin 3, pull-up R37
track('RX', [(7.54, 23.84), (7.54, 12.0), (21.25, 12.0)], W['SIG'])
track('RX', [(7.54, 17.225), (9.0, 17.225)], W['SIG'])
# TX: module pin 4 -> 680 ohm R38 -> U6 LED (pin 1); LED cathode (pin 2) to GND
track('TX', [(21.25, 13.5), (17.2, 13.5), (17.2, 15.225)], W['SIG'])
track('TX_A', [(17.2, 16.775), (17.2, 23.84), (16.54, 23.84)], W['SIG'])
# USB 5 V (A4/B9) -> DC-DC input, and its capacitor
track('VBUS2', [(51.95, 19.45), (50.6, 19.45), (50.6, 23.0), (37.46, 23.0), (37.46, 37.05), (39.0, 37.05)], 0.4)

# ---- bus side
P = 0.5
# BUS+ trunk: terminal -> R30 (receive), R31 (transmit), TVS
track('BUS_P', [(4.0, 48.0), (4.0, 44.0), (31.75, 44.0), (31.75, 38.2)], P)
track('BUS_P', [(6.175, 38.85), (6.175, 44.0)], 0.4)
track('BUS_P', [(17.0, 44.0), (17.0, 49.5)], P)
# receive: zener anode -> U5 LED anode; R30 -> zener cathode
track('RX_A', [(2.46, 35.55), (2.46, 33.36)], W['SIG'])
track('RX_K', [(2.46, 38.85), (4.625, 38.85)], W['SIG'])
# transmit: U6 output -> R32 -> Q5 base, R33 pull-up to V5I
track('TX_O', [(11.46, 33.36), (11.46, 37.25), (14.225, 37.25)], W['SIG'])
track('TX_O', [(11.46, 39.4), (12.225, 39.4)], W['SIG'])
track('TX_O', [(11.46, 37.25), (11.46, 39.4)], W['SIG'])
track('Q5_B', [(15.775, 37.25), (18.56, 37.25)], W['SIG'])
track('Q5_C', [(20.44, 38.2), (22.225, 38.2)], W['SIG'])
track('Q6_B', [(23.775, 38.2), (24.6, 37.25), (26.06, 37.25)], W['SIG'])
track('Q6_B', [(26.06, 35.675), (26.06, 37.25)], W['SIG'])
track('Q6_C', [(27.94, 38.2), (29.85, 38.2)], 0.4)
# V5I (isolated 5 V): DC-DC pin 4 -> C24 on top; on the bottom to U6, Q5 and R33
track('V5I', [(32.38, 33.0), (32.38, 34.6), (33.8, 35.2), (33.8, 40.55)], 0.4)
track('V5I', [(32.38, 33.0), (32.38, 41.0), (14.8, 41.0), (14.8, 39.4)], 0.4, BCU)
track('V5I', [(16.54, 41.0), (16.54, 35.6)], 0.4, BCU)
track('V5I', [(18.56, 41.0), (18.56, 40.4)], 0.4, BCU)
via('V5I', 14.8, 39.4)
via('V5I', 16.54, 35.6)
via('V5I', 18.56, 40.4)
track('V5I', [(13.775, 39.4), (14.8, 39.4)], W['SIG'])
track('V5I', [(16.54, 35.6), (16.54, 33.36)], 0.4)
track('V5I', [(18.56, 40.4), (18.56, 39.15)], 0.4)

# Ground stubs to vias into the planes: ESP32 side (GND) and bus side (BGND)
for netname, pad_xy, v_xy in [
    ('GND', (45.36, 16.0), (44.2, 16.0)),
    ('GND', (47.625, 12.4), (46.8, 12.4)),
    ('GND', (47.025, 19.6), (46.2, 19.6)),
    ('GND', (47.25, 10.2), (46.4, 10.2)),
    ('GND', (56.35, 10.2), (57.6, 10.2)),
    ('GND', (49.35, 3.2), (47.6, 3.0)),
    ('GND', (1.72, 11.375), (1.72, 12.3)),
    ('GND', (5.48, 8.2), (5.48, 9.3)),
    ('GND', (5.48, 2.2), (6.4, 2.6)),
    ('GND', (12.48, 8.2), (12.48, 9.2)),
    ('GND', (12.48, 2.2), (13.4, 2.6)),
    ('GND', (21.25, 21.0), (19.8, 21.0)),
    ('GND', (4.575, 19.4), (5.5, 19.4)),        # C23
    ('GND', (5.0, 23.84), (5.0, 22.2)),         # U5 pin 5
    ('GND', (14.0, 23.84), (14.0, 22.0)),       # U6 LED cathode
    ('GND', (39.0, 38.95), (39.0, 40.0)),       # C25
    ('GND', (40.0, 33.0), (41.4, 34.4)),        # DC-DC -Vin
    ('BGND', (5.0, 33.36), (5.0, 35.6)),        # U5 LED cathode
    ('BGND', (14.0, 33.36), (14.0, 35.6)),      # U6 pin 5
    ('BGND', (26.06, 34.125), (26.06, 33.2)),   # R35
    ('BGND', (26.06, 39.15), (26.06, 40.2)),    # Q6 emitter
    ('BGND', (33.8, 42.45), (33.8, 43.2)),      # C24
    ('BGND', (34.92, 33.0), (33.5, 31.5)),      # DC-DC 0 V (via kept away from pin 2)
    ('BGND', (21.0, 49.5), (22.6, 49.5)),       # TVS
]:
    track(netname, [pad_xy, v_xy], W['GND'])
    via(netname, *v_xy)
track('GND', [(51.11, 1.0), (50.0, 2.6), (49.35, 3.2)], 0.3)
# stitching vias: ESP32 side ...
for xy in [(45, 30), (55, 32), (58, 18), (42, 22), (30, 24.5), (22, 25.5), (45, 42),
           (50, 46), (42, 48), (58, 40), (48, 36), (10.4, 26.8)]:
    via('GND', *xy)
# ... and bus side
for xy in [(3, 30.6), (20, 31.2), (24, 31.2), (9.5, 35.8), (14.2, 45.6), (26, 47), (34, 47), (28.5, 52.5), (1.6, 41.5)]:
    via('BGND', *xy)

# ---------------------------------------------------------------- outline and the two ground planes
rect = pcbnew.PCB_SHAPE(B)
rect.SetShape(pcbnew.SHAPE_T_RECTANGLE)
rect.SetStart(V(0, 0))
rect.SetEnd(V(BOARD_W, BOARD_H))
rect.SetLayer(pcbnew.Edge_Cuts)
rect.SetWidth(mm(0.1))
B.Add(rect)

GAP = 1.0   # each plane stops 1 mm short of the barrier line: >= 2 mm of bare board between them
E = 0.2
ESP_OUTLINE = [(E, E), (BOARD_W - E, E), (BOARD_W - E, BOARD_H - E), (BARRIER_X + GAP, BOARD_H - E),
               (BARRIER_X + GAP, BARRIER_Y - GAP), (E, BARRIER_Y - GAP)]
BUS_OUTLINE = [(E, BARRIER_Y + GAP), (BARRIER_X - GAP, BARRIER_Y + GAP), (BARRIER_X - GAP, BOARD_H - E), (E, BOARD_H - E)]
for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
    for netname, outline in (('GND', ESP_OUTLINE), ('BGND', BUS_OUTLINE)):
        z = pcbnew.ZONE(B)
        z.SetLayer(layer)
        z.SetNet(net(netname))
        z.SetLocalClearance(mm(0.25))
        z.SetMinThickness(mm(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in outline:
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
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    B.Add(t)


def silk_line(pts, layer=pcbnew.F_SilkS, width=0.15):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        s = pcbnew.PCB_SHAPE(B)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(x1, y1))
        s.SetEnd(V(x2, y2))
        s.SetLayer(layer)
        s.SetWidth(mm(width))
        B.Add(s)


# the barrier, dashed, between the optocouplers' pad rows
for x0 in range(0, 36, 2):
    if not (0.5 < x0 < 9.5 or 9.5 < x0 < 18.5):    # skip under U5/U6 bodies
        silk_line([(x0 + 0.2, BARRIER_Y), (min(x0 + 1.2, BARRIER_X), BARRIER_Y)])
for y0 in range(29, 54, 2):
    if not (29 <= y0 <= 37):                         # skip under the DC-DC
        silk_line([(BARRIER_X, y0 + 0.2), (BARRIER_X, min(y0 + 1.2, BOARD_H - 0.6))])
# B0505S body outline (SIP stands upright; keep this area clear) and pin 1 mark
silk_line([(30.4, 30.0), (42.0, 30.0), (42.0, 36.0), (30.4, 36.0), (30.4, 30.0)])
silk('B0505S  1', 40.0, 30.9, 0.7)
silk('AISLADO / ISOLATED', 26.0, 27.4, 0.7)
silk('+ ROJO', 3.4, 41.2, 0.9, bold=True)
silk('- MARRON', 10.4, 41.2, 0.9, bold=True)
silk('RST', 3.6, 0.9, 0.7)
silk('BOOT', 10.6, 0.9, 0.7)
silk('USB-C 5V', 55.0, 24.5, 0.8)
silk('PWR', 49.5, 0.75, 0.6)
silk('v3', 46.0, 52.0, 0.9, bold=True)
BSILK = pcbnew.B_SilkS
silk('AIRE PANASONIC  R1/R2', 30.0, 3.6, 1.6, BSILK, bold=True)
silk('ESP32-C3  v3  ISOLATED  2026-11', 30.0, 6.2, 1.0, BSILK)

# ---------------------------------------------------------------- fill zones and save
filler = pcbnew.ZONE_FILLER(B)
filler.Fill(B.Zones())
B.Save(OUT)
import json
json.dump({
    'meta': {'filename': 'panasonic_rd_v3.kicad_pro', 'version': 1},
    'board': {'design_settings': {'rules': {
        'min_clearance': 0.15, 'min_track_width': 0.15, 'min_via_diameter': 0.5, 'min_via_annular_width': 0.1,
        'min_through_hole_diameter': 0.3, 'min_hole_clearance': 0.25, 'min_hole_to_hole': 0.25,
        'min_copper_edge_clearance': 0.3, 'min_silk_clearance': 0.0, 'min_text_height': 0.6, 'min_text_thickness': 0.1}}},
    'net_settings': {'classes': [{'name': 'Default', 'clearance': 0.15, 'track_width': 0.25, 'via_diameter': 0.5,
                                  'via_drill': 0.3, 'microvia_diameter': 0.3, 'microvia_drill': 0.1}], 'meta': {'version': 3}},
}, open(OUT.replace('.kicad_pcb', '.kicad_pro'), 'w'), indent=2)
print('wrote', OUT)
