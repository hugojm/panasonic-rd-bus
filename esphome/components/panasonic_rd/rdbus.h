// rdbus.h - platform-independent decoder/encoder for the Panasonic residential
// ducted wired-remote bus (R1/R2, CZ-RD514C family).
//
// Physical layer (as reported in the HA community thread, topic 996275):
//   - DC-powered two-wire bus (~15 V idle on a W18BD3P).
//   - Data is on/off keying of a ~19-24 kHz carrier: carrier present = 0,
//     silence = 1. Roughly 2.02 ms per bit (~495 baud), 8E1, LSB first.
//
// Link layer (provisional, from one AI-assisted decode in post 54):
//   - Single-byte polls 0x80..0x9F, single-byte replies (e.g. 0xA6).
//   - Data frames: E3 LEN payload[LEN] CS, where (sum of all bytes) & 0x7F == 0.
//
// Nothing here depends on Arduino or ESP-IDF, so it builds and is tested natively.
#pragma once

#include <cstddef>
#include <cstdint>

// Functions called from an interrupt handler must not end up in flash on ESP32.
#if defined(__GNUC__)
#define RDBUS_ISR_INLINE inline __attribute__((always_inline))
#else
#define RDBUS_ISR_INLINE inline
#endif

namespace rdbus {

// ---------------------------------------------------------------------------
// Carrier envelope: edges -> bursts
// ---------------------------------------------------------------------------

struct Burst {
  uint32_t start_us;  // first edge
  uint32_t end_us;    // last edge
  uint32_t edges;
};

// Groups edges from an opto/comparator on the bus into carrier bursts. Only the
// spacing of edges matters, so the polarity of the front end is irrelevant.
class EnvelopeDetector {
 public:
  void set_gap_us(uint32_t g) { gap_us_ = g; }
  void set_min_edges(uint32_t m) { min_edges_ = m; }

  // Feed one edge. Returns true and fills *done when the previous burst ended.
  RDBUS_ISR_INLINE bool edge(uint32_t t, Burst *done) {
    bool emitted = false;
    if (active_ && (uint32_t) (t - last_) > gap_us_)
      emitted = finish_(done);
    if (!active_) {
      active_ = true;
      start_ = t;
      edges_ = 0;
    }
    last_ = t;
    edges_++;
    return emitted;
  }

  // Closes the current burst once the line has been quiet for gap_us.
  RDBUS_ISR_INLINE bool idle(uint32_t now, Burst *done) {
    if (active_ && (uint32_t) (now - last_) > gap_us_)
      return finish_(done);
    return false;
  }

  bool active() const { return active_; }
  uint32_t active_start() const { return start_; }
  uint32_t last_edge() const { return last_; }

 private:
  RDBUS_ISR_INLINE bool finish_(Burst *done) {
    active_ = false;
    if (edges_ < min_edges_)
      return false;  // glitch
    done->start_us = start_;
    done->end_us = last_;
    done->edges = edges_;
    return true;
  }

  // Silence longer than this ends a burst. A quarter bit (~500 us) bridges the short
  // carrier dropouts seen on a real W18BD3P bus while still splitting at a 1-bit.
  uint32_t gap_us_ = 500;
  uint32_t min_edges_ = 3;
  bool active_ = false;
  uint32_t start_ = 0, last_ = 0, edges_ = 0;
};

// ---------------------------------------------------------------------------
// Bursts -> UART bytes (start bit = carrier)
// ---------------------------------------------------------------------------

enum class Parity : uint8_t { NONE, EVEN, ODD };

struct RxByte {
  uint8_t value;
  uint32_t t_us;  // start of the start bit
  bool parity_ok;
  bool stop_ok;
};

inline uint8_t parity_bit(uint8_t v, Parity p) {
  uint8_t ones = 0;
  for (int i = 0; i < 8; i++)
    ones += (v >> i) & 1;
  return p == Parity::EVEN ? (ones & 1) : !(ones & 1);
}

class ByteDecoder {
 public:
  static constexpr size_t kCap = 24;

  void set_bit_us(uint32_t b) { bit_us_ = b; }
  uint32_t bit_us() const { return bit_us_; }
  void set_parity(Parity p) { parity_ = p; }
  uint32_t frame_bits() const { return 1 + 8 + (parity_ == Parity::NONE ? 0 : 1) + 1; }

