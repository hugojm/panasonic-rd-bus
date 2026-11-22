# Bringing up a new unit: from first capture to Home Assistant

This is the path the W18BD3P went through. On another model, follow it to confirm the
bus and map your registers before enabling transmit. Each step has a check that tells you
whether to move on.

## 0. Measure (multimeter + scope)

1. AC off at the breaker. Find R1/R2 on the indoor unit (or on the back of the CZ-RD514C).
2. Power on. Measure R1-R2 DC, and each wire against earth (AC and DC).
3. Scope R1-R2 (differential, or one probe with its ground on the other wire if the
   scope is battery-powered). At 10 us/div, check the carrier frequency. At 20 ms/div,
   check the bit pattern (bursts with gaps of whole ~2 ms multiples).

**Check:** idle and low levels noted, so you can set the receive threshold in `hardware.md`.

## 1. Receive only

Build the receive half of the circuit in `hardware.md` (Q1). Flash the sniffer:

```bash
cd firmware
pio run -t upload && pio device monitor
```

Type `stats` after a minute. It prints the measured carrier frequency and bit time.
Set the bit time with `bit <us>` (it's applied immediately) and put it in the ESPHome
YAML later.

**Check:** single-byte `POLL` lines about every 155 ms, and `FRAME E3 …` lines marked
`[cs ok]` when you press buttons on the wall controller. If you see bytes but every
frame has `[cs BAD]` or `[parity/stop error]`, the bit time is off. Try `bursts` to
see raw burst lengths: they should be multiples of one bit time.

If the checksum never passes but bytes are stable, your unit may use a different
frame format from majid's CS-F50DD1E5. Capture anyway: the raw bytes are what
matter.

## 2. Who is the master?

- Power-cycle at the breaker while logging, to capture the start-up sequence
  (the ASCII-looking `E3 0A 6B 30 30 30 30 …` frames are likely identification).
- With the unit off at the breaker, disconnect the wall controller. Power on and log
  for a minute, then reconnect. If polls continue without the wall controller, the
  indoor unit is the master. (The unit may show a communication error code until
  the controller is back. That is expected.)

**Check:** you know which device sends the 0x80-0x9F polls.

## 3. Map the registers

Type a marker before each action, e.g. `m power on`, then press the button once and
wait 5 s. Do each of these:

- power on, power off
- every mode (note what the wall controller shows)
- every fan speed
- setpoint from minimum to maximum, one step at a time, noting the displayed
  temperature each time
- anything else the controller has (eco, vane, timer)

`state` prints the tracked registers. Fill this table:

| Register | Meaning | Values seen |
| --- | --- | --- |
| 0x60 | power | 0 = off, 1 = on |
| 0x61 | mode | |
| 0x62 | fan | |
| 0x63 | ? | |
| 0x64 | setpoint index | index → °C: |

**Check:** you can predict the frame for each button press. Please share the table
(issue or the HA thread) so other models get documented.

## 4. Transmit slot

On the W18BD3P the answer was: reply to poll `81` (unused sub-controller address), 44 ms
after it, like the wall controller does after poll `80`. Check that `81` is silent on your
bus (no `A6` replies after it) before using it.

## 5. First transmission

Build the transmit half (Q2, 220 Ω). Scope on the bus if you have one. In the sniffer:

```
carrier 19300        # use the value from `stats`
trigger 81
delay 44
arm
send 62 02           # a harmless fan change first (fan medium on a W18BD3P)
```

**Check, in order:**
1. Sniffer prints `^ our frame, echo OK`. Your signal is on the bus and decodes.
2. On the scope, your dips match the wall controller's depth.
3. The wall controller's display or the unit reacts. This is the real proof.

If 1 passes and 3 doesn't, compare your frame byte-for-byte and timing with the
wall controller's (inter-byte gaps, repeats).

## 6. ESPHome

Copy the calibrated values (bit time, carrier, setpoint base/step, mode and fan
values) into `esphome/panasonic-ac.yaml`. Leave `transmit: false` first and
check that the climate entity follows the wall controller in Home Assistant. Then
set `transmit: true`.
