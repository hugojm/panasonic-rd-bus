# How I got Home Assistant to talk to my Panasonic ducted AC over its 2-wire bus

*Hugo Jiménez, November 2026*

My flat has a Panasonic ducted air conditioner (W18BD3P) with a CZ-RD514C wall controller.
I wanted it in Home Assistant: local, no cloud, and two-way, so Home Assistant knows when
someone changes it from the wall. The usual Panasonic ESPHome projects need a CN-CNT
connector on the indoor unit. This one doesn't have one. The only way in is the two wires,
R1 and R2, that run from the indoor unit to the wall controller.

I asked on the Home Assistant forum. A few people had scoped the bus and shared captures,
but nobody had it working. Here is how it went from "two wires and a mystery" to a climate
entity on my iPad dashboard.

<!-- PHOTO: the wall controller, and the breadboard next to it -->

## 1. The first attempt read garbage

My first try, months earlier, treated the bus like a serial port: a resistor divider into the
ESP32's UART at 1200 baud. It printed bytes, and even something that looked like a fan
speed table. It was wrong.

The bus isn't a plain serial line. It sits at ~15 V, and a device "talks" by pulling it down
with a **~19 kHz carrier** for each 0-bit and leaving it alone for each 1-bit. A UART
sampling at 16 × 1200 = 19.2 kHz is sampling at almost exactly the carrier frequency, so
it aliased: the "bytes" were patterns of the carrier, not data. Almost every one was built
from the same three bits.

## 2. Listening properly

The fix was to stop pretending it's a UART. The ESP32 timestamps every edge in an
interrupt. An envelope detector turns "edges closer than 0.5 ms" into "carrier on", and a
decoder turns carrier on/off into **2 ms bits, 8 data bits, even parity, 1 stop bit**.
Frames look like `E3 LEN payload CS`, where all bytes summed, masked to 7 bits, equal 0.
Every frame a forum member had posted passed that checksum, which is very unlikely by
chance. That was the first sign the format was right.

For the hardware I didn't need to buy anything. One NPN transistor and two resistors make
a threshold detector: the 10k/680 Ω divider turns the transistor on above ~10 V. The bus
idles at 15 V and dips to ~7.6 V during the carrier, so the transistor follows the carrier
and the ESP32 sees clean edges. (I nearly ordered €44 of optocouplers from AliExpress,
€30 of it import fees, before realising a transistor kit would do.)

<!-- PHOTO: the one-transistor receiver on the breadboard -->

## 3. The first real capture

Once the wiring was right, the log filled with this:

```
POLL 80 → A6     POLL 81     POLL 90 → A6     POLL 91 … POLL 9F     (every 154.6 ms)
FRAME E3 02 64 07 30  [cs ok]          ← pressing TEMP ▲
```

Something polls addresses `80`, `81`, `90`…`9F` all day. The wall controller answers `80`
with `A6`, 44 ms later. Something else answers `90`, on a slightly different carrier
(~24 kHz): most likely the **Airzone** zoning gateway that also sits on my bus.

## 4. Mapping the buttons, one at a time

Then the slow part: press one button, wait, write down what the display shows, repeat. The
sniffer lets you type a marker (`m fan medium`) so the log stays readable. The result:

| Register | Meaning | Values |
| --- | --- | --- |
| `60` | power | 0 off, 1 on |
| `61` | mode | 1 heat, 2 cool, 3 fan, 4 dry, 8 auto |
| `62` | fan | 1 high, 2 medium, 3 low, 8 auto |
| `64` | setpoint | °C = value + 16 |
| `66` | filter | 1 = "clean the filter" |

So `E3 02 64 07 30` means "23 °C". Some surprises along the way:

- **Timer, clock, CHECK and A/C No. send nothing.** The wall controller keeps its clock and
  timers to itself, and when a timer fires it just sends an ordinary power command. Home
  Assistant automations replace all of that.
