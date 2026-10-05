# Release notes

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/).

## 1.0.0 — 2026-10-04

First release of the Raspberry Pi 5 PCA9685 micro servo controller.

### Added

- ServoKit demo on channel 15 (`servo_test.py`) and channel 0 (`test_servo_i2c.py`)
- Low-level PCA9685 helper (`servo_api.py`) with `set_servo_angle` and `release_servo`
- ServoKit wrapper that logs decoded PCA9685 I2C register writes (`servo_controller.py`)
- FastAPI server with REST endpoints, WebSocket I2C monitor, and web UI (`server.py`, `static/index.html`)
- Hardware wiring, calibration, and troubleshooting guide (`README.md`)
- Versioned pre-commit hook that checks Python syntax and blocks secrets and generated files
- Commitizen setup (`cz commit`) for Conventional Commits, with a commit-msg check

### Notes

- Default pulse range is 500–2500 µs at 50 Hz on I2C address `0x40`
- Releasing PWM after a move lets the servo go limp and cool down
