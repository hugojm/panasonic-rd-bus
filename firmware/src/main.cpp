// Panasonic R1/R2 bus sniffer + experimental transmitter (ESP32, Arduino).
//
// Type `help` in the serial monitor (115200 baud, send on Enter).
#include <Arduino.h>

#include "rdbus.h"
#include "rdbus_esp32.h"

using namespace rdbus;

#ifndef RX_PIN
#define RX_PIN 27  // receiver transistor/opto collector, external 10k pull-up to 3V3
#endif
// GPIO34-39 are input-only without pull-ups; elsewhere add the internal one as a backup.
#define RX_INTERNAL_PULLUP (RX_PIN < 34)
#ifndef TX_PIN
#define TX_PIN 25  // drives the 6N137 LED via 220 ohm; HIGH = pull the bus
#endif

static Receiver rx;
static Transmitter tx;
static ByteDecoder dec;
static FrameAssembler fa;
static BusStats stats;
static TxScheduler sched;
static UnitState state;

static bool show_bursts = false;
static bool show_polls = true;
static bool armed = false;
static bool tx_ready = false;
static uint32_t carrier_hz = 19200;
static uint32_t last_msg_us = 0;
static String line;

static void print_hex(const uint8_t *d, size_t n) {
  for (size_t i = 0; i < n; i++)
    Serial.printf("%02X ", d[i]);
}

static void print_state() {
  Serial.printf("  state: power=%d mode=%d fan=%d vane=%d setpoint_idx=%d\n", state.reg[kRegPower],
                state.reg[kRegMode], state.reg[kRegFan], state.reg[kRegVane], state.reg[kRegSetpoint]);
}

static void on_message(const Message &m) {
  switch (sched.on_message(m)) {
    case TxScheduler::Event::SENT_OK:
      Serial.println("  ^ our frame, echo OK");
      break;
    case TxScheduler::Event::COLLISION:
      Serial.println("  ^ echo mismatch: collision, will retry");
      break;
    case TxScheduler::Event::GAVE_UP:
      Serial.println("  ^ echo mismatch: giving up on this frame");
      break;
    default:
      break;
  }
  const uint32_t dt = m.t_us - last_msg_us;
  last_msg_us = m.t_us;
  if (m.kind == MsgKind::POLL && !show_polls && !m.rx_error)
    return;
  Serial.printf("%10.3f +%6.1fms %-5s ", m.t_us / 1000.0, dt / 1000.0, kind_name(m.kind));
  print_hex(m.data, m.len);
  if (m.len > 1)
    Serial.print(m.checksum_ok ? " [cs ok]" : " [cs BAD]");
  if (m.rx_error)
    Serial.print(" [parity/stop error]");
  Serial.println();
  if (apply_frame(m, &state))
    print_state();
}

static void print_stats() {
  Serial.printf("bursts=%u edges=%u ring_overflows=%u\n", stats.bursts(), rx.edges(), rx.overflows());
  Serial.printf("carrier ~ %.0f Hz   bit time ~ %.0f us (decoder uses %u us)\n", stats.carrier_hz(), stats.bit_us(),
                dec.bit_us());
}

static void help() {
  Serial.println(
      "commands:\n"
      "  m <text>        print a marker line (do this before each button press)\n"
      "  stats           measured carrier frequency and bit time\n"
      "  bit <us>        set decoder bit time (default 2020)\n"
      "  bursts          toggle raw burst printing (start, length, edges)\n"
      "  polls           toggle printing of single-byte polls\n"
      "  state           print tracked register state\n"
      "  carrier <hz>    set transmit carrier (use the measured value)\n"
      "  arm / disarm    enable or disable transmit\n"
      "  send <reg> <val>  send E3 02 reg val CS three times (hex), e.g. send 60 01\n"
      "  raw <hex...>    send bytes exactly as given, once, e.g. raw E3 02 60 01 3A\n"
      "  trigger <hex|off>  only transmit right after this single-byte message\n"
      "  delay <ms>      with a trigger: answer exactly this long after it (remote uses 44)\n");
}

static size_t parse_hex(const String &s, uint8_t *out, size_t max) {
  size_t n = 0;
  int i = 0;
  while (i < (int) s.length() && n < max) {
    while (i < (int) s.length() && s[i] == ' ')
      i++;
    if (i >= (int) s.length())
      break;
    char *end;
    long v = strtol(s.c_str() + i, &end, 16);
    int used = end - (s.c_str() + i);
    if (used == 0 || v < 0 || v > 255)
      return 0;
    out[n++] = (uint8_t) v;
    i += used;
  }
  return n;
}

static void queue_tx(const uint8_t *b, size_t n, uint8_t sends) {
  if (!tx_ready) {
    Serial.println("transmitter not initialised");
    return;
  }
  if (!armed) {
    Serial.println("not armed: type `arm` first (read docs/test-plan.md)");
    return;
  }
  if (!sched.enqueue(b, n, sends)) {
    Serial.println("queue full");
    return;
  }
  Serial.print("queued: ");
  print_hex(b, n);
  Serial.printf("x%u\n", sends);
}

