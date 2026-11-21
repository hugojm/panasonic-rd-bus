# Hardware: isolated R1/R2 interface for an ESP32

Two optocoupled channels: a receiver that turns carrier bursts into edges, and a
transmitter that shunts the bus through a resistor at the carrier frequency, the
way the wall controller's transistor stage does. The ESP32 never shares a ground
with the bus.

> **Safety.** Switch the AC off at the breaker before touching the indoor unit.
> On many indoor PCBs the R1/R2 terminals sit next to mains terminals. Before
> connecting anything, measure each bus wire against earth (AC and DC): you want
> a few volts at most. If you see mains-level voltages, stop.

## Numbers this design is based on

| Quantity | Value | Source |
| --- | --- | --- |
| Idle bus voltage | ~15.2 V DC | your scope, thread post 18 (multimeter shows 11-12 V because it averages) |
| Line during carrier | pulled down to ~7.6 V | same |
| Carrier | ~19-24 kHz (half period ~21-26 us) | post 18 (your "21 us half-cell") and post 45 (19.2 kHz) |
| Bit time | ~2.02 ms, 8E1, carrier = 0 | post 54 (majid's captures) |
| Polarity | none (the bus is polarity-free) | Intesis INMBSPAN001R000 manual |

Other units in the thread differ (one reported up to 31 V with 100 Hz ripple), so
**measure yours first** and adjust the zener (below).

## Schematic

```
                 BUS SIDE (floating)                 |        ESP32 SIDE
                                                     |
 R1 ─┐   ┌──────────┐                                |
     ├───┤ ~      + ├──── +V  (~13.8 V idle after    |
 R2 ─┘   │  bridge  │          the bridge)           |
         │ MB6S     │                                |
         │ ~      - ├──── -V                         |
         └──────────┘                                |
                                                     |
 RECEIVE                                             |
   +V ──[1k]──┤◄── 8.2 V zener ──► H11L1 pin1 (A)    |   H11L1 pin6 Vcc ── 3V3  (100 nF to GND)
                                   H11L1 pin2 (K) ── -V   H11L1 pin5 GND ── GND
                                                     |   H11L1 pin4 OUT ──┬── GPIO34
                                                     |                    └─[4.7k]── 3V3
                                                     |
 TRANSMIT                                            |
   +5Viso ── B0505S out (+)        B0505S in (+) ────┼── 5V (VIN)
   -V     ── B0505S out (-)        B0505S in (-) ────┼── GND
                                                     |
   6N137 pin8 Vcc ── +5Viso ;  pin7 VE ── +5Viso     |   GPIO25 ──[220R]── 6N137 pin2 (A)
   6N137 pin5 GND ── -V ; 100 nF pin8-pin5           |   6N137 pin3 (K) ── GND
   6N137 pin6 OUT ──┬──[1k]── +5Viso                 |
                    └──[4.7k]── BC547 base           |
   BC547 emitter ── -V                               |
   BC547 collector ──┬──[4.7k]── +5Viso              |
                     └── 2N7000 gate                 |
   2N7000 source ── -V                               |
   2N7000 drain ──[R_TX]── +V                        |
```

Zener orientation: cathode towards `+V` (it is reverse-biased in normal use).

### How it works

**Receive.** Current flows through the H11L1's LED only while the bus is above
about `Vz + 1.2 V + 1 mA * 1k`, roughly 10.4 V after the bridge. Idle (13.8 V) turns
the LED on and the carrier dips (~6.2 V) turn it off, so the H11L1 output toggles at
the carrier frequency during every 0-bit. The firmware only looks at edge spacing,
so the output polarity does not matter. The H11L1 has a Schmitt-trigger output and
switches in about 1 us. A PC817 is too slow for a 20 kHz carrier, which is probably
why some captures in the thread changed shape when people swapped resistors.

**Transmit.** GPIO25 HIGH lights the 6N137, its output goes low, the BC547
turns off, the gate pull-up switches the 2N7000 on, and `R_TX` pulls the bus
down. The firmware drives GPIO25 with a 50 % carrier during 0-bits. If the ESP32
is unpowered, resetting or idle (GPIO LOW), the 6N137 output is high, the BC547
holds the gate low and the bus is left alone. If the B0505S is unpowered the gate
has no supply at all. So the transmitter fails safe.

### Choosing the zener

You want the threshold half-way between idle and the carrier dips, after the
bridge's ~1.4 V drop:

```
Vz ~= (V_idle + V_low) / 2 - 1.4 V (bridge) - 1.2 V (LED) - 1 V (1 mA in 1k)
```

| Bus idle / low | Zener |
| --- | --- |
| 15.2 V / 7.6 V (W18BD3P) | 7.5-8.2 V |
| 12 V / 6 V | 5.6 V |
| ~30 V with ripple | measure the dips first; use a comparator if the ripple is close to the swing |

### Choosing R_TX

Start with **R_TX = 1 kΩ** (about 14 mA at 14 V; a 2N7000 is fine up to 200 mA).
Put the scope on R1/R2, send a frame, and compare your dips with the wall
controller's. Lower R_TX (680, 470, 330 Ω) until yours reach the same level
(~7.6 V on a W18BD3P). Don't go deeper than the wall controller does. If the dips
reach your own receiver's threshold, the firmware reports "echo OK".

## Zero-cost receiver (parts from a transistor + resistor kit)

You can capture traffic before buying anything. One NPN transistor acts as the
threshold detector:

```
 Bus + ──[10k]──┬── base   2N2222 / BC547 / 2N3904
                │
              [680R]
                │
 Bus − ─────────┴── emitter ── ESP32 GND
                    collector ──┬── GPIO34
                                └─[10k]── 3V3
```

- The transistor switches on when its base reaches ~0.65 V. That happens at a bus
  voltage of about 0.65 × (10k + 680) / 680 ≈ 10.2 V, half-way between idle
  (15.2 V) and the carrier dips (7.6 V). At idle it is fully on. In the dips it is
  off. So the collector toggles with the carrier. Polarity doesn't matter to the
  firmware.
- **This version is not isolated:** the ESP32's ground is bus −. Find which wire
  is + with a multimeter first (there is no bridge). Check that neither wire shows
  more than a few volts to earth. While connected, run the laptop on battery with
  its charger unplugged.
- The bus loading is ~1.4 mA, about the same as the opto version.
- For another idle voltage, scale the 10k so the threshold sits half-way:
  `R_top ≈ 680 × (V_threshold / 0.65 − 1)`.

Once frames decode with `[cs ok]`, buy the isolated parts below. Ordering them
together from one EU shop avoids the per-parcel import fees AliExpress adds.

## Parts

| Part | Qty | Notes |
| --- | --- | --- |
| ESP32 DevKit (the one you have) | 1 | any ESP32/S3/C3 works; adjust pins |
| MB6S or DB107 bridge rectifier | 1 | |
| H11L1 optocoupler | 1 | Schmitt output, 1 MHz. Not a PC817 |
| 6N137 optocoupler | 1 | 10 MBd |
| B0505S-1W isolated DC-DC | 1 | powers the bus side of the transmitter |
| 2N7000 (or BS170) | 1 | |
| BC547 (or 2N3904) | 1 | |
| 8.2 V zener, 0.5 W | 1 | see table |
| Resistors | | 220R, 1k ×3 (incl. R_TX), 4.7k ×4 |
| 100 nF ceramic | 2 | |
| Screw terminals, perfboard | | |

Receive-only first: you can build the bridge + zener + H11L1 part alone and leave
the transmit half for later.
