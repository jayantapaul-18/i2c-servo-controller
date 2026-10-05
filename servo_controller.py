"""Servo controller with PCA9685 I2C protocol logging."""

from __future__ import annotations

import asyncio
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from adafruit_servokit import ServoKit

PCA9685_ADDRESS = 0x40
I2C_BUS = 1
PULSE_MIN_US = 500
PULSE_MAX_US = 2500
SERVO_FREQUENCY_HZ = 50
MAX_CHANNELS = 16

# PCA9685 register map (from datasheet)
REG_MODE1 = 0x00
REG_MODE2 = 0x01
REG_PRESCALE = 0xFE
LED0_ON_L = 0x06


@dataclass
class I2CEvent:
    timestamp: str
    operation: str
    address: str
    channel: int | None
    angle: float | None
    pulse_us: int | None
    duty_cycle: int | None
    registers: list[dict[str, Any]]
    protocol_lines: list[str]
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "operation": self.operation,
            "address": self.address,
            "channel": self.channel,
            "angle": self.angle,
            "pulse_us": self.pulse_us,
            "duty_cycle": self.duty_cycle,
            "registers": self.registers,
            "protocol_lines": self.protocol_lines,
            "description": self.description,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _channel_base_register(channel: int) -> int:
    return LED0_ON_L + 4 * channel


def _angle_to_pulse_us(angle: float) -> int:
    clamped = max(0.0, min(180.0, angle))
    span = PULSE_MAX_US - PULSE_MIN_US
    return int(PULSE_MIN_US + (clamped / 180.0) * span)


def _pulse_us_to_duty(pulse_us: int) -> int:
    return int(pulse_us / 20000 * 4096)


def _build_pwm_registers(channel: int, duty: int) -> list[dict[str, Any]]:
    """Build PCA9685 LEDn ON/OFF register writes for a given duty cycle."""
    base = _channel_base_register(channel)
    on_l, on_h = 0x00, 0x00
    off_value = duty
    off_l = off_value & 0xFF
    off_h = (off_value >> 8) & 0x0F

    return [
        {"register": f"LED{channel}_ON_L", "addr": f"0x{base:02X}", "value": f"0x{on_l:02X}"},
        {"register": f"LED{channel}_ON_H", "addr": f"0x{base + 1:02X}", "value": f"0x{on_h:02X}"},
        {"register": f"LED{channel}_OFF_L", "addr": f"0x{base + 2:02X}", "value": f"0x{off_l:02X}"},
        {"register": f"LED{channel}_OFF_H", "addr": f"0x{base + 3:02X}", "value": f"0x{off_h:02X}"},
    ]


def _build_protocol_lines(
    operation: str,
    channel: int | None,
    registers: list[dict[str, Any]],
    extra: str = "",
) -> list[str]:
    lines = [
        "┌─ I2C START",
        f"├─ ADDR + W  → 0x{PCA9685_ADDRESS:02X}  (PCA9685)",
    ]
    if operation == "RELEASE":
        lines.append("├─ REG MODE2 or LED_OFF registers")
    elif operation == "INIT":
        lines.append(f"├─ REG MODE1  (0x{REG_MODE1:02X})")
        lines.append(f"├─ REG PRESCALE (0x{REG_PRESCALE:02X}) → 50 Hz")
    else:
        for reg in registers:
            lines.append(f"├─ REG {reg['register']} ({reg['addr']}) = {reg['value']}")

    if extra:
        lines.append(f"├─ {extra}")
    lines.append("└─ I2C STOP")
    return lines


