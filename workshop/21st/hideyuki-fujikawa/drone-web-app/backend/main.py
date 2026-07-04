import asyncio
import json
import os
import threading
import time
import functools
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pymavlink import mavutil

app = FastAPI()

# Mount static files for the frontend
app.mount("/static", StaticFiles(directory="../frontend"), name="static")

# Drone connection global variables
# BlueOS 上では bridge 経由になり localhost では届かないため、既定は host.docker.internal 経由の udpout。
connection_string = os.environ.get("MAV_ENDPOINT", "udpout:host.docker.internal:14550")
vehicle = None
drone_connected = False
MODE_MAP = {}
drone_status = {
    "connected": False,
    "armed": False,
    "mode": "UNKNOWN",
    "latitude": 0.0,
    "longitude": 0.0,
    "altitude": 0.0,
    "heading": 0,
}


def _connect_loop():
    """Connect to the vehicle in the background so uvicorn/register_service is never blocked."""
    global vehicle, drone_connected, MODE_MAP
    while vehicle is None:
        try:
            print(f"Attempting to connect to vehicle on: {connection_string}")
            m = mavutil.mavlink_connection(connection_string)
            m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                                  mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)

            # Router 経由だと GCS 自身の HEARTBEAT も混ざるので、autopilot 側の HEARTBEAT を特定する
            hb = None
            deadline = time.time() + 30
            while time.time() < deadline:
                msg = m.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
                if msg and msg.autopilot != mavutil.mavlink.MAV_AUTOPILOT_INVALID:
                    hb = msg
                    break
            if hb is None:
                print("No autopilot heartbeat yet, retrying...")
                continue

            m.target_system = hb.get_srcSystem()
            m.target_component = hb.get_srcComponent()
            # mode_mapping() は直近 HEARTBEAT の型を見るため誤爆しうる。機体タイプから一度だけ確定させる。
            MODE_MAP = mavutil.mode_mapping_byname(hb.type) or {}
            m.mav.request_data_stream_send(
                m.target_system, m.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)

            vehicle = m
            drone_connected = True
            drone_status["connected"] = True
            print(f"Heartbeat from system (system {m.target_system} component {m.target_component})")
        except Exception as e:
            print(f"connect retry: {e}")
            time.sleep(3)


threading.Thread(target=_connect_loop, daemon=True).start()


# --- MAVLink Helper Functions (adapted from CLI app) ---
async def set_mode(mode_name):
    if not vehicle or not drone_connected:
        return False

    print(f"Setting mode to {mode_name}...")
    if mode_name not in MODE_MAP:
        print(f"Unknown mode: {mode_name}")
        print("Available modes: ", list(MODE_MAP.keys()))
        return False

    mode_id = MODE_MAP[mode_name]
    vehicle.set_mode(mode_id)
    # Don't sleep here. Let the mavlink_reader report the mode change.
    print(f"Mode change command sent for {mode_name}.")
    return True

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
        1, 0, 0, 0, 0, 0, 0)
    # Don't sleep or assume success. The mavlink_reader will update the armed status
    # based on HEARTBEAT messages from the drone.
    print("Arm command sent.")

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
        0, 0, 0, 0, 0, 0, altitude)
    # Don't sleep. The mavlink_reader will report altitude changes.
    print("Takeoff command sent.")

async def land_vehicle():
    if not vehicle or not drone_connected:
        return

    print("Landing vehicle...")
    vehicle.mav.command_long_send(
        vehicle.target_system,
        vehicle.target_component,
        mavutil.mavlink.MAV_CMD_NAV_LAND,
        0,
        0, 0, 0, 0, 0, 0, 0)
    # Don't sleep. The mavlink_reader will report status changes.
    print("Land command sent.")

async def goto_location(latitude, longitude, altitude):
    if not vehicle or not drone_connected:
        return

    if not await set_mode("GUIDED"):
        print("Failed to set GUIDED mode. Cannot go to location.")
        return

    print(f"Moving to Lat: {latitude}, Lon: {longitude}, Alt: {altitude}")
    vehicle.mav.set_position_target_global_int_send(
        0,       # time_boot_ms (not used)
        vehicle.target_system,
        vehicle.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        0b0000111111111000, # type_mask (only position enabled)
        int(latitude * 1e7),
        int(longitude * 1e7),
        altitude,
        0,       # vx
        0,       # vy
        0,       # vz
        0, 0, 0, # afx, afy, afz (not used)
        0, 0)    # yaw, yaw_rate (not used)
    # Don't sleep. The mavlink_reader will report position changes.
    print("Go-to command sent.")