- **`E3` is the wall controller and `E1` is the indoor unit.** The filter warning proved it:
  the unit reports `E1 02 66 01 36`, the remote's reset sends `E3 02 66 00 35`, and the unit
  confirms with `E1 02 66 00 37`. That gave me a "filter needs cleaning" sensor and a reset
  button for free.

## 5. Talking back

Receiving is safe. Transmitting means putting your own carrier on the bus of a machine you
care about, so it took a few careful rounds:

- **Too weak.** A 1 kΩ pull-down made dips the receiver could barely see. 220 Ω matched the
  wall controller's depth.
- **Wrong moment.** Sending in a quiet gap collided with other traffic. The bus has a
  schedule, and the wall controller only ever speaks 44 ms after poll `80`.
- **The answer:** poll `81` is the address for a *second* wall controller, and nobody answers
  it on my install. So the ESP32 answers poll `81`, 44 ms later, exactly like a second
  controller would.

The first command, `E3 02 62 02 37` (fan → medium), changed the unit and the wall
controller's display followed. That was the moment it worked.

<!-- PHOTO or VIDEO: wall controller display changing when Home Assistant sends a command -->

Getting this into ESPHome had one more trap. The window to start a reply is a few
milliseconds wide, and ESPHome's main loop runs every ~16 ms, so it kept missing it. The
fix was to compute the exact start time when the poll arrives and start the carrier from a
hardware timer instead of the loop.

Along the way I also lost one ESP32 pin and a transistor when 15 V from the bus reached
them. Keep a resistor between the bus side and every GPIO.

## 6. In Home Assistant

The ESPHome component exposes a normal **climate entity** (power, mode, fan, setpoint),
plus the filter sensor and reset button. Because it reads the bus, changes made at the wall
controller show up in Home Assistant within a second or so.

One detail made it feel right: the indoor unit takes a moment to confirm a change, while
the wall controller updates its own display instantly. So the entity now shows the
requested state immediately and then follows what the unit reports, which makes it feel
as quick as the wall controller.

<!-- SCREENSHOT: the climate tile on the dashboard -->

## 7. From breadboard to a factory board

A breadboard behind the wall controller isn't a permanent solution, so I designed a small
board (60 × 46 mm): an ESP32-C3 module, USB-C, the same two-transistor circuit, a TVS diode
and a screw terminal for the bus wires. The layout is generated by a Python script against
KiCad's API, checked with KiCad's design-rule check, and exported as Gerber/BOM/placement
files for JLCPCB to assemble.

JLCPCB's placement preview was worth checking. It showed the voltage regulator rotated
180° (it would have shorted the 5 V supply), the transistors and the USB protection chip
turned the wrong way, and the two buttons left out of the order. All of that was fixed
before paying. Five assembled boards cost about $77 with shipping (plus import VAT), and
they're on their way.

<!-- IMAGE: hardware/pcb/fab/preview_top.png -->

## 8. What's next

- **v2, powered by the bus itself.** No USB charger: the board draws a steady,
  current-limited ~19 mA from the bus into two capacitors, and a buck converter makes
  3.3 V. Wi-Fi waits until the capacitors are charged. It's designed but not built yet.
- **Other models.** This is confirmed on one W18BD3P. If you have a Panasonic ducted unit
  with a CZ-RD514C-type controller, the sniffer in the repo will tell you in five minutes
  whether your bus looks the same. Please share what you find.

## Get it

Everything is open: the ESPHome component, the sniffer, the protocol notes, and the board
files. **github.com/hugojm/panasonic-rd-bus**

Thanks to everyone in the
[Home Assistant forum thread](https://community.home-assistant.io/t/panasonic-paci-commercial-unit-wired-controller-protocol-2-wire-bus-anyone-working-on-this/996275)
who shared scope shots and captures. They made the first decode possible.

*Not affiliated with Panasonic. Connecting to your AC's control bus is at your own risk;
switch it off at the breaker before touching the wiring.*
