#!/usr/bin/env python3
from adafruit_servokit import ServoKit

# Pi 5: header I2C is bus 1; PCA9685 default address 0x40
kit = ServoKit(channels=16, address=0x40)

SERVO_CHANNEL = 15  # PCA9685 channel 0-15

# Calibrate pulse range for your micro servo (typical SG90 values)
kit.servo[SERVO_CHANNEL].set_pulse_width_range(500, 2500)

# Move servo: 0° = min, 180° = max
kit.servo[SERVO_CHANNEL].angle = 0
import time
time.sleep(1)

kit.servo[SERVO_CHANNEL].angle = 90
time.sleep(1)

kit.servo[SERVO_CHANNEL].angle = 180
time.sleep(1)

kit.servo[SERVO_CHANNEL].angle = None  # stop PWM (servo goes limp)
