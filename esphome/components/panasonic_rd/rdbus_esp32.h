// rdbus_esp32.h - ESP32 receive/transmit glue for rdbus.h.
// Uses only ESP-IDF APIs that exist in both IDF 4.4 (Arduino-ESP32 2.x) and IDF 5.x
// (ESPHome's default esp-idf framework, Arduino-ESP32 3.x).
#pragma once

#include "rdbus.h"

#include "driver/gpio.h"
#include "driver/ledc.h"
#include "esp_attr.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"

namespace rdbus {

// Timestamps every edge from the receive opto in an IRAM interrupt and groups them
// into carrier bursts. The main loop pops finished bursts.
class Receiver {
 public:
  static constexpr size_t kRing = 256;

  void set_gap_us(uint32_t g) { env_.set_gap_us(g); }

  bool begin(gpio_num_t pin, bool internal_pullup) {
    gpio_config_t c = {};
    c.pin_bit_mask = 1ULL << pin;
    c.mode = GPIO_MODE_INPUT;
    c.pull_up_en = internal_pullup ? GPIO_PULLUP_ENABLE : GPIO_PULLUP_DISABLE;
    c.pull_down_en = GPIO_PULLDOWN_DISABLE;
    c.intr_type = GPIO_INTR_ANYEDGE;
    if (gpio_config(&c) != ESP_OK)
      return false;
    esp_err_t e = gpio_install_isr_service(ESP_INTR_FLAG_IRAM);
    if (e != ESP_OK && e != ESP_ERR_INVALID_STATE)
      return false;  // INVALID_STATE = someone already installed it, fine
    return gpio_isr_handler_add(pin, isr_, this) == ESP_OK;
  }

  // Closes a burst once the line has gone quiet and returns the time up to which
  // the line state is fully known. Call before popping.
  uint32_t service(uint32_t /*caller_now*/) {
    Burst b;
    portENTER_CRITICAL(&mux_);
    // Read the clock inside the lock so no edge can be newer than `now`.
    const uint32_t now = (uint32_t) esp_timer_get_time();
    if (env_.idle(now, &b))
      push_(this, b);
    const uint32_t known = env_.active() ? env_.active_start() : now;
    portEXIT_CRITICAL(&mux_);
    return known;
  }

  bool pop(Burst *b) {
    bool ok = false;
    portENTER_CRITICAL(&mux_);
    if (tail_ != head_) {
      *b = ring_[tail_];
      tail_ = (tail_ + 1) % kRing;
      ok = true;
    }
    portEXIT_CRITICAL(&mux_);
    return ok;
  }

  uint32_t last_edge() const { return last_edge_; }
  uint32_t edges() const { return edges_; }
  uint32_t overflows() const { return overflows_; }

 private:
  static RDBUS_ISR_INLINE void push_(Receiver *self, const Burst &b) {
    const size_t next = (self->head_ + 1) % kRing;
    if (next == self->tail_) {
      self->overflows_++;
      return;
    }
    self->ring_[self->head_] = b;
    self->head_ = next;
  }

  static void IRAM_ATTR isr_(void *arg) {
    auto *self = static_cast<Receiver *>(arg);
    const uint32_t t = (uint32_t) esp_timer_get_time();
    Burst b;
    portENTER_CRITICAL_ISR(&self->mux_);
    self->last_edge_ = t;
    self->edges_++;
    if (self->env_.edge(t, &b))
      push_(self, b);
    portEXIT_CRITICAL_ISR(&self->mux_);
  }

  portMUX_TYPE mux_ = portMUX_INITIALIZER_UNLOCKED;
  EnvelopeDetector env_;
  Burst ring_[kRing];
  volatile size_t head_ = 0, tail_ = 0;
  volatile uint32_t last_edge_ = 0, edges_ = 0, overflows_ = 0;
};

// Drives the transmit opto: LEDC produces the carrier, an esp_timer gates it on and
// off per bit on an absolute schedule (no drift). GPIO idles LOW = transmitter off.
class Transmitter {
 public:
  static constexpr size_t kMaxSeg = 11 * kMaxMsg;  // worst case: every bit toggles