  // Add a completed burst. Writes decoded bytes to out (at most max), returns count.
  size_t push(const Burst &b, RxByte *out, size_t max) {
    if (n_ == kCap) {  // should never happen on a sane bus; resync
      n_ = 0;
      in_byte_ = false;
    }
    buf_[n_++] = b;
    return drain_(b.end_us, out, max);
  }

  // The line state is known up to known_until (no burst is open before it).
  size_t flush(uint32_t known_until, RxByte *out, size_t max) { return drain_(known_until, out, max); }

 private:
  size_t drain_(uint32_t known_until, RxByte *out, size_t max) {
    size_t k = 0;
    while (k < max) {
      if (!in_byte_) {
        if (n_ == 0)
          break;
        t0_ = buf_[0].start_us;
        in_byte_ = true;
      }
      const uint32_t decide_at = frame_bits() * bit_us_ - bit_us_ / 2;  // middle of the stop bit
      if ((int32_t) (known_until - (t0_ + decide_at)) < 0)
        break;
      RxByte rb;
      if (decode_one_(&rb)) {
        out[k++] = rb;
        consume_(t0_ + decide_at);
      } else {
        consume_(t0_ + 1);  // only the glitch; the next burst may be a real start bit
      }
      in_byte_ = false;
    }
    return k;
  }

  // Line level at time t: 0 if inside a burst (carrier), 1 otherwise.
  int level_(uint32_t t) const {
    for (size_t i = 0; i < n_; i++) {
      if ((int32_t) (t - buf_[i].start_us) >= 0 && (int32_t) (buf_[i].end_us - t) >= 0)
        return 0;
    }
    return 1;
  }

  bool decode_one_(RxByte *rb) {
    auto sample = [&](uint32_t bit) { return level_(t0_ + bit * bit_us_ + bit_us_ / 2); };
    if (sample(0) != 0)
      return false;  // burst shorter than half a bit: noise
    uint8_t v = 0;
    for (uint32_t i = 0; i < 8; i++)
      v |= (uint8_t) (sample(1 + i) << i);
    rb->value = v;
    rb->t_us = t0_;
    rb->parity_ok = parity_ == Parity::NONE || (uint8_t) sample(9) == parity_bit(v, parity_);
    rb->stop_ok = sample(frame_bits() - 1) == 1;
    return true;
  }

  // Drop every burst that started before `until`.
  void consume_(uint32_t until) {
    size_t j = 0;
    for (size_t i = 0; i < n_; i++) {
      if ((int32_t) (buf_[i].start_us - until) >= 0)
        buf_[j++] = buf_[i];
    }
    n_ = j;
  }

  uint32_t bit_us_ = 2020;
  Parity parity_ = Parity::EVEN;
  Burst buf_[kCap];
  size_t n_ = 0;
  bool in_byte_ = false;
  uint32_t t0_ = 0;
};

// ---------------------------------------------------------------------------
// Bytes -> messages
// ---------------------------------------------------------------------------

constexpr uint8_t kFrameHeader = 0xE3;
constexpr size_t kMaxMsg = 40;

// Checksum byte that makes (sum of all bytes) & 0x7F == 0.
inline uint8_t checksum7(const uint8_t *d, size_t n) {
  uint32_t s = 0;
  for (size_t i = 0; i < n; i++)
    s += d[i];
  return (uint8_t) ((0x80 - (s & 0x7F)) & 0x7F);
}

inline bool checksum7_ok(const uint8_t *d, size_t n) {
  uint32_t s = 0;
  for (size_t i = 0; i < n; i++)
    s += d[i];
  return (s & 0x7F) == 0;
}

enum class MsgKind : uint8_t { POLL, TOKEN, FRAME, BAD_FRAME };

inline const char *kind_name(MsgKind k) {
  switch (k) {
    case MsgKind::POLL:
      return "POLL";
    case MsgKind::TOKEN:
      return "TOKEN";
    case MsgKind::FRAME:
      return "FRAME";
    default:
      return "BAD";
  }
}

struct Message {
  MsgKind kind;
  uint8_t data[kMaxMsg];
  uint8_t len;
  uint32_t t_us;
  bool checksum_ok;
  bool rx_error;  // any byte had a parity or stop-bit error
};

class FrameAssembler {
 public:
  void set_byte_timeout_us(uint32_t t) { timeout_us_ = t; }

