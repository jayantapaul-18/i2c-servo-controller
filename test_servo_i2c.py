#!/usr/bin/env python3
import time

from adafruit_servokit import ServoKit

kit = ServoKit(channels=16, address=0x40)

SERVO_CHANNEL = 0  # PCA9685 channel 0-15

kit.servo[SERVO_CHANNEL].set_pulse_width_range(500, 2500)

for angle in (0, 90, 180):
    kit.servo[SERVO_CHANNEL].angle = angle
    time.sleep(1)

kit.servo[SERVO_CHANNEL].angle = None  # stop PWM (servo goes limp)
