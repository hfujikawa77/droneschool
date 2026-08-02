import os
import asyncio
import json
import time
import functools
import threading
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pymavlink import mavutil

app = FastAPI()

# Mount static files for the frontend
app.mount("/static", StaticFiles(directory="../frontend"), name="static")

# --- Drone connection settings ---
# ローカル SITL 用（最重要）
connection_string = "udp:127.0.0.1:14550"

vehicle = None
drone_connected = False
MODE_MAP = {}
REVERSE_MODE_MAP = {}

drone_status = {
    "connected": False,
    "armed": False,
    "mode": "UNKNOWN",
    "latitude": 0.0,
    "longitude": 0.0,
    "altitude": 0.0,
    "heading": 0,
}

# --- Force GLOBAL_POSITION_INT (確実に位置情報を送らせる) ---
def force_position_stream(m):
    try:
        m.mav.command_long_send(
            m.target_system,
            m.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
            0,
            mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT,
            100000,  # 100ms = 10Hz
            0, 0, 0, 0, 0
        )
        print("GLOBAL_POSITION_INT forced at 10Hz")
    except Exception as e:
        print(f"Failed to force position stream: {e}")

# --- Connect to vehicle ---
def connect_to_vehicle():
    global vehicle, drone_connected, MODE_MAP, REVERSE_MODE_MAP

    def _connect():
        global vehicle, drone_connected, MODE_MAP, REVERSE_MODE_MAP

        while True:
            try:
                print(f"Attempting to connect to vehicle on: {connection_string}")
                m = mavutil.mavlink_connection(connection_string)

                # Send GCS heartbeat
                try:
                    m.mav.heartbeat_send(
                        mavutil.mavlink.MAV_TYPE_GCS,
                        mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                        0, 0, 0
                    )
                except:
                    pass

                # Wait for autopilot heartbeat
                hb = None
                deadline = time.time() + 30
                while time.time() < deadline:
                    msg = m.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
                    if msg and msg.autopilot != mavutil.mavlink.MAV_AUTOPILOT_INVALID:
                        hb = msg
                        break

                if hb is None:
                    print("No valid HEARTBEAT found, retrying...")
                    m.close()
                    time.sleep(3)
                    continue

                m.target_system = hb.get_srcSystem()
                m.target_component = hb.get_srcComponent()

                MODE_MAP = mavutil.mode_mapping_byname(hb.type) or {}
                REVERSE_MODE_MAP = {v: k for k, v in MODE_MAP.items()}

                vehicle = m
                drone_connected = True
                drone_status["connected"] = True

                print(f"Connected to vehicle (system {m.target_system}, component {m.target_component})")

                # Force position stream
                force_position_stream(m)

                return True

            except Exception as e:
                print(f"connect retry: {e}")
                time.sleep(3)

    threading.Thread(target=_connect, daemon=True).start()
    return True

# --- Mode change ---
async def set_mode(mode_name):
    if not vehicle or not drone_connected:
        return False

    print(f"Setting mode to {mode_name}...")
    if mode_name not in vehicle.mode_mapping():
        print(f"Unknown mode: {mode_name}")
        print("Available modes:", list(vehicle.mode_mapping().keys()))
        return False

    mode_id = vehicle.mode_mapping()[mode_name]
    vehicle.set_mode(mode_id)
    print(f"Mode change command sent for {mode_name}.")
    return True

# --- Arm ---
async def arm_vehicle():
    if not vehicle or not drone_connected:
        return

    if not await set_mode("GUIDED"):
        print("Failed to set GUIDED mode. Cannot arm.")
        return

    print("Arming motors...")
    vehicle.mav.command_long_send(
        vehicle.target_system,
        vehicle.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0,
        1, 0, 0, 0, 0, 0, 0
    )
    print("Arm command sent.")

