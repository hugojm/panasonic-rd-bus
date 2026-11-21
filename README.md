# panasonic-rd-bus

Local Home Assistant control for Panasonic **residential ducted** units that only
have a 2-wire wired controller (R1/R2, CZ-RD514C family). These units have no
CN-CNT port, so they can't use the usual Panasonic ESPHome projects. Developed for a
W18BD3P, following the HA community thread
[Panasonic PACi / commercial unit wired controller protocol](https://community.home-assistant.io/t/panasonic-paci-commercial-unit-wired-controller-protocol-2-wire-bus-anyone-working-on-this/996275).

**Status: tooling done; the protocol is not yet confirmed on this unit.** The
decoder works on synthetic traffic built from the community's captures. The next
step is a capture on real hardware (see `docs/test-plan.md`).

> Have a PACi (commercial) unit with a CZ-RTC controller instead? Use
> [rndm2/esphome_panasonic_paci](https://github.com/rndm2/esphome_panasonic_paci)
> with a CZ-CAPWFC1 bridge. That one is a different, already-working protocol.

## How the bus works

The bus carries ~15 V DC. A sender pulls the line down with a ~19-24 kHz
carrier for each 0-bit and leaves it alone for 1-bits. That gives ~495 baud, 8E1
characters. On top of that are single-byte polls and `E3 LEN payload CS` frames with
a 7-bit sum checksum. Details and confidence levels are in `docs/protocol.md`.

The software demodulates the carrier from edge timing in an interrupt. It does not
rely on a hardware UART, which is what produced aliased garbage in earlier
attempts.

## What's here

| Path | What |
| --- | --- |
| `esphome/components/panasonic_rd/rdbus.h` | protocol core: envelope detection, 8E1 decoding, frames, checksum, transmit scheduling. No platform dependencies |
| `esphome/components/panasonic_rd/rdbus_esp32.h` | ESP32 receive (IRAM interrupt) and transmit (LEDC carrier gated by esp_timer) |
| `esphome/components/panasonic_rd/` | ESPHome climate component (listen-only by default) |
| `esphome/panasonic-ac.yaml` | example config |
| `firmware/` | PlatformIO serial sniffer with markers, stats, and armed transmit commands |
| `tools/decode_capture.py` | decode PulseView/sigrok CSV captures with the same algorithm |
| `test/` | native tests (`make -C test`) |
| `docs/hardware.md` | isolated interface schematic and parts |
| `docs/test-plan.md` | step-by-step from first capture to Home Assistant |

## Quick start

```bash
make -C test                                   # native tests
python3 tools/decode_capture.py --selftest

cd firmware && pio run -t upload && pio device monitor   # sniffer, then type `help`

cd esphome && esphome run panasonic-ac.yaml    # once calibrated
```

Transmit is off everywhere by default. In the sniffer it needs `arm`; in ESPHome it
needs `transmit: true`.
