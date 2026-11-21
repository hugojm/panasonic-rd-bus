// Native tests for rdbus.h: synthesise carrier-modulated bus traffic, decode it.
// Build & run:  make -C test
#include "../esphome/components/panasonic_rd/rdbus.h"

#include <cstdio>
#include <cstdlib>
#include <random>
#include <string>
#include <vector>

using namespace rdbus;

static int g_fail = 0;
#define CHECK(c)                                                  \
  do {                                                            \
    if (!(c)) {                                                   \
      std::printf("  FAIL %s:%d: %s\n", __FILE__, __LINE__, #c);  \
      g_fail++;                                                   \
    }                                                             \
  } while (0)

using Bytes = std::vector<uint8_t>;

// Frames quoted in post 54 of the thread (checksums verified independently).
static const std::vector<Bytes> kPost54Frames = {
    {0xE3, 0x02, 0x60, 0x01, 0x3A},  // power on
    {0xE3, 0x02, 0x60, 0x00, 0x3B},  // power off
    {0xE3, 0x02, 0x62, 0x03, 0x36},  // fan
    {0xE3, 0x02, 0x62, 0x08, 0x31},  // fan auto?
    {0xE3, 0x02, 0x64, 0x00, 0x37},  // setpoint index 0
    {0xE3, 0x02, 0x64, 0x04, 0x33},  // setpoint index 4
    {0xE3, 0x0C, 0x60, 0x21, 0x61, 0x22, 0x62, 0x28, 0x63, 0x28, 0x64, 0x21, 0x49, 0x20, 0x0A},  // dump
    {0xE3, 0x0A, 0x6B, 0x30, 0x30, 0x30, 0x30, 0x48, 0x02, 0x0F, 0x4B, 0x20, 0x24},             // ascii-ish
    {0xE3, 0x07, 0x6B, 0x30, 0x30, 0x30, 0x30, 0x4B, 0x20, 0x00},
    {0xE1, 0x03, 0x70, 0x00, 0x00, 0x2C},  // E1 frames captured on a W18BD3P
    {0xE1, 0x02, 0x53, 0x00, 0x4A},
    {0xE1, 0x02, 0x66, 0x01, 0x36},
};

struct Sim {
  uint32_t carrier_hz = 19200;
  double bit_scale = 1.0;  // transmitter bit time relative to the receiver's
  uint32_t jitter_us = 2;
  double dropout_per_bit = 0;  // chance of a 100-350 us carrier gap inside a 0-bit
  std::mt19937 rng{42};
  std::vector<uint32_t> edges;
  uint32_t t = 100000;  // start at 100 ms

  // Append bytes as they would appear on the bus, then `gap_us` of silence.
  void send(const Bytes &b, uint32_t gap_us, uint32_t idle_bits_between = 0) {
    std::vector<Segment> seg(512);
    const uint32_t bit = (uint32_t) (2020 * bit_scale);
    size_t n = encode_bytes(b.data(), b.size(), bit, Parity::EVEN, idle_bits_between, seg.data(), seg.size());
    std::uniform_int_distribution<int> j(-(int) jitter_us, (int) jitter_us);
    const double half = 1e6 / carrier_hz / 2;
    for (size_t i = 0; i < n; i++) {
      if (seg[i].carrier) {
        // Optional dropout: no edges inside [gap_from, gap_to).
        uint32_t gap_from = UINT32_MAX, gap_to = 0;
        std::uniform_real_distribution<double> u(0, 1);
        const uint32_t nbits = seg[i].us / bit;
        for (uint32_t b = 0; b < nbits && dropout_per_bit > 0; b++) {
          if (u(rng) < dropout_per_bit) {
            gap_from = b * bit + 300 + (uint32_t) (u(rng) * (bit - 800));
            gap_to = gap_from + 100 + (uint32_t) (u(rng) * 250);
            break;
          }
        }
        uint32_t k = 0;
        for (; k * half < seg[i].us; k++) {
          const uint32_t off = (uint32_t) (k * half);
          if (off >= gap_from && off < gap_to)
            continue;
          edges.push_back(t + off + j(rng));
        }
        if (k % 2 == 1)  // line still pulled low: release at the end
          edges.push_back(t + seg[i].us);
      }
      t += seg[i].us;
    }
    t += gap_us;
  }

  void glitch() {  // a lone spike on an idle line
    edges.push_back(t);
    edges.push_back(t + 3);
    t += 20000;
  }
};

// Runs edges through the whole receive chain.
static std::vector<Message> decode(const std::vector<uint32_t> &edges, uint32_t end_t, uint32_t rx_bit_us = 2020) {
  EnvelopeDetector env;
  ByteDecoder dec;
  dec.set_bit_us(rx_bit_us);
  FrameAssembler fa;
  std::vector<Message> msgs;
  RxByte rb[8];
  Message m[4];
  auto on_bytes = [&](size_t n) {
    for (size_t i = 0; i < n; i++) {
      size_t k = fa.push(rb[i], m);
      for (size_t x = 0; x < k; x++)
        msgs.push_back(m[x]);
    }
  };
  Burst b;
  for (uint32_t e : edges) {
    if (env.edge(e, &b))
      on_bytes(dec.push(b, rb, 8));
  }
  if (env.idle(end_t, &b))
    on_bytes(dec.push(b, rb, 8));
  on_bytes(dec.flush(end_t, rb, 8));
  size_t k = fa.flush(end_t + 1000000, m);
  for (size_t x = 0; x < k; x++)
    msgs.push_back(m[x]);
  return msgs;
}

static std::string hex(const uint8_t *d, size_t n) {
  std::string s;
  char buf[4];
  for (size_t i = 0; i < n; i++) {
    std::snprintf(buf, sizeof buf, "%02X ", d[i]);
    s += buf;
  }
  return s;
}

static bool same(const Message &m, const Bytes &b) {
  return m.len == b.size() && std::equal(b.begin(), b.end(), m.data);
}

static void test_checksums() {
  std::printf("checksums of post-54 frames\n");
  for (auto &f : kPost54Frames) {
    CHECK(checksum7_ok(f.data(), f.size()));
    if (f[0] != kFrameHeader)
      continue;
    uint8_t out[kMaxMsg];
    size_t n = build_frame(f.data() + 2, f.size() - 3, out, sizeof out);
    CHECK(n == f.size());
    CHECK(Bytes(out, out + n) == f);
  }
}

// Polls, replies and frames, the way post 54 describes the traffic.
static void scenario(Sim &sim, std::vector<Bytes> &expect) {
  const Bytes polls = {0x80, 0x81, 0x90, 0x91, 0x92};
  for (uint8_t p : polls) {
    sim.send({p}, 20000);
    expect.push_back({p});
    if (p == 0x80 || p == 0x90) {
      sim.send({0xA6}, 110000);
      expect.push_back({0xA6});
    } else {
      sim.t += 110000;
    }
  }
  for (auto &f : kPost54Frames) {
    sim.send(f, 88500);
    expect.push_back(f);
  }
  sim.send({0x00}, 30000);  // all-zero byte: one long burst
  expect.push_back({0x00});
  sim.send({0xFF}, 30000);
  expect.push_back({0xFF});
}

static void run_case(const char *name, Sim sim, uint32_t rx_bit_us = 2020) {
  std::printf("%s\n", name);
  std::vector<Bytes> expect;
  scenario(sim, expect);
  auto msgs = decode(sim.edges, sim.t + 100000, rx_bit_us);
  CHECK(msgs.size() == expect.size());
  for (size_t i = 0; i < msgs.size() && i < expect.size(); i++) {
    if (!same(msgs[i], expect[i])) {
      std::printf("  got %s want %s\n", hex(msgs[i].data, msgs[i].len).c_str(),
                  hex(expect[i].data(), expect[i].size()).c_str());
      g_fail++;
    }
    CHECK(!msgs[i].rx_error);
    if (expect[i].size() > 1)
      CHECK(msgs[i].kind == MsgKind::FRAME && msgs[i].checksum_ok);
  }
}

static void test_glitch_rejected() {
  std::printf("glitches between messages are ignored\n");
  Sim sim;
  sim.send({0x90}, 30000);
  sim.glitch();
  sim.send({0xE3, 0x02, 0x60, 0x01, 0x3A}, 30000);
  auto msgs = decode(sim.edges, sim.t + 100000);
  CHECK(msgs.size() == 2);
  if (msgs.size() == 2) {
    CHECK(msgs[0].kind == MsgKind::POLL && msgs[0].data[0] == 0x90);
    CHECK(msgs[1].kind == MsgKind::FRAME && msgs[1].checksum_ok);
  }
}

static void test_short_burst_before_frame() {
  std::printf("a short noise burst just before a frame does not swallow it\n");
  Sim sim;
  for (int k = 0; k < 8; k++)  // ~200 us of carrier: passes min_edges, shorter than half a bit
    sim.edges.push_back(sim.t + k * 26);
  sim.t += 3000;
  sim.send({0xE3, 0x02, 0x60, 0x01, 0x3A}, 30000);
  auto msgs = decode(sim.edges, sim.t + 100000);
  CHECK(msgs.size() == 1);
  if (!msgs.empty())
    CHECK(msgs[0].kind == MsgKind::FRAME && msgs[0].checksum_ok);
}

static void test_idle_with_stale_clock() {
  std::printf("idle() with a clock read just before the last edge does not split the burst\n");
  EnvelopeDetector env;
  Burst b;
  for (uint32_t t = 1000; t < 3000; t += 26)
    CHECK(!env.edge(t, &b));
  // The loop read now=2950, then an edge arrived at ~2990 before idle() ran.
  CHECK(!env.idle(2950, &b));
  CHECK(env.active());
  CHECK(env.idle(2990 + 600, &b));  // genuinely quiet afterwards: closes once
  CHECK(b.start_us == 1000 && b.edges > 70);
}

static void test_corrupt_checksum() {
  std::printf("bad checksum is flagged\n");
  Sim sim;
  sim.send({0xE3, 0x02, 0x60, 0x01, 0x3B}, 30000);
  auto msgs = decode(sim.edges, sim.t + 100000);
  CHECK(msgs.size() == 1);
  if (!msgs.empty())
    CHECK(msgs[0].kind == MsgKind::BAD_FRAME && !msgs[0].checksum_ok);
}

static void test_truncated_frame_times_out() {
  std::printf("truncated frame is reported after timeout\n");
  Sim sim;
  sim.send({0xE3, 0x02, 0x60}, 200000);
  sim.send({0x90}, 30000);
  auto msgs = decode(sim.edges, sim.t + 100000);
  CHECK(msgs.size() == 2);
  if (msgs.size() == 2) {
    CHECK(msgs[0].kind == MsgKind::BAD_FRAME && msgs[0].len == 3);
    CHECK(msgs[1].kind == MsgKind::POLL);
  }
}

static void test_state() {
  std::printf("state tracking from commands and dumps\n");
  UnitState s;
  auto msg = [](const Bytes &b) {
    Message m{};
    m.kind = MsgKind::FRAME;
    m.len = (uint8_t) b.size();
    std::copy(b.begin(), b.end(), m.data);
    m.checksum_ok = true;
    return m;
  };
  CHECK(apply_frame(msg(kPost54Frames[6]), &s));  // dump
  CHECK(s.reg[kRegPower] == 1 && s.reg[kRegMode] == 2 && s.reg[kRegFan] == 8 && s.reg[kRegSetpoint] == 1);
  CHECK(s.reg[0x49] == 0);
  CHECK(apply_frame(msg(kPost54Frames[1]), &s));  // power off
  CHECK(s.reg[kRegPower] == 0);
  CHECK(!apply_frame(msg(kPost54Frames[1]), &s));  // unchanged
  CHECK(!apply_frame(msg(kPost54Frames[7]), &s));  // ascii-ish frame is not a register list
  CHECK(apply_frame(msg(kPost54Frames[5]), &s));
  CHECK(s.reg[kRegSetpoint] == 4);
}

static Message mk(const Bytes &b, uint32_t t, bool err = false) {
  Message m{};
  m.kind = b.size() == 1 ? MsgKind::POLL : MsgKind::FRAME;
  m.len = (uint8_t) b.size();
  std::copy(b.begin(), b.end(), m.data);
  m.t_us = t;
  m.checksum_ok = true;
  m.rx_error = err;
  return m;
}

static void test_scheduler() {
  std::printf("tx scheduler: idle wait, echo, repeats, collisions, trigger\n");
  using E = TxScheduler::Event;
  const Bytes f = {0xE3, 0x02, 0x60, 0x01, 0x3A};
  TxScheduler s;
  s.set_min_idle_us(8000);
  s.set_repeat_spacing_us(88500);
  CHECK(s.enqueue(f.data(), f.size(), 3));
  CHECK(!s.should_start(10000, 5000, false));   // bus active 5 ms ago
  CHECK(!s.should_start(20000, 5000, true));    // transmitter busy
  CHECK(s.should_start(20000, 5000, false));    // quiet for 15 ms
  CHECK(!s.should_start(30000, 5000, false));   // waiting for echo
  CHECK(s.on_message(mk(f, 20300)) == E::SENT_OK);
  CHECK(!s.should_start(60000, 20000, false));  // spacing not reached
  CHECK(s.should_start(120000, 20000, false));
  CHECK(s.on_message(mk({0x90}, 120300)) == E::COLLISION);  // someone else's byte
  CHECK(s.should_start(220000, 130000, false));
  CHECK(s.on_message(mk(f, 220300)) == E::SENT_OK);
  CHECK(s.should_start(320000, 230000, false));
  CHECK(s.on_message(mk(f, 320300, true)) == E::COLLISION);  // echo with parity error
  CHECK(s.should_start(420000, 330000, false));
  CHECK(s.on_message(mk(f, 420300)) == E::SENT_OK);
  CHECK(!s.pending());

  TxScheduler g;
  g.set_max_failures(2);
  g.enqueue(f.data(), f.size(), 1);
  CHECK(g.should_start(20000, 0, false));
  CHECK(g.poll(500000, 400000) == E::COLLISION);  // no echo at all
  CHECK(g.should_start(700000, 0, false));
  CHECK(g.poll(1200000, 400000) == E::GAVE_UP);
  CHECK(!g.pending());

  TxScheduler t;
  t.set_trigger(0x9F);
  t.enqueue(f.data(), f.size(), 1);
  CHECK(!t.should_start(50000, 0, false));
  t.on_message(mk({0x9E}, 60000));
  CHECK(!t.should_start(100000, 60000, false));
  t.on_message(mk({0x9F}, 110000));
  CHECK(t.should_start(140000, 110000, false));
}

static void test_stats() {
  std::printf("bus stats estimate bit time and carrier\n");
  for (uint32_t hz : {19200u, 24000u}) {
    Sim sim;
    sim.carrier_hz = hz;
    std::vector<Bytes> expect;
    scenario(sim, expect);
    EnvelopeDetector env;
    BusStats st;
    Burst b;
    for (uint32_t e : sim.edges)
      if (env.edge(e, &b))
        st.add(b);
    std::printf("  %u Hz: estimated carrier %.0f Hz, bit %.1f us\n", hz, st.carrier_hz(), st.bit_us());
    CHECK(std::abs(st.carrier_hz() - hz) < hz * 0.03);
    CHECK(std::abs(st.bit_us() - 2020) < 2020 * 0.02);
  }
}

int main() {
  test_scheduler();
  test_stats();
  test_checksums();
  run_case("clean bus, 19.2 kHz carrier", Sim{});
  {
    Sim s;
    s.carrier_hz = 24000;
    run_case("24 kHz carrier (what the scope suggested)", s);
  }
  {
    Sim s;
    s.bit_scale = 1.03;
    run_case("transmitter 3% slow", s);
  }
  {
    Sim s;
    s.bit_scale = 0.97;
    run_case("transmitter 3% fast", s);
  }
  {
    Sim s;
    s.jitter_us = 8;
    run_case("8 us edge jitter", s);
  }
  {
    Sim s;
    s.dropout_per_bit = 0.3;
    run_case("carrier dropouts of 100-350 us inside 0-bits (seen on the real bus)", s);
  }
  {
    Sim s;
    s.bit_scale = 2000.0 / 2020.0;
    run_case("500 baud bus decoded with the 495 baud default", s);
  }
  {
    std::printf("decoding at 1200 baud (the old sniffer setting) does not recover frames\n");
    Sim s;
    std::vector<Bytes> expect;
    scenario(s, expect);
    auto msgs = decode(s.edges, s.t + 100000, 833);
    size_t good_frames = 0;
    for (auto &m : msgs)
      good_frames += m.kind == MsgKind::FRAME && m.checksum_ok && !m.rx_error;
    CHECK(good_frames == 0);
  }
  test_glitch_rejected();
  test_short_burst_before_frame();
  test_idle_with_stale_clock();
  test_corrupt_checksum();
  test_truncated_frame_times_out();
  test_state();
  if (g_fail) {
    std::printf("\n%d check(s) failed\n", g_fail);
    return 1;
  }
  std::printf("\nall tests passed\n");
  return 0;
}