# --- Takeoff ---
async def takeoff_vehicle(altitude):
    if not vehicle or not drone_connected:
        return

    if not await set_mode("GUIDED"):
        print("Failed to set GUIDED mode. Cannot takeoff.")
        return

    print(f"Taking off to altitude: {altitude} meters")
    vehicle.mav.command_long_send(
        vehicle.target_system,
        vehicle.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0,
        0, 0, 0, 0, 0, 0, altitude
    )
    print("Takeoff command sent.")

# --- Land ---
async def land_vehicle():
    if not vehicle or not drone_connected:
        return

    print("Landing vehicle...")
    vehicle.mav.command_long_send(
        vehicle.target_system,
        vehicle.target_component,
        mavutil.mavlink.MAV_CMD_NAV_LAND,
        0,
        0, 0, 0, 0, 0, 0, 0
    )
    print("Land command sent.")

# --- GoTo ---
async def goto_location(latitude, longitude, altitude):
    if not vehicle or not drone_connected:
        return

    if not await set_mode("GUIDED"):
        print("Failed to set GUIDED mode. Cannot go to location.")
        return

    print(f"Moving to Lat: {latitude}, Lon: {longitude}, Alt: {altitude}")
    vehicle.mav.set_position_target_global_int_send(
        0,
        vehicle.target_system,
        vehicle.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        0b0000111111111000,
        int(latitude * 1e7),
        int(longitude * 1e7),
        altitude,
        0, 0, 0,
        0, 0, 0,
        0, 0
    )
    print("Go-to command sent.")

# --- WebSocket ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket connected.")

    await websocket.send_json(drone_status)

    async def mavlink_reader():
        global drone_status
        loop = asyncio.get_event_loop()

        while True:
            try:
                if vehicle and drone_connected:
                    msg = await loop.run_in_executor(
                        None, functools.partial(vehicle.recv_match, blocking=True, timeout=0.1)
                    )

                    if msg:
                        src_sys = msg.get_srcSystem()
                        src_comp = msg.get_srcComponent()

                        if src_sys == vehicle.target_system and src_comp == vehicle.target_component:

                            if msg.get_type() == "GLOBAL_POSITION_INT":
                                drone_status["latitude"] = msg.lat / 1e7
                                drone_status["longitude"] = msg.lon / 1e7
                                drone_status["altitude"] = msg.relative_alt / 1000.0
                                drone_status["heading"] = msg.hdg / 100.0

                            elif msg.get_type() == "HEARTBEAT":
                                drone_status["armed"] = bool(
                                    msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                                )
                                drone_status["mode"] = REVERSE_MODE_MAP.get(msg.custom_mode, "UNKNOWN")

                            await websocket.send_json(drone_status)

                await asyncio.sleep(0.01)

            except WebSocketDisconnect:
                print("WebSocket disconnected.")
                break

    reader_task = asyncio.create_task(mavlink_reader())

    try:
        while True:
            data = await websocket.receive_text()
            command = json.loads(data)

            if command["type"] == "connect":
                if not drone_connected:
                    connect_to_vehicle()
                await websocket.send_json({"type": "status", "message": "Connection attempt initiated."})

            elif command["type"] == "arm":
                await arm_vehicle()
                await websocket.send_json({"type": "status", "message": "Arm command sent."})

            elif command["type"] == "takeoff":
                await takeoff_vehicle(float(command["altitude"]))
                await websocket.send_json({"type": "status", "message": "Takeoff command sent."})

            elif command["type"] == "land":
                await land_vehicle()
                await websocket.send_json({"type": "status", "message": "Land command sent."})

            elif command["type"] == "goto":
                await goto_location(
                    float(command["latitude"]),
                    float(command["longitude"]),
                    float(command["altitude"])
                )
                await websocket.send_json({"type": "status", "message": "GoTo command sent."})

            elif command["type"] == "mode":
                await set_mode(command["mode_name"].upper())
                await websocket.send_json({"type": "status", "message": "Mode change sent."})

    finally:
        if not reader_task.done():
            reader_task.cancel()

# --- Serve frontend ---
@app.get("/")
async def get_frontend():
    with open("../frontend/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