# --- WebSocket Endpoint ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket connected.")
    try:
        # Send initial drone status
        await websocket.send_json(drone_status)

        # Task to continuously read MAVLink messages and send status
        async def mavlink_reader():
            global drone_status
            loop = asyncio.get_event_loop()
            while True:
                try:
                    if vehicle and drone_connected:
                        # Use run_in_executor to avoid blocking the event loop.
                        # Add a timeout to recv_match to prevent it from blocking indefinitely,
                        # which can cause websocket keepalive pings to fail.
                        msg = await loop.run_in_executor(
                            None, functools.partial(vehicle.recv_match, blocking=True, timeout=0.1)
                        )
                        # Router 経由だと他機体/GCSのメッセージも流れてくるので自機のものだけ処理する
                        if (msg and msg.get_srcSystem() == vehicle.target_system
                                and msg.get_srcComponent() == vehicle.target_component):
                            # Update drone_status based on MAVLink messages
                            if msg.get_type() == 'GLOBAL_POSITION_INT':
                                drone_status["latitude"] = msg.lat / 1e7
                                drone_status["longitude"] = msg.lon / 1e7
                                drone_status["altitude"] = msg.relative_alt / 1000.0 # mm to meters (home-relative, matches GCS)
                                drone_status["heading"] = msg.hdg / 100.0 # centidegrees to degrees
                            elif msg.get_type() == 'HEARTBEAT':
                                # ARM 状態は base_mode の SAFETY_ARMED ビットで判定する
                                drone_status["armed"] = bool(
                                    msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)

                                # Reverse lookup for mode name from mode ID
                                mode_name = "UNKNOWN"
                                for name, mode_id_val in MODE_MAP.items():
                                    if mode_id_val == msg.custom_mode:
                                        mode_name = name
                                        break
                                drone_status["mode"] = mode_name

                            # Send updated status to frontend ONLY when there's a new message
                            await websocket.send_json(drone_status)
                        elif msg is None:
                            # No message received within the timeout, yield control briefly
                            await asyncio.sleep(0.01)
                    else:
                        # If not connected, wait a bit before checking again
                        await asyncio.sleep(1)
                except WebSocketDisconnect:
                    print("MAVLink reader: WebSocket disconnected, stopping task.")
                    break  # Exit the loop if the socket is closed
                except Exception as e:
                    print(f"An error occurred in mavlink_reader: {e}")
                    # If any other error occurs, log it and break the loop to be safe
                    break


        reader_task = asyncio.create_task(mavlink_reader())

        while True:
            data = await websocket.receive_text()
            command = json.loads(data)
            print(f"Received command: {command}")

            # Handle commands from frontend
            if command["type"] == "connect":
                # 接続はバックグラウンドスレッドが起動時から自動で試行しているので、
                # ここでは現在の接続状態を返すのみ。
                message = "Connected." if drone_connected else "Connecting..."
                await websocket.send_json({"type": "status", "message": message})
            elif command["type"] == "arm":
                await arm_vehicle()
                await websocket.send_json({"type": "status", "message": "Arm command sent."})
            elif command["type"] == "takeoff":
                altitude = float(command["altitude"])
                await takeoff_vehicle(altitude)
                await websocket.send_json({"type": "status", "message": f"Takeoff to {altitude}m command sent."})
            elif command["type"] == "land":
                await land_vehicle()
                await websocket.send_json({"type": "status", "message": "Land command sent."})
            elif command["type"] == "goto":
                lat = float(command["latitude"])
                lon = float(command["longitude"])
                alt = float(command["altitude"])
                await goto_location(lat, lon, alt)
                await websocket.send_json({"type": "status", "message": f"GoTo {lat},{lon},{alt} command sent."})
            elif command["type"] == "mode":
                mode_name = command["mode_name"].upper()
                await set_mode(mode_name)
                await websocket.send_json({"type": "status", "message": f"Mode change to {mode_name} command sent."})

    except WebSocketDisconnect:
        print("WebSocket disconnected.")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        if 'reader_task' in locals() and not reader_task.done():
            reader_task.cancel()

# --- HTTP Endpoints for BlueOS Extension ---
@app.get("/")
async def get_frontend():
    # Serve the index.html file from the frontend directory
    with open("../frontend/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/register_service")
async def register_service():
    return {
        "name": "Drone Web App",
        "description": "Webブラウザからドローンを操作する Pymavlink + FastAPI 製アプリ",
        "icon": "mdi-drone",
        "company": "",
        "version": "1.0.0",
        "webpage": "",
        "api": "/docs",
        # WebSocket はプロキシ非対応のため、BlueOS の右ペイン埋め込みではなく直接ポートを開く
        "avoid_iframes": True,
    }
