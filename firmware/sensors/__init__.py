# SleepSense Pro - FSR408 Sensor Module
# Custom I2C driver for ADS1115 ADC (byte-level implementation, no adafruit library)
# Meets specification #10: byte-level communication over I2C bus

from .ads1115 import ADS1115
from .fsr408 import FSR408

__all__ = ["ADS1115", "FSR408"]
