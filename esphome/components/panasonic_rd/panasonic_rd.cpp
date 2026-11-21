#include "panasonic_rd.h"

#include <cinttypes>
#include <cmath>

#include "esphome/core/helpers.h"
#include "esphome/core/log.h"

namespace esphome::panasonic_rd {

static const char *const TAG = "panasonic_rd";

void PanasonicRD::setup() {
  this->dec_.set_bit_us(this->bit_us_);
  this->sched_.set_trigger(this->transmit_after_);
  this->sched_.set_reply_delay_us(this->reply_delay_us_);
  if (!this->rx_.begin((gpio_num_t) this->rx_pin_, this->rx_pullup_)) {
    ESP_LOGE(TAG, "Could not set up the receive pin");
    this->mark_failed();
    return;
  }
  if (this->transmit_ && this->tx_pin_ >= 0) {
    this->tx_ready_ = this->tx_.begin((gpio_num_t) this->tx_pin_, this->carrier_hz_);
    if (!this->tx_ready_)
      ESP_LOGE(TAG, "Could not set up the transmit pin; continuing receive-only");
  }
  this->mode = climate::CLIMATE_MODE_OFF;
  this->target_temperature = NAN;
}

void PanasonicRD::dump_config() {
  ESP_LOGCONFIG(TAG, "Panasonic R1/R2 bus:");
  ESP_LOGCONFIG(TAG, "  RX pin: GPIO%u%s", this->rx_pin_, this->rx_pullup_ ? " (pull-up)" : "");
  ESP_LOGCONFIG(TAG, "  Bit time: %" PRIu32 " us", this->bit_us_);
  if (this->transmit_) {
    ESP_LOGCONFIG(TAG, "  TX pin: GPIO%d, carrier %" PRIu32 " Hz%s", this->tx_pin_, this->carrier_hz_,
                  this->tx_ready_ ? "" : " (FAILED)");
    ESP_LOGCONFIG(TAG, "  Transmits %" PRIu32 " us after poll 0x%02X", this->reply_delay_us_, this->transmit_after_);
  } else {
    ESP_LOGCONFIG(TAG, "  Transmit: disabled (listen only)");
  }
  ESP_LOGCONFIG(TAG, "  Setpoint: index 0..%u -> %.1f + %.1f * index", this->sp_max_, this->sp_base_,
                this->sp_step_);
  if (this->modes_.empty())
    ESP_LOGCONFIG(TAG, "  Modes: none mapped; 'auto' means on, in the wall controller's mode");
}

void PanasonicRD::loop() {
  rdbus::RxByte rb[8];
  rdbus::Message msg[4];
  rdbus::Burst b;
  const uint32_t now = (uint32_t) esp_timer_get_time();

  auto deliver = [&](size_t nbytes) {
    for (size_t i = 0; i < nbytes; i++) {
      const size_t nm = this->fa_.push(rb[i], msg);
      for (size_t j = 0; j < nm; j++)
        this->on_message_(msg[j]);
    }
  };

  const uint32_t known = this->rx_.service(now);
  while (this->rx_.pop(&b)) {
    this->stats_.add(b);
    deliver(this->dec_.push(b, rb, 8));
  }
  deliver(this->dec_.flush(known, rb, 8));
  const size_t nm = this->fa_.flush(now, msg);
  for (size_t j = 0; j < nm; j++)
    this->on_message_(msg[j]);

  if (this->tx_ready_) {
    const auto *pending = this->sched_.current();
    const auto event = pending ? this->sched_.poll(now, rdbus::TxScheduler::echo_timeout_us(*pending, this->dec_.bit_us()))
                               : rdbus::TxScheduler::Event::NONE;
    switch (event) {
      case rdbus::TxScheduler::Event::COLLISION:
        ESP_LOGW(TAG, "No echo of our frame; retrying");
        break;
      case rdbus::TxScheduler::Event::GAVE_UP:
        ESP_LOGE(TAG, "Gave up sending a frame (no echo). Check the TX stage.");
        break;
      default:
        break;
    }
    // The reply slot is only ~3 ms wide and this loop runs every ~16 ms, so schedule
    // the exact start with a hardware timer as soon as the trigger poll is decoded.
    uint32_t start_at = 0;
    if (this->sched_.should_start_at(now, this->rx_.last_edge(), this->tx_.busy(), &start_at)) {
      static rdbus::Segment seg[rdbus::Transmitter::kMaxSeg];
      const auto *job = this->sched_.current();
      const size_t n = rdbus::encode_bytes(job->bytes, job->len, this->dec_.bit_us(), rdbus::Parity::EVEN, 0, seg,
                                           rdbus::Transmitter::kMaxSeg);
      if (n == 0 || !this->tx_.send(seg, n, start_at)) {
        ESP_LOGW(TAG, "Transmitter refused the frame");
      } else {
        ESP_LOGV(TAG, "Transmitting in %d us", (int) (int32_t) (start_at - now));
      }
    }
  }

  if (now - this->last_stats_log_ > 15000000) {
    this->last_stats_log_ = now;
    ESP_LOGD(TAG,
             "Bus: %" PRIu32 " bursts, %" PRIu32 " edges, RX level %d, carrier ~%.0f Hz, bit ~%.0f us, "
             "frames ok/bad %" PRIu32 "/%" PRIu32 ", ring overflows %" PRIu32,
             this->stats_.bursts(), this->rx_.edges(), gpio_get_level((gpio_num_t) this->rx_pin_),
             this->stats_.carrier_hz(), this->stats_.bit_us(), this->good_frames_, this->bad_frames_,
             this->rx_.overflows());
  }
}

void PanasonicRD::on_message_(const rdbus::Message &m) {
  switch (this->sched_.on_message(m)) {
    case rdbus::TxScheduler::Event::SENT_OK:
      ESP_LOGD(TAG, "Our frame was echoed correctly");
      break;
    case rdbus::TxScheduler::Event::COLLISION:
      ESP_LOGW(TAG, "Echo mismatch (collision?); retrying");
      break;
    case rdbus::TxScheduler::Event::GAVE_UP:
      ESP_LOGE(TAG, "Echo mismatch; gave up on this frame");
      break;
    default:
      break;
  }

  const bool quiet = m.kind == rdbus::MsgKind::POLL && !m.rx_error && !this->log_polls_;
  if (!quiet) {
    char hex[rdbus::kMaxMsg * 3 + 1];
    format_hex_pretty_to(hex, sizeof hex, m.data, m.len, ' ');
    ESP_LOGD(TAG, "%-5s %s%s%s", rdbus::kind_name(m.kind), hex,
             m.len > 1 ? (m.checksum_ok ? " [cs ok]" : " [cs BAD]") : "", m.rx_error ? " [rx error]" : "");
  }
  if (m.kind == rdbus::MsgKind::FRAME)
    this->good_frames_++;
  else if (m.kind == rdbus::MsgKind::BAD_FRAME)
    this->bad_frames_++;

  if (rdbus::apply_frame(m, &this->state_)) {
    this->publish_from_registers_();
    const int16_t f = this->state_.reg[rdbus::kRegFilter];
    if (this->filter_sensor_ != nullptr && f >= 0 && f != this->last_filter_) {
      this->last_filter_ = f;
      this->filter_sensor_->publish_state(f != 0);
    }
  }
}

void PanasonicRD::publish_from_registers_() {
  const auto &r = this->state_.reg;
  // Bit 0 = on; bit 2 (value 4) appears while a timer is set, so test only bit 0.
  if (r[rdbus::kRegPower] >= 0 && (r[rdbus::kRegPower] & 1) == 0) {
    this->mode = climate::CLIMATE_MODE_OFF;
  } else if (r[rdbus::kRegPower] >= 0) {
    climate::ClimateMode mode = climate::CLIMATE_MODE_AUTO;
    for (auto &mv : this->modes_)
      if (mv.value == r[rdbus::kRegMode])
        mode = mv.key;
    this->mode = mode;
  }
  if (r[rdbus::kRegSetpoint] >= 0)
    this->target_temperature = this->sp_base_ + this->sp_step_ * r[rdbus::kRegSetpoint];
  for (auto &fv : this->fans_)
    if (fv.value == r[rdbus::kRegFan])
      this->fan_mode = fv.key;
  ESP_LOGI(TAG, "State: power=%d mode=%d fan=%d vane=%d setpoint_index=%d", r[rdbus::kRegPower],
           r[rdbus::kRegMode], r[rdbus::kRegFan], r[rdbus::kRegVane], r[rdbus::kRegSetpoint]);
  this->publish_state();
}

climate::ClimateTraits PanasonicRD::traits() {
  auto t = climate::ClimateTraits();
  t.add_supported_mode(climate::CLIMATE_MODE_OFF);
  if (this->modes_.empty()) {
    t.add_supported_mode(climate::CLIMATE_MODE_AUTO);
  } else {
    for (auto &mv : this->modes_)
      t.add_supported_mode(mv.key);
  }
  for (auto &fv : this->fans_)
    t.add_supported_fan_mode(fv.key);
  t.set_visual_min_temperature(this->sp_base_);
  t.set_visual_max_temperature(this->sp_base_ + this->sp_step_ * this->sp_max_);
  t.set_visual_target_temperature_step(this->sp_step_);
  return t;
}

void PanasonicRD::control(const climate::ClimateCall &call) {
  if (!this->tx_ready_) {
    ESP_LOGW(TAG, "Transmit is disabled; ignoring the request");
    this->publish_state();  // revert the UI
    return;
  }
  const auto &r = this->state_.reg;
  if (call.get_mode().has_value()) {
    const auto mode = *call.get_mode();
    if (mode == climate::CLIMATE_MODE_OFF) {
      this->send_register(rdbus::kRegPower, 0);
    } else {
      if (r[rdbus::kRegPower] < 0 || (r[rdbus::kRegPower] & 1) == 0)
        this->send_register(rdbus::kRegPower, 1);
      for (auto &mv : this->modes_)
        if (mv.key == mode && mv.value != r[rdbus::kRegMode])
          this->send_register(rdbus::kRegMode, mv.value);
    }
  }
  if (call.get_target_temperature().has_value()) {
    const float t = *call.get_target_temperature();
    int idx = (int) lroundf((t - this->sp_base_) / this->sp_step_);
    idx = clamp(idx, 0, (int) this->sp_max_);
    this->send_register(rdbus::kRegSetpoint, (uint8_t) idx);
  }
  if (call.get_fan_mode().has_value()) {
    for (auto &fv : this->fans_)
      if (fv.key == *call.get_fan_mode())
        this->send_register(rdbus::kRegFan, fv.value);
  }
  // State is published when the unit's traffic (or our own echo) confirms the change.
}

bool PanasonicRD::send_register(uint8_t reg, uint8_t value) {
  const uint8_t payload[2] = {reg, value};
  uint8_t frame[rdbus::kMaxMsg];
  const size_t n = rdbus::build_frame(payload, 2, frame, sizeof frame);
  // Once is enough: each attempt waits for poll 0x81 (~2.7 s apart), the echo check
  // retries corrupted copies, and the controller's state dump confirms the change.
  return this->send_raw(std::vector<uint8_t>(frame, frame + n), 1);
}

bool PanasonicRD::send_raw(const std::vector<uint8_t> &bytes, uint8_t times) {
  if (!this->tx_ready_) {
    ESP_LOGW(TAG, "Transmit is disabled");
    return false;
  }
  if (!this->sched_.enqueue(bytes.data(), bytes.size(), times)) {
    ESP_LOGW(TAG, "Transmit queue full");
    return false;
  }
  return true;
}

}  // namespace esphome::panasonic_rd
