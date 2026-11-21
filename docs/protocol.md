# What is known about the bus (2026-11-21)

Units: Panasonic residential ducted (W18BD3P, CS-F50DD1E5 and likely the
CU-LxxDBE5 family) with a CZ-RD514C-type wired controller on R1/R2. This is
**not** the PACi CZ-RTC bus that
[rndm2/esphome_panasonic_paci](https://github.com/rndm2/esphome_panasonic_paci)
supports. That bus runs at 2400 baud 8E1 with an XOR checksum, behind Panasonic's
CZ-CAPWFC1 bridge.

Confidence: **confirmed** = measured on more than one unit or checked
independently; **likely** = one capture set; **guess** = interpretation.

## Physical layer

| Item | Value | Confidence |
| --- | --- | --- |
| Medium | 2 wires, polarity-free, DC-powered (~15 V idle on a W18BD3P) | confirmed |
| Modulation | on/off keying of a ~19-24 kHz carrier; carrier = 0, silence = 1 | likely (posts 18, 45) |
| Bit rate | ~2.02 ms per bit (~495 baud) | likely (post 54) |
| Characters | 8E1, LSB first | likely (post 54) |

Your scope's "Manchester, ~21 us half-cell" (post 18) is most likely the carrier
itself, seen at a fine timebase. Taken that way, it agrees with majid's
~19 kHz carrier.

### Why the March 2026 "1200 baud 8N1 inverted" result is unreliable

The old sniffer read the bus through a 10k/3.3k divider into a hardware UART at
1200 baud. Problems:

- Idle 15.2 V becomes 3.77 V (above the ESP32's 3.6 V limit), and the 7.6 V carrier
  dips become 1.9 V, between the input's valid low and high. So the input saw the carrier
  only some of the time.
- A UART oversamples at 16 × 1200 = 19.2 kHz, about the carrier frequency, so the
  samples aliased.
- The decoded bytes are almost all built only from bits 3, 4 and 7
  (`00 08 80 88 90 98`), which looks like aliasing, not data.

What the old captures do show correctly is timing: bursts every ~155 ms, the same
poll interval as post 54. That's good evidence that your unit runs the same bus
as majid's. The fan-speed table in the old `PROTOCOL.md` probably follows the real
state through a consistent alias. Don't reuse its byte values.

`test/test_rdbus.cpp` shows this: the same synthetic traffic decoded at 1200 baud
recovers no valid frames.

## Link layer (post 54, AI-assisted, one unit)

- Polls: single bytes cycling `80 81 90 91 … 9F`, one every ~155 ms. `80` and
  `90` get a one-byte reply `A6`. Guess: `80/81` = main/sub controller, `90-9F` =
  indoor units.
- Frames: `E3 LEN payload[LEN] CS`, with `(sum of all bytes) & 0x7F == 0`.
  **Confirmed**: every frame quoted in post 54 passes (checked in the tests), which
  is unlikely by chance for 13 frames.
- Each command frame is sent 3 times, ~177 ms apart start to start (88.5 ms of silence between copies).
- State goes out only on change. Idle polls look the same whether the unit is on or off.

## Registers (confirmed on a W18BD3P + CZ-RD514C, 2026-11-21)

Captured with the sniffer while pressing each button and noting the display.

| Register | Meaning | Values |
| --- | --- | --- |
| `0x60` | power | 0 = off, 1 = on |
| `0x61` | mode | 1 = heat, 2 = cool, 3 = fan, 4 = dry, 8 = auto |
| `0x62` | fan | 1 = high, 2 = medium, 3 = low, 8 = auto (the reverse of post 54's guess) |
| `0x63` | vane | always 8 on this ducted unit ("not available") |
| `0x64` | setpoint | index; °C = index + 16 (22 °C = 6, 25 °C = 9) |
| `0x66` | filter | 1 = clean the filter. The indoor unit reports it (`E1 02 66 01 36`); the remote's reset sends `E3 02 66 00 35`, and the unit confirms with `E1 02 66 00 37` |

Command example: `E3 02 64 07 30` sets 23 °C. State dumps such as
`E3 0C 60 21 61 22 62 28 63 28 64 26 49 20 0C` carry (reg, 0x20 + value) pairs:
on, cool, fan auto, vane 8, 22 °C.

Also seen, meaning unknown:

- **`E1` frames come from the indoor unit and `E3` frames from the wall controller**
  (confirmed by the filter reset). Unknown `E1` frames: `E1 03 70 00 00 2C`,
  `E1 02 53 00 4A`, `E1 05 53 00 70 00 00 57`.
- `E3 0C 68 00 6B 30 30 30 30 48 02 0D 50 13 44`: ASCII-like, sent with state dumps.
- `E3 0C 65 20 61 22 62 21 64 26 63 28 68 00 09`: an alternative dump ordering.

Buttons mapped one at a time (2026-11-21): OFF/ON, OPERATION, FAN SPEED, TEMP ▲/▼ and
FILTER RESET send frames. **TIMER (SELECT, ▲/▼, SET, CANCEL), CLOCK, CHECK and A/C No.
send nothing**: the controller keeps its clock and timers to itself and, when a timer
fires, sends an ordinary power command. In Home Assistant, use automations instead.
`D0 02 50 14 4A` plus a power value of 5 (`E3 02 60 05 36`) appeared once, while power
was toggled with an OFF timer (13:20) armed. Probably a "timer armed" status; not needed.

Housekeeping, about every 60 s: controller dumps `E3 0C 68 …` and `E3 0C 60 …`, then the
indoor unit sends `E1 02 53 00 4A` and `E1 03 70 00 00 2C`.

Bus devices on this install: wall controller (answers poll 0x80), an **Airzone** zoning
gateway (probably poll 0x90; its `A6` replies use a ~24 kHz carrier vs ~19 kHz), and the
ESP32, which answers the otherwise silent poll 0x81.

Timing: polls every 154.6 ms; `A6` replies 44 ms after polls `80` and `90`;
2-byte command frames repeated 3× at 176.7 ms; 12-byte dumps repeated 3× at 397.6 ms.
Carrier measured at 19.1-19.3 kHz.

## Open questions

1. Which device polls (the test plan's step 2 answers this).
2. What the `E1` frames and registers `0x49`, `0x65`, `0x68`, `0x6B` mean.
3. Inter-byte timing inside frames, and how the wall controller picks its
   transmit slot.
4. Whether the indoor unit accepts a second controller's frames, and from which
   address. The PACi bus distinguishes the wall controller (0x40) from an
   adaptor (0xE0). If this bus does something similar, frames may carry a
   source we haven't recognised yet.