static void command(String c) {
  c.trim();
  if (c.isEmpty())
    return;
  String arg;
  int sp = c.indexOf(' ');
  String cmd = sp < 0 ? c : c.substring(0, sp);
  if (sp >= 0)
    arg = c.substring(sp + 1);
  if (cmd == "help") {
    help();
  } else if (cmd == "m") {
    Serial.printf("\n==== %10.3f MARK: %s ====\n", (uint32_t) esp_timer_get_time() / 1000.0, arg.c_str());
  } else if (cmd == "stats") {
    print_stats();
  } else if (cmd == "bit") {
    dec.set_bit_us(arg.toInt());
    Serial.printf("bit time %u us\n", dec.bit_us());
  } else if (cmd == "bursts") {
    show_bursts = !show_bursts;
  } else if (cmd == "polls") {
    show_polls = !show_polls;
  } else if (cmd == "state") {
    print_state();
  } else if (cmd == "carrier") {
    carrier_hz = arg.toInt();
    Serial.println(tx.set_carrier_hz(carrier_hz) ? "ok" : "failed (busy?)");
  } else if (cmd == "arm") {
    armed = true;
    Serial.printf("ARMED. carrier %u Hz, bit %u us\n", carrier_hz, dec.bit_us());
  } else if (cmd == "disarm") {
    armed = false;
    Serial.println("disarmed");
  } else if (cmd == "send") {
    uint8_t rv[2], frame[kMaxMsg];
    if (parse_hex(arg, rv, 2) != 2) {
      Serial.println("usage: send <reg> <val>   (hex)");
      return;
    }
    size_t n = build_frame(rv, 2, frame, sizeof frame);
    queue_tx(frame, n, 3);
  } else if (cmd == "raw") {
    uint8_t b[kMaxMsg];
    size_t n = parse_hex(arg, b, sizeof b);
    if (!n) {
      Serial.println("usage: raw <hex bytes>");
      return;
    }
    queue_tx(b, n, 1);
  } else if (cmd == "hold") {
    // Diagnostic: continuous carrier for N ms, to check the TX stage reaches the bus.
    if (!armed || !tx_ready) {
      Serial.println("arm first");
      return;
    }
    Segment s{true, (uint32_t) arg.toInt() * 1000};
    Serial.println(tx.send(&s, 1) ? "carrier on" : "transmitter busy");
  } else if (cmd == "delay") {
    sched.set_reply_delay_us((uint32_t) (arg.toFloat() * 1000));
    Serial.printf("reply delay %.1f ms after the trigger byte starts\n", arg.toFloat());
  } else if (cmd == "trigger") {
    if (arg == "off") {
      sched.set_trigger(-1);
    } else {
      uint8_t b;
      if (parse_hex(arg, &b, 1) == 1)
        sched.set_trigger(b);
    }
    Serial.println("ok");
  } else {
    Serial.println("unknown command; type help");
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  if (!rx.begin((gpio_num_t) RX_PIN, RX_INTERNAL_PULLUP))
    Serial.println("RX init failed");
  tx_ready = tx.begin((gpio_num_t) TX_PIN, carrier_hz);
  Serial.printf("\nPanasonic R1/R2 bus sniffer. RX GPIO%d, TX GPIO%d%s\n", RX_PIN, TX_PIN,
                tx_ready ? "" : " (TX init failed)");
  Serial.println("Transmit is DISARMED. Type `help`.\n");
}

void loop() {
  RxByte rb[8];
  Message msg[4];
  Burst b;
  const uint32_t now = (uint32_t) esp_timer_get_time();

  const uint32_t known = rx.service(now);
  while (rx.pop(&b)) {
    stats.add(b);
    if (show_bursts)
      Serial.printf("  burst %10.3f  %5u us  %4u edges\n", b.start_us / 1000.0, b.end_us - b.start_us, b.edges);
    size_t nb = dec.push(b, rb, 8);
    for (size_t i = 0; i < nb; i++) {
      size_t nm = fa.push(rb[i], msg);
      for (size_t j = 0; j < nm; j++)
        on_message(msg[j]);
    }
  }
  size_t nb = dec.flush(known, rb, 8);
  for (size_t i = 0; i < nb; i++) {
    size_t nm = fa.push(rb[i], msg);
    for (size_t j = 0; j < nm; j++)
      on_message(msg[j]);
  }
  size_t nm = fa.flush(now, msg);
  for (size_t j = 0; j < nm; j++)
    on_message(msg[j]);

  // Transmit
  if (armed && tx_ready) {
    const auto *pending = sched.current();
    if (pending && sched.poll(now, TxScheduler::echo_timeout_us(*pending, dec.bit_us())) != TxScheduler::Event::NONE)
      Serial.println("  ! no echo of our frame (is the TX stage connected?)");
    if (sched.should_start(now, rx.last_edge(), tx.busy())) {
      const auto *job = sched.current();
      static Segment seg[Transmitter::kMaxSeg];
      size_t n = encode_bytes(job->bytes, job->len, dec.bit_us(), Parity::EVEN, 0, seg, Transmitter::kMaxSeg);
      if (!tx.send(seg, n))
        Serial.println("  ! transmitter refused");
    }
  }

  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r' || ch == '\n') {
      command(line);
      line = "";
    } else if (line.length() < 120) {
      line += ch;
    }
  }
}
