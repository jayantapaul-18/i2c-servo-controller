import board
import busio
from adafruit_pca9685 import PCA9685

PULSE_MIN_US = 500
PULSE_MAX_US = 2500
SERVO_FREQUENCY_HZ = 50

i2c = busio.I2C(board.SCL, board.SDA)
pca = PCA9685(i2c, address=0x40)
pca.frequency = SERVO_FREQUENCY_HZ


def set_servo_angle(channel, angle):
    """Set servo angle (0-180°). Keeps PWM active until release_servo() is called."""
    pulse_us = PULSE_MIN_US + (angle / 180.0) * (PULSE_MAX_US - PULSE_MIN_US)
    duty = int(pulse_us / 20000 * 4096)
    pca.channels[channel].duty_cycle = duty


def release_servo(channel):
    """Stop PWM on a channel so the servo goes limp and cools down."""
    pca.channels[channel].duty_cycle = 0
