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
- Each command frame is sent 3 times, 88.5 ms apart.
- State goes out only on change. Idle polls look the same whether the unit is on or off.

## Registers (guess, from post 54)

| Frame | Meaning |
| --- | --- |
| `E3 02 60 01 3A` / `E3 02 60 00 3B` | power on / off |
| `E3 02 62 0v CS` | fan, v = 3/2/1 (high/med/low?), 8 (auto?) |
| `E3 02 64 0i CS` | setpoint *index*, 0-4 seen; mapping to °C unknown |
| `E3 0C 60 21 61 22 62 28 63 28 64 21 49 20 0A` | state dump: (reg, 0x20 + value) pairs |
| `E3 0A 6B 30 30 30 30 48 02 0F 4B 20 24` | unknown, ASCII-like ("0000"), maybe identification |

## Open questions

1. Which device polls (the test plan's step 2 answers this).
2. Mode values (register 0x61) and setpoint index → °C.
3. Inter-byte timing inside frames, and how the wall controller picks its
   transmit slot.
4. Whether the indoor unit accepts a second controller's frames, and from which
   address. The PACi bus distinguishes the wall controller (0x40) from an
   adaptor (0xE0). If this bus does something similar, frames may carry a
   source we haven't recognised yet.