  // Returns number of messages written to out (0..2).
  size_t push(const RxByte &b, Message *out) {
    size_t k = 0;
    if (collecting_ && (uint32_t) (b.t_us - last_t_) > timeout_us_)
      k += abort_(out + k);
    last_t_ = b.t_us;
    const bool err = !b.parity_ok || !b.stop_ok;
    if (!collecting_) {
      if (b.value == kFrameHeader) {
        collecting_ = true;
        cur_ = Message{};
        cur_.kind = MsgKind::FRAME;
        cur_.t_us = b.t_us;
        cur_.data[0] = b.value;
        cur_.len = 1;
        cur_.rx_error = err;
        return k;
      }
      Message &m = out[k++];
      m = Message{};
      m.kind = (b.value >= 0x80 && b.value <= 0x9F) ? MsgKind::POLL : MsgKind::TOKEN;
      m.data[0] = b.value;
      m.len = 1;
      m.t_us = b.t_us;
      m.checksum_ok = true;
      m.rx_error = err;
      return k;
    }
    cur_.data[cur_.len++] = b.value;
    cur_.rx_error |= err;
    if (cur_.len == 2 && (size_t) b.value + 3 > kMaxMsg)
      return k + abort_(out + k);
    if (cur_.len >= 2 && cur_.len == cur_.data[1] + 3) {
      cur_.checksum_ok = checksum7_ok(cur_.data, cur_.len);
      if (!cur_.checksum_ok)
        cur_.kind = MsgKind::BAD_FRAME;
      out[k++] = cur_;
      collecting_ = false;
    }
    return k;
  }

  size_t flush(uint32_t now, Message *out) {
    if (collecting_ && (uint32_t) (now - last_t_) > timeout_us_)
      return abort_(out);
    return 0;
  }

 private:
  size_t abort_(Message *out) {
    collecting_ = false;
    cur_.kind = MsgKind::BAD_FRAME;
    cur_.checksum_ok = false;
    *out = cur_;
    return 1;
  }

  uint32_t timeout_us_ = 60000;
  bool collecting_ = false;
  uint32_t last_t_ = 0;
  Message cur_{};
};

// ---------------------------------------------------------------------------
// Encoding (for transmit and tests)
// ---------------------------------------------------------------------------

// Builds E3 LEN payload CS. Returns total length, or 0 if it does not fit.
inline size_t build_frame(const uint8_t *payload, size_t n, uint8_t *out, size_t max) {
  if (n + 3 > max || n > 0x7F)
    return 0;
  out[0] = kFrameHeader;
  out[1] = (uint8_t) n;
  for (size_t i = 0; i < n; i++)
    out[2 + i] = payload[i];
  out[2 + n] = checksum7(out, 2 + n);
  return n + 3;
}

struct Segment {
  bool carrier;  // true = carrier on (logical 0)
  uint32_t us;
};

// Turns bytes into carrier on/off segments (consecutive equal levels merged).
// idle_bits_between adds extra stop-level time between bytes.
inline size_t encode_bytes(const uint8_t *bytes, size_t n, uint32_t bit_us, Parity parity,
                           uint32_t idle_bits_between, Segment *out, size_t max) {
  size_t k = 0;
  auto put = [&](bool carrier, uint32_t us) {
    if (us == 0)
      return true;
    if (k > 0 && out[k - 1].carrier == carrier) {
      out[k - 1].us += us;
      return true;
    }
    if (k == max)
      return false;
    out[k++] = Segment{carrier, us};
    return true;
  };
  for (size_t i = 0; i < n; i++) {
    const uint8_t v = bytes[i];
    bool ok = put(true, bit_us);  // start bit
    for (int b = 0; b < 8; b++)
      ok = ok && put(((v >> b) & 1) == 0, bit_us);
    if (parity != Parity::NONE)
      ok = ok && put(parity_bit(v, parity) == 0, bit_us);
    ok = ok && put(false, bit_us);  // stop bit
    if (i + 1 < n)
      ok = ok && put(false, idle_bits_between * bit_us);
    if (!ok)
      return 0;
  }
  return k;
}

// ---------------------------------------------------------------------------
// Transmit scheduling: wait for a quiet bus, check our own echo, retry on collision
// ---------------------------------------------------------------------------

class TxScheduler {
 public:
  static constexpr size_t kQueue = 8;

