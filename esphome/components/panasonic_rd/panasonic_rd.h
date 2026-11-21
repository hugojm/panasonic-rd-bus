#pragma once

#include <vector>

#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/climate/climate.h"
#include "esphome/core/component.h"

#include "rdbus.h"
#include "rdbus_esp32.h"

namespace esphome::panasonic_rd {

// Climate entity on the Panasonic residential ducted wired-remote bus (R1/R2).
// Listens to the wall controller's traffic to track state; optionally transmits.
class PanasonicRD : public climate::Climate, public Component {
 public:
  void set_rx_pin(uint8_t pin, bool pullup) {
    this->rx_pin_ = pin;
    this->rx_pullup_ = pullup;
  }
  void set_tx_pin(uint8_t pin) { this->tx_pin_ = pin; }
  void set_transmit(bool v) { this->transmit_ = v; }
  void set_bit_time_us(uint32_t v) { this->bit_us_ = v; }
  void set_carrier_hz(uint32_t v) { this->carrier_hz_ = v; }
  void set_transmit_after(uint8_t b) { this->transmit_after_ = b; }
  void set_setpoint_map(float base, float step, uint8_t max_index) {
    this->sp_base_ = base;
    this->sp_step_ = step;
    this->sp_max_ = max_index;
  }
  void add_mode_value(climate::ClimateMode m, uint8_t v) { this->modes_.push_back({m, v}); }
  void add_fan_value(climate::ClimateFanMode f, uint8_t v) { this->fans_.push_back({f, v}); }
  void set_log_polls(bool v) { this->log_polls_ = v; }
  void set_filter_sensor(binary_sensor::BinarySensor *s) { this->filter_sensor_ = s; }

  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

  // For YAML lambdas / API actions. Both return false if transmit is off or the queue is full.
  bool send_register(uint8_t reg, uint8_t value);
  bool send_raw(const std::vector<uint8_t> &bytes, uint8_t times = 1);
  // Same frame the wall controller sends for "filter reset" (E3 02 66 00 35).
  bool reset_filter() { return this->send_register(rdbus::kRegFilter, 0); }

 protected:
  climate::ClimateTraits traits() override;
  void control(const climate::ClimateCall &call) override;

  void on_message_(const rdbus::Message &m);
  void publish_from_registers_();

  template<typename T> struct Mapping {
    T key;
    uint8_t value;
  };

  uint8_t rx_pin_{0};
  bool rx_pullup_{false};
  int tx_pin_{-1};
  bool transmit_{false};
  bool tx_ready_{false};
  uint32_t bit_us_{2020};
  uint32_t carrier_hz_{19200};
  int transmit_after_{-1};
  float sp_base_{16};
  float sp_step_{1};
  uint8_t sp_max_{14};
  bool log_polls_{false};
  binary_sensor::BinarySensor *filter_sensor_{nullptr};
  int16_t last_filter_{-1};
  std::vector<Mapping<climate::ClimateMode>> modes_;
  std::vector<Mapping<climate::ClimateFanMode>> fans_;

  rdbus::Receiver rx_;
  rdbus::Transmitter tx_;
  rdbus::ByteDecoder dec_;
  rdbus::FrameAssembler fa_;
  rdbus::BusStats stats_;
  rdbus::TxScheduler sched_;
  rdbus::UnitState state_;
  uint32_t last_stats_log_{0};
  uint32_t good_frames_{0}, bad_frames_{0};
};

}  // namespace esphome::panasonic_rd
