# Hardware: R1/R2 interface for an ESP32

> **Safety.** Switch the AC off at the breaker before touching the indoor unit or the
> wall controller. On many indoor PCBs the R1/R2 terminals sit next to mains terminals.
> Before connecting anything, measure each bus wire against earth (AC and DC): you want a
> few volts at most. If you see mains-level voltages, stop.

## The proven circuit (breadboard and PCBs)

This is what runs on the W18BD3P, and what PCB v1/v2 implement. Two NPN transistors and
six resistors.

```
                 RECEIVE                                   TRANSMIT

 Bus + ──[10k]──┬── Q1 base (2N2222)        GPIO25 (TX) ──[1k]──┬── Q2 base (2N2222)
                │                                               │
              [680]                                           [10k]
                │                                               │
 Bus − ─────────┴── Q1 emitter ── GND       GND ────────────────┴── Q2 emitter
                    Q1 collector ──[1k]── GPIO26 (RX, internal pull-up on)
                                                                    Q2 collector ──[220]── Bus +
```

Bus − is the ESP32's ground. On the PCBs there is also an SMAJ24A TVS diode across the bus.

**Receive.** Q1 switches on when its base reaches ~0.65 V, i.e. at a bus voltage of about
0.65 × (10k + 680) / 680 ≈ 10.2 V: half-way between idle (15.2 V) and the carrier dips
(7.6 V). Idle = on, dips = off, so the collector toggles with the carrier and the firmware
measures edge timing. The 1k protects the GPIO; the bus loading is ~1.4 mA.

**Transmit.** The firmware drives GPIO25 with a 19.3 kHz, 50 % carrier during 0-bits. Q2
then pulls the bus down through 220 Ω, which makes dips as deep as the wall controller's.
1 kΩ was too weak on the W18BD3P. The 10k holds Q2 off while the ESP32 boots or resets,
so the transmitter is silent by default.

**Notes**

- **Not isolated.** Find which wire is + with a multimeter first (there is no bridge
  rectifier). While a laptop is connected over USB, run it on battery.
- **Never let the bus reach a GPIO directly.** 15 V on a GPIO destroys the pin (it
  happened to GPIO27 during development, along with the transistor in front of it). Keep the
  1k series resistors.
- Avoid input-only or strapping pins. On a classic ESP32 DevKit, GPIO26 (RX) and GPIO25
  (TX) work; on the ESP32-C3 PCBs, GPIO4 and GPIO5.
- For a different idle voltage, scale the 10k so the threshold sits half-way:
  `R_top ≈ 680 × (V_threshold / 0.65 − 1)`.

## Numbers this design is based on

| Quantity | Value | Source |
| --- | --- | --- |
| Idle bus voltage | ~15.2 V DC | scope, thread post 18 (a multimeter shows 11-12 V because it averages) |
| Line during carrier | pulled down to ~7.6 V | same |
| Carrier | 19.1-19.3 kHz from the wall controller; ~24 kHz from an Airzone gateway | measured on the W18BD3P |
| Bit time | 2.0 ms, 8E1, carrier = 0 | measured; agrees with thread post 54 |

Other units in the thread differ (one reported up to 31 V with 100 Hz ripple), so
**measure yours first**.

## Alternative: isolated interface (designed, not built)

If you'd rather keep the ESP32 galvanically separate from the bus, this version uses two
optocouplers and an isolated DC-DC. It has not been built or tested.

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
                                                     |   H11L1 pin4 OUT ──┬── GPIO26
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

- **Receive.** The H11L1's LED conducts only while the bus is above about
  `Vz + 1.2 V + 1 mA × 1k` (~10.4 V after the bridge), so its output toggles at the
  carrier frequency during every 0-bit. It has a Schmitt-trigger output and switches in
  ~1 µs; a PC817 is too slow for a 20 kHz carrier.
- **Transmit.** GPIO25 HIGH lights the 6N137, the BC547 turns off, the 2N7000 switches on
  and `R_TX` pulls the bus down. Unpowered or idle, the 2N7000 stays off.
- **Zener:** `Vz ≈ (V_idle + V_low) / 2 − 1.4 V (bridge) − 1.2 V (LED) − 1 V`; 7.5-8.2 V
  for 15.2 V / 7.6 V.
- **R_TX:** start at 1 kΩ and lower it (680, 470, 330, 220 Ω) until your dips on a scope
  match the wall controller's. Don't go deeper than the wall controller does.

Parts: MB6S bridge, H11L1, 6N137, B0505S-1W, 2N7000, BC547, 8.2 V zener, resistors
(220R, 1k × 3, 4.7k × 4), 2 × 100 nF.