  struct Job {
    uint8_t bytes[kMaxMsg];
    uint8_t len;
    uint8_t sends_left;  // successful sends still wanted
    uint8_t failures;
  };

  enum class Event : uint8_t { NONE, SENT_OK, COLLISION, GAVE_UP };

  void set_min_idle_us(uint32_t v) { min_idle_us_ = v; }
  void set_repeat_spacing_us(uint32_t v) { spacing_us_ = v; }
  void set_max_failures(uint8_t v) { max_failures_ = v; }
  // Only start right after this single-byte message (e.g. a poll), or -1 for any quiet gap.
  void set_trigger(int byte) { trigger_ = byte; }

  bool enqueue(const uint8_t *b, size_t n, uint8_t sends) {
    if (count_ == kQueue || n == 0 || n > kMaxMsg)
      return false;
    Job &j = q_[(head_ + count_) % kQueue];
    for (size_t i = 0; i < n; i++)
      j.bytes[i] = b[i];
    j.len = (uint8_t) n;
    j.sends_left = sends ? sends : 1;
    j.failures = 0;
    count_++;
    return true;
  }

  bool pending() const { return count_ > 0; }
  const Job *current() const { return count_ ? &q_[head_] : nullptr; }

  // Feed every decoded message (including our own echo).
  Event on_message(const Message &m) {
    if (trigger_ >= 0 && m.len == 1 && m.data[0] == (uint8_t) trigger_ && m.kind != MsgKind::BAD_FRAME)
      triggered_ = true;
    if (!awaiting_echo_ || !count_)
      return Event::NONE;
    const Job &j = q_[head_];
    if ((int32_t) (m.t_us - tx_start_) < -1000)
      return Event::NONE;  // older than our transmission
    bool match = m.len == j.len && !m.rx_error;
    for (size_t i = 0; match && i < j.len; i++)
      match = m.data[i] == j.bytes[i];
    awaiting_echo_ = false;
    return match ? succeeded_(m.t_us) : failed_(m.t_us);
  }

  // Call often. Returns true when the caller should start transmitting current() now.
  bool should_start(uint32_t now, uint32_t last_bus_activity, bool transmitter_busy) {
    if (!count_ || awaiting_echo_ || transmitter_busy)
      return false;
    if (have_last_ && (uint32_t) (now - last_done_) < spacing_us_)
      return false;
    if ((uint32_t) (now - last_bus_activity) < min_idle_us_)
      return false;
    if (trigger_ >= 0 && !triggered_)
      return false;
    triggered_ = false;
    awaiting_echo_ = true;
    tx_start_ = now;
    return true;
  }

  // How long to wait for our own echo: the frame's air time plus decode slack.
  static uint32_t echo_timeout_us(const Job &j, uint32_t bit_us) { return j.len * 11u * bit_us + 150000u; }

  // Call while waiting: reports a collision if no echo arrived in time.
  Event poll(uint32_t now, uint32_t echo_timeout_us) {
    if (awaiting_echo_ && (uint32_t) (now - tx_start_) > echo_timeout_us) {
      awaiting_echo_ = false;
      return failed_(now);
    }
    return Event::NONE;
  }

 private:
  Event succeeded_(uint32_t t) {
    Job &j = q_[head_];
    last_done_ = t;
    have_last_ = true;
    if (--j.sends_left == 0)
      pop_();
    return Event::SENT_OK;
  }

  Event failed_(uint32_t t) {
    Job &j = q_[head_];
    last_done_ = t;
    have_last_ = true;
    if (++j.failures >= max_failures_) {
      pop_();
      return Event::GAVE_UP;
    }
    return Event::COLLISION;
  }

  void pop_() {
    head_ = (head_ + 1) % kQueue;
    count_--;
  }

