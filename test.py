#!/usr/bin/env python3
import time

from servo_api import release_servo, set_servo_angle

SERVO_CHANNEL = 15  # PCA9685 channel 0-15

for angle in (0, 90, 180):
    set_servo_angle(SERVO_CHANNEL, angle)
    time.sleep(1)

release_servo(SERVO_CHANNEL)
