import esphome.codegen as cg
from esphome.components import binary_sensor, climate
import esphome.config_validation as cv
from esphome import pins
from esphome.components.esp32 import include_builtin_idf_component

DEPENDENCIES = ["esp32"]
AUTO_LOAD = ["binary_sensor"]

panasonic_rd_ns = cg.esphome_ns.namespace("panasonic_rd")
PanasonicRD = panasonic_rd_ns.class_("PanasonicRD", climate.Climate, cg.Component)

CONF_RX_PIN = "rx_pin"
CONF_RX_PULLUP = "rx_pullup"
CONF_TX_PIN = "tx_pin"
CONF_TRANSMIT = "transmit"
CONF_BIT_TIME = "bit_time"
CONF_CARRIER_FREQUENCY = "carrier_frequency"
CONF_TRANSMIT_AFTER = "transmit_after"
CONF_SETPOINT_BASE = "setpoint_base"
CONF_SETPOINT_STEP = "setpoint_step"
CONF_SETPOINT_MAX_INDEX = "setpoint_max_index"
CONF_MODE_VALUES = "mode_values"
CONF_FAN_VALUES = "fan_values"
CONF_LOG_POLLS = "log_polls"
CONF_FILTER_DIRTY = "filter_dirty"

# Register values confirmed on a W18BD3P + CZ-RD514C (captured 2026-11-21).
MODE_KEYS = {
    "cool": climate.CLIMATE_MODES["COOL"],
    "heat": climate.CLIMATE_MODES["HEAT"],
    "dry": climate.CLIMATE_MODES["DRY"],
    "fan_only": climate.CLIMATE_MODES["FAN_ONLY"],
    "auto": climate.CLIMATE_MODES["HEAT_COOL"],
}
FAN_KEYS = {
    "low": climate.CLIMATE_FAN_MODES["LOW"],
    "medium": climate.CLIMATE_FAN_MODES["MEDIUM"],
    "high": climate.CLIMATE_FAN_MODES["HIGH"],
    "auto": climate.CLIMATE_FAN_MODES["AUTO"],
}
FAN_DEFAULTS = {"low": 3, "medium": 2, "high": 1, "auto": 8}
MODE_DEFAULTS = {"cool": 2, "heat": 1, "dry": 4, "fan_only": 3, "auto": 8}

CONFIG_SCHEMA = cv.All(
    climate.climate_schema(PanasonicRD)
    .extend(
        {
            cv.Required(CONF_RX_PIN): pins.internal_gpio_input_pin_number,
            cv.Optional(CONF_RX_PULLUP, default=False): cv.boolean,
            cv.Optional(CONF_TX_PIN): pins.internal_gpio_output_pin_number,
            cv.Optional(CONF_TRANSMIT, default=False): cv.boolean,
            cv.Optional(CONF_BIT_TIME, default="2020us"): cv.All(
                cv.positive_time_period_microseconds,
                cv.Range(min=cv.TimePeriod(microseconds=500), max=cv.TimePeriod(microseconds=10000)),
            ),
            cv.Optional(CONF_CARRIER_FREQUENCY, default="19200Hz"): cv.All(
                cv.frequency, cv.Range(min=5000, max=100000)
            ),
            cv.Optional(CONF_TRANSMIT_AFTER): cv.hex_uint8_t,
            cv.Optional(CONF_SETPOINT_BASE, default=16.0): cv.float_,
            cv.Optional(CONF_SETPOINT_STEP, default=1.0): cv.positive_float,
            cv.Optional(CONF_SETPOINT_MAX_INDEX, default=14): cv.int_range(min=1, max=63),
            cv.Optional(CONF_MODE_VALUES, default=MODE_DEFAULTS): cv.Schema(
                {cv.Optional(k): cv.hex_uint8_t for k in MODE_KEYS}
            ),
            cv.Optional(CONF_FAN_VALUES, default=FAN_DEFAULTS): cv.Schema(
                {cv.Optional(k): cv.hex_uint8_t for k in FAN_KEYS}
            ),
            cv.Optional(CONF_LOG_POLLS, default=False): cv.boolean,
            # Indoor unit's "clean the filter" flag (register 0x66).
            cv.Optional(CONF_FILTER_DIRTY): binary_sensor.binary_sensor_schema(
                device_class="problem", icon="mdi:air-filter"
            ),
        }
    )
    .extend(cv.COMPONENT_SCHEMA),
    cv.only_on_esp32,
)


def _final_validate(config):
    if config[CONF_TRANSMIT] and CONF_TX_PIN not in config:
        raise cv.Invalid(f"'{CONF_TRANSMIT}: true' needs '{CONF_TX_PIN}'")
    return config


FINAL_VALIDATE_SCHEMA = _final_validate


async def to_code(config):
    include_builtin_idf_component("esp_driver_ledc")  # carrier for transmit
    var = await climate.new_climate(config)
    await cg.register_component(var, config)
    cg.add(var.set_rx_pin(config[CONF_RX_PIN], config[CONF_RX_PULLUP]))
    if CONF_TX_PIN in config:
        cg.add(var.set_tx_pin(config[CONF_TX_PIN]))
    cg.add(var.set_transmit(config[CONF_TRANSMIT]))
    cg.add(var.set_bit_time_us(config[CONF_BIT_TIME].total_microseconds))
    cg.add(var.set_carrier_hz(int(config[CONF_CARRIER_FREQUENCY])))
    if CONF_TRANSMIT_AFTER in config:
        cg.add(var.set_transmit_after(config[CONF_TRANSMIT_AFTER]))
    cg.add(
        var.set_setpoint_map(
            config[CONF_SETPOINT_BASE],
            config[CONF_SETPOINT_STEP],
            config[CONF_SETPOINT_MAX_INDEX],
        )
    )
    for key, value in config[CONF_MODE_VALUES].items():
        cg.add(var.add_mode_value(MODE_KEYS[key], value))
    for key, value in config[CONF_FAN_VALUES].items():
        cg.add(var.add_fan_value(FAN_KEYS[key], value))
    cg.add(var.set_log_polls(config[CONF_LOG_POLLS]))
    if CONF_FILTER_DIRTY in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_FILTER_DIRTY])
        cg.add(var.set_filter_sensor(sens))
