#!/usr/bin/env python3
"""FastAPI server for PCA9685 servo control with live I2C protocol monitor."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from servo_controller import get_controller

STATIC_DIR = Path(__file__).parent / "static"


class AngleRequest(BaseModel):
    angle: float = Field(ge=0, le=180)


class SweepRequest(BaseModel):
    angles: list[float] = Field(default=[0, 90, 180])
    delay_s: float = Field(default=1.0, ge=0.1, le=10)


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_controller()
    yield


app = FastAPI(
    title="Servo Control API",
    description="Control PCA9685 servos on Raspberry Pi 5 with live I2C protocol visualization",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
async def status():
    ctrl = get_controller()
    bus_scan = ctrl.scan_i2c_bus()
    return {**ctrl.get_status(), "i2c_scan": bus_scan}


@app.get("/api/i2c/events")
async def i2c_events(limit: int = 50):
    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be 1-200")
    return {"events": get_controller().get_events(limit)}


@app.get("/api/i2c/scan")
async def i2c_scan():
    return get_controller().scan_i2c_bus()


@app.post("/api/servo/{channel}/angle")
async def set_angle(channel: int, body: AngleRequest):
    try:
        event = get_controller().set_angle(channel, body.angle)
        return {"ok": True, "event": event}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/servo/{channel}/release")
async def release(channel: int):
    try:
        event = get_controller().release(channel)
        return {"ok": True, "event": event}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/servo/{channel}/sweep")
async def sweep(channel: int, body: SweepRequest):
    try:
        if not body.angles:
            raise ValueError("angles must not be empty")
        for angle in body.angles:
            if not 0 <= angle <= 180:
                raise ValueError("All angles must be 0-180")

        ctrl = get_controller()
        loop = asyncio.get_event_loop()
        events = await loop.run_in_executor(
            None,
            lambda: ctrl.sweep(channel, body.angles, body.delay_s),
        )
        return {"ok": True, "events": events}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.websocket("/ws/i2c")
async def i2c_websocket(websocket: WebSocket):
    await websocket.accept()
    ctrl = get_controller()
    queue = ctrl.subscribe()

    await websocket.send_json({
        "type": "history",
        "events": ctrl.get_events(30),
    })

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                await websocket.send_json({"type": "event", "event": event})
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        ctrl.unsubscribe(queue)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=5080, reload=False)