  bool begin(gpio_num_t pin, uint32_t carrier_hz) {
    ledc_timer_config_t t = {};
    t.speed_mode = LEDC_LOW_SPEED_MODE;
    t.duty_resolution = LEDC_TIMER_8_BIT;
    t.timer_num = kTimer;
    t.freq_hz = carrier_hz;
    t.clk_cfg = LEDC_AUTO_CLK;
    if (ledc_timer_config(&t) != ESP_OK)
      return false;
    ledc_channel_config_t c = {};
    c.gpio_num = pin;
    c.speed_mode = LEDC_LOW_SPEED_MODE;
    c.channel = kChannel;
    c.intr_type = LEDC_INTR_DISABLE;
    c.timer_sel = kTimer;
    c.duty = 0;
    c.hpoint = 0;
    if (ledc_channel_config(&c) != ESP_OK)
      return false;
    pin_ = pin;
    esp_timer_create_args_t a = {};
    a.callback = &Transmitter::tick_;
    a.arg = this;
    a.name = "rdbus_tx";
    return esp_timer_create(&a, &timer_) == ESP_OK;
  }

  // Move the carrier output to another pin (diagnostics: find where the TX stage is wired).
  bool set_pin(gpio_num_t pin) {
    if (busy_)
      return false;
    if (pin_ >= 0)
      gpio_reset_pin((gpio_num_t) pin_);
    ledc_channel_config_t c = {};
    c.gpio_num = pin;
    c.speed_mode = LEDC_LOW_SPEED_MODE;
    c.channel = kChannel;
    c.intr_type = LEDC_INTR_DISABLE;
    c.timer_sel = kTimer;
    c.duty = 0;
    c.hpoint = 0;
    if (ledc_channel_config(&c) != ESP_OK)
      return false;
    pin_ = pin;
    return true;
  }

  bool set_carrier_hz(uint32_t hz) {
    return !busy_ && ledc_set_freq(LEDC_LOW_SPEED_MODE, kTimer, hz) == ESP_OK;
  }

  bool busy() const { return busy_; }

  // Starts sending asynchronously. Returns false if busy or too long.
  bool send(const Segment *s, size_t n) {
    if (busy_ || n == 0 || n > kMaxSeg || timer_ == nullptr)
      return false;
    for (size_t i = 0; i < n; i++)
      segs_[i] = s[i];
    n_ = n;
    idx_ = 0;
    busy_ = true;
    next_at_ = esp_timer_get_time() + 200;
    esp_timer_start_once(timer_, 200);
    return true;
  }

 private:
  static constexpr ledc_timer_t kTimer = LEDC_TIMER_3;
  static constexpr ledc_channel_t kChannel = LEDC_CHANNEL_7;

  static void carrier_(bool on) {
    ledc_set_duty(LEDC_LOW_SPEED_MODE, kChannel, on ? 128 : 0);  // 50 % duty
    ledc_update_duty(LEDC_LOW_SPEED_MODE, kChannel);
  }

  static void tick_(void *arg) {
    auto *self = static_cast<Transmitter *>(arg);
    if (self->idx_ < self->n_) {
      const Segment &s = self->segs_[self->idx_++];
      carrier_(s.carrier);
      self->next_at_ += s.us;
      int64_t d = self->next_at_ - esp_timer_get_time();
      esp_timer_start_once(self->timer_, d > 1 ? d : 1);
    } else {
      carrier_(false);
      self->busy_ = false;
    }
  }

  esp_timer_handle_t timer_ = nullptr;
  int pin_ = -1;
  Segment segs_[kMaxSeg];
  size_t n_ = 0, idx_ = 0;
  int64_t next_at_ = 0;
  volatile bool busy_ = false;
};

}  // namespace rdbus