  Job q_[kQueue];
  size_t head_ = 0, count_ = 0;
  bool awaiting_echo_ = false, triggered_ = false, have_last_ = false;
  uint32_t tx_start_ = 0, last_done_ = 0;
  uint32_t min_idle_us_ = 8000, spacing_us_ = 88500;
  uint8_t max_failures_ = 6;
  int trigger_ = -1;
};

// ---------------------------------------------------------------------------
// Bit-time and carrier estimation from observed bursts
// ---------------------------------------------------------------------------

class BusStats {
 public:
  static constexpr size_t kN = 256;

  void add(const Burst &b) {
    const uint32_t dur = b.end_us - b.start_us;
    if (b.edges > 10 && dur > 0) {
      carrier_sum_ += (double) (b.edges - 1) * 1e6 / (2.0 * dur);
      carrier_n_++;
    }
    dur_[n_ % kN] = dur;
    n_++;
  }

  uint32_t bursts() const { return n_; }
  double carrier_hz() const { return carrier_n_ ? carrier_sum_ / carrier_n_ : 0; }

  // Single-bit bursts are the shortest cluster; longer ones are near multiples of it.
  // floor_us: ignore fragments shorter than this (use about half the expected bit).
  double bit_us(uint32_t floor_us = 1000) const {
    const size_t n = n_ < kN ? n_ : kN;
    if (n < 16)
      return 0;
    uint32_t mn = UINT32_MAX;
    for (size_t i = 0; i < n; i++)
      if (dur_[i] > floor_us && dur_[i] < mn)
        mn = dur_[i];
    if (mn == UINT32_MAX)
      return 0;
    // The burst spans first..last edge, so it is short by up to one carrier period.
    const double pad = carrier_hz() > 0 ? 1e6 / carrier_hz() / 2 : 0;
    double sum = 0;
    size_t cnt = 0;
    for (size_t i = 0; i < n; i++) {
      const double d = dur_[i] + pad;
      const double k = (double) (long) (d / (mn + pad) + 0.5);
      if (k >= 1 && k <= 10) {
        sum += d / k;
        cnt++;
      }
    }
    return cnt ? sum / cnt : 0;
  }

 private:
  uint32_t dur_[kN] = {};
  size_t n_ = 0;
  double carrier_sum_ = 0;
  size_t carrier_n_ = 0;
};

// ---------------------------------------------------------------------------
// Unit state. Register map confirmed on a W18BD3P + CZ-RD514C (2026-11-21):
//   0x60 power     0 = off, 1 = on
//   0x61 mode      1 = heat, 2 = cool, 3 = fan, 4 = dry, 8 = auto
//   0x62 fan       1 = high, 2 = medium, 3 = low, 8 = auto
//   0x63 vane      always 8 on a ducted unit ("not available")
//   0x64 setpoint  index, degrees C = index + 16
// Command frames carry (reg, value). State dumps carry (reg, 0x20 + value) pairs.
// ---------------------------------------------------------------------------

constexpr uint8_t kRegPower = 0x60;
constexpr uint8_t kRegMode = 0x61;
constexpr uint8_t kRegFan = 0x62;
constexpr uint8_t kRegVane = 0x63;
constexpr uint8_t kRegSetpoint = 0x64;

struct UnitState {
  int16_t reg[256];
  UnitState() {
    for (auto &r : reg)
      r = -1;
  }
};

// Applies a good frame to the state. Returns true if a register changed.
inline bool apply_frame(const Message &m, UnitState *s) {
  if (m.kind != MsgKind::FRAME || m.len < 5)
    return false;
  const uint8_t n = m.data[1];
  const uint8_t *p = m.data + 2;
  if (n % 2 != 0)
    return false;  // not a register/value list (e.g. the ASCII-looking 6B frames)
  for (uint8_t i = 0; i < n; i += 2) {
    if (p[i] < 0x40 || p[i] > 0x7F)
      return false;
  }
  const bool dump = n > 2;
  bool changed = false;
  for (uint8_t i = 0; i < n; i += 2) {
    int v = p[i + 1];
    if (dump) {
      if (v < 0x20)
        continue;
      v -= 0x20;
    }
    if (s->reg[p[i]] != v) {
      s->reg[p[i]] = (int16_t) v;
      changed = true;
    }
  }
  return changed;
}

}  // namespace rdbus