class ServoController:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._kit = ServoKit(channels=MAX_CHANNELS, address=PCA9685_ADDRESS)
        for ch in range(MAX_CHANNELS):
            self._kit.servo[ch].set_pulse_width_range(PULSE_MIN_US, PULSE_MAX_US)

        self._events: deque[I2CEvent] = deque(maxlen=200)
        self._subscribers: set[asyncio.Queue] = set()
        self._channel_angles: dict[int, float | None] = {ch: None for ch in range(MAX_CHANNELS)}
        self._log_init_event()

    def _append_event(self, event: I2CEvent) -> None:
        self._events.append(event)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event.to_dict())
            except asyncio.QueueFull:
                pass

    def _log_init_event(self) -> None:
        registers = [
            {"register": "MODE1", "addr": f"0x{REG_MODE1:02X}", "value": "0x01"},
            {"register": "PRESCALE", "addr": f"0x{REG_PRESCALE:02X}", "value": "0x79"},
        ]
        event = I2CEvent(
            timestamp=_now_iso(),
            operation="INIT",
            address=f"0x{PCA9685_ADDRESS:02X}",
            channel=None,
            angle=None,
            pulse_us=None,
            duty_cycle=None,
            registers=registers,
            protocol_lines=_build_protocol_lines("INIT", None, registers, "50 Hz PWM enabled"),
            description="PCA9685 initialized on I2C bus 1 at address 0x40",
        )
        self._append_event(event)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def get_events(self, limit: int = 50) -> list[dict[str, Any]]:
        items = list(self._events)[-limit:]
        return [e.to_dict() for e in items]

    def get_status(self) -> dict[str, Any]:
        return {
            "device": "PCA9685",
            "i2c_bus": I2C_BUS,
            "i2c_address": f"0x{PCA9685_ADDRESS:02X}",
            "frequency_hz": SERVO_FREQUENCY_HZ,
            "pulse_range_us": [PULSE_MIN_US, PULSE_MAX_US],
            "channels": MAX_CHANNELS,
            "channel_angles": self._channel_angles,
        }

    def scan_i2c_bus(self) -> dict[str, Any]:
        try:
            result = subprocess.run(
                ["i2cdetect", "-y", str(I2C_BUS)],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            devices = []
            for line in result.stdout.splitlines():
                if ":" not in line:
                    continue
                _, addrs = line.split(":", 1)
                for token in addrs.split():
                    if token.strip() not in ("--", ""):
                        devices.append(f"0x{token.strip().upper()}")

            pca_found = f"0x{PCA9685_ADDRESS:02X}" in devices

            return {
                "bus": I2C_BUS,
                "raw": result.stdout,
                "devices": devices,
                "pca9685_detected": pca_found or f"0x{PCA9685_ADDRESS:02X}" in result.stdout,
            }
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return {"bus": I2C_BUS, "error": str(exc), "devices": [], "pca9685_detected": False}

    def set_angle(self, channel: int, angle: float) -> dict[str, Any]:
        if not 0 <= channel < MAX_CHANNELS:
            raise ValueError(f"Channel must be 0-{MAX_CHANNELS - 1}")
        if not 0 <= angle <= 180:
            raise ValueError("Angle must be 0-180")

        pulse_us = _angle_to_pulse_us(angle)
        duty = _pulse_us_to_duty(pulse_us)
        registers = _build_pwm_registers(channel, duty)
        protocol_lines = _build_protocol_lines(
            "SET_ANGLE",
            channel,
            registers,
            f"angle={angle}° pulse={pulse_us}µs duty={duty}/4096",
        )

        with self._lock:
            self._kit.servo[channel].angle = angle
            self._channel_angles[channel] = angle

        event = I2CEvent(
            timestamp=_now_iso(),
            operation="SET_ANGLE",
            address=f"0x{PCA9685_ADDRESS:02X}",
            channel=channel,
            angle=angle,
            pulse_us=pulse_us,
            duty_cycle=duty,
            registers=registers,
            protocol_lines=protocol_lines,
            description=f"Channel {channel} → {angle}° ({pulse_us} µs pulse)",
        )
        self._append_event(event)
        return event.to_dict()

    def release(self, channel: int) -> dict[str, Any]:
        if not 0 <= channel < MAX_CHANNELS:
            raise ValueError(f"Channel must be 0-{MAX_CHANNELS - 1}")

        registers = _build_pwm_registers(channel, 0)
        protocol_lines = _build_protocol_lines(
            "RELEASE",
            channel,
            registers,
            "PWM stopped — servo goes limp",
        )

        with self._lock:
            self._kit.servo[channel].angle = None
            self._channel_angles[channel] = None

        event = I2CEvent(
            timestamp=_now_iso(),
            operation="RELEASE",
            address=f"0x{PCA9685_ADDRESS:02X}",
            channel=channel,
            angle=None,
            pulse_us=None,
            duty_cycle=0,
            registers=registers,
            protocol_lines=protocol_lines,
            description=f"Channel {channel} PWM released",
        )
        self._append_event(event)
        return event.to_dict()

    def sweep(self, channel: int, angles: list[float] | None = None, delay_s: float = 1.0) -> list[dict[str, Any]]:
        if angles is None:
            angles = [0, 90, 180]
        results = []
        for angle in angles:
            results.append(self.set_angle(channel, angle))
            time.sleep(delay_s)
        results.append(self.release(channel))
        return results


_controller: ServoController | None = None
_controller_lock = threading.Lock()


def get_controller() -> ServoController:
    global _controller
    with _controller_lock:
        if _controller is None:
            _controller = ServoController()
        return _controller
