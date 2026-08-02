import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
import uvicorn

from pymavlink.dialects.v20 import ardupilotmega as mavlink_module
from pymavlink import mavutil

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== Constants ==========
DEFAULT_CONNECTION = "tcp:127.0.0.1:5762"
SERVER_PORT = 9999
EXECUTOR = ThreadPoolExecutor(max_workers=4)

# MAVLink message constants
MAV_CMD_COMPONENT_ARM_DISARM = 400
MAV_CMD_NAV_TAKEOFF = 22
MAV_CMD_NAV_LAND = 21
MAV_MODE_FLAG_SAFETY_ARMED = 128
MAV_FRAME_GLOBAL_RELATIVE_ALT_INT = 10
MAV_TYPE_GCS = 5
MAV_AUTOPILOT_INVALID = 0

# ========== Global State ==========
state: Dict[str, Any] = {
    "connected": False,
    "armed": False,
    "mode": "UNKNOWN",
    "latitude": 0.0,
    "longitude": 0.0,
    "altitude": 0.0,
    "heading": 0,
}

vehicle: Optional[mavutil.mavfile] = None
target_system = 1
target_component = 1
ws_manager: Optional["WebSocketManager"] = None


# ========== FastAPI Setup ==========
app = FastAPI(title="Drone Web App")
app.mount("/static", StaticFiles(directory="../frontend"), name="static")


@app.get("/")
async def root():
    return FileResponse("../frontend/index.html")


# ========== WebSocket Manager ==========
class WebSocketManager:
    def __init__(self):
        self.active_connection: Optional[WebSocket] = None
        self.receive_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connection = websocket
        logger.info("WebSocket connected")
        # Send initial state
        await self.send_state()

    async def disconnect(self):
        self.active_connection = None
        if self.receive_task:
            self.receive_task.cancel()
            try:
                await self.receive_task
            except asyncio.CancelledError:
                pass
        logger.info("WebSocket disconnected")

    async def send_message(self, msg: Dict[str, Any]):
        if self.active_connection:
            try:
                await self.active_connection.send_json(msg)
            except Exception as e:
                logger.error(f"Error sending message: {e}")

    async def send_state(self):
        await self.send_message({"type": "state", "state": state})

    async def send_status(self, message: str):
        await self.send_message({"type": "status", "message": message})

    async def receive_commands(self):
        if not self.active_connection:
            return
        try:
            while True:
                data = await self.active_connection.receive_json()
                await handle_command(data)
        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
            await self.disconnect()
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            await self.disconnect()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global ws_manager
    ws_manager = WebSocketManager()
    await ws_manager.connect(websocket)
    await ws_manager.receive_commands()


# ========== Command Handlers ==========
async def handle_command(command: Dict[str, Any]):
    cmd_type = command.get("type")
    logger.info(f"Received command: {cmd_type}")

    if cmd_type == "connect":
        asyncio.create_task(connect_vehicle())
    elif cmd_type == "arm":
        await arm_disarm(True)
    elif cmd_type == "disarm":
        await arm_disarm(False)
    elif cmd_type == "takeoff":
        altitude = command.get("altitude", 10)
        await takeoff(altitude)
    elif cmd_type == "land":
        await land()
    elif cmd_type == "goto":
        lat = command.get("latitude")
        lon = command.get("longitude")
        alt = command.get("altitude")
        await goto(lat, lon, alt)
    elif cmd_type == "mode":
        mode = command.get("mode", "GUIDED")
        await set_mode(mode)
    else:
        await ws_manager.send_status(f"Unknown command: {cmd_type}")


async def connect_vehicle():
    global vehicle, state, target_system, target_component
    if state["connected"]:
        await ws_manager.send_status("Already connected")
        return

    def blocking_connect():
        try:
            logger.info(f"Connecting to {DEFAULT_CONNECTION}...")
            v = mavutil.mavlink_connection(DEFAULT_CONNECTION, baud=115200)
            logger.info("Waiting for heartbeat...")
            v.wait_heartbeat()
            logger.info("Connected!")
            return v
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return None

    vehicle = await asyncio.get_event_loop().run_in_executor(
        EXECUTOR, blocking_connect
    )

    if vehicle:
        state["connected"] = True
        # Request data streams
        request_data_streams()
        await ws_manager.send_status("Vehicle connected")
        # Start MAVLink receive loop
        asyncio.create_task(receive_mavlink_messages())
    else:
        await ws_manager.send_status("Failed to connect to vehicle")


def request_data_streams():
    if not vehicle:
        return
    try:
        # Request GLOBAL_POSITION_INT and HEARTBEAT
        vehicle.mav.request_data_stream_send(
            target_system, target_component, 33, 10, 1
        )  # GLOBAL_POSITION_INT
    except Exception as e:
        logger.error(f"Error requesting data streams: {e}")


async def receive_mavlink_messages():
    global state, target_system, target_component
    while vehicle and state["connected"]:
        try:
            def blocking_recv():
                return vehicle.recv_match(blocking=True, timeout=0.1)

            msg = await asyncio.get_event_loop().run_in_executor(
                EXECUTOR, blocking_recv
            )

            if msg:
                # Filter HEARTBEAT by source
                if msg.get_type() == "HEARTBEAT":
                    if msg.type == MAV_TYPE_GCS or msg.autopilot == MAV_AUTOPILOT_INVALID:
                        continue
                    target_system = msg.get_srcSystem()
                    target_component = msg.get_srcComponent()
                    # Update armed state and mode
                    state["armed"] = bool(msg.base_mode & MAV_MODE_FLAG_SAFETY_ARMED)
                    mode_id = msg.custom_mode
                    if hasattr(vehicle, "mode_mapping"):
                        mode_map = vehicle.mode_mapping()
                        state["mode"] = (
                            mode_map.get(mode_id, "UNKNOWN") if mode_map else "UNKNOWN"
                        )

                elif msg.get_type() == "GLOBAL_POSITION_INT":
                    # Convert units: lat/lon (*1e7), altitude (mm->m)
                    state["latitude"] = msg.lat / 1e7
                    state["longitude"] = msg.lon / 1e7
                    state["altitude"] = msg.relative_alt / 1000.0
                    if msg.hdg != 65535:
                        state["heading"] = msg.hdg / 100

                await ws_manager.send_state()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"MAVLink receive error: {e}")
            await asyncio.sleep(0.1)


async def arm_disarm(arm: bool):
    if not vehicle or not state["connected"]:
        await ws_manager.send_status("Vehicle not connected")
        return

    try:
        param1 = 1 if arm else 0
        vehicle.mav.command_long_send(
            target_system,
            target_component,
            MAV_CMD_COMPONENT_ARM_DISARM,
            0,
            param1,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        action = "Arming" if arm else "Disarming"
        await ws_manager.send_status(f"{action}...")
    except Exception as e:
        logger.error(f"Arm/Disarm error: {e}")
        await ws_manager.send_status(f"Error: {e}")


async def takeoff(altitude: float):
    if not vehicle or not state["connected"]:
        await ws_manager.send_status("Vehicle not connected")
        return

    try:
        # Switch to GUIDED mode first
        await set_mode("GUIDED")
        await asyncio.sleep(1)

        # Send takeoff command
        vehicle.mav.command_long_send(
            target_system,
            target_component,
            MAV_CMD_NAV_TAKEOFF,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            altitude,
        )
        await ws_manager.send_status(f"Taking off to {altitude}m")
    except Exception as e:
        logger.error(f"Takeoff error: {e}")
        await ws_manager.send_status(f"Takeoff error: {e}")


async def land():
    if not vehicle or not state["connected"]:
        await ws_manager.send_status("Vehicle not connected")
        return

    try:
        vehicle.mav.command_long_send(
            target_system,
            target_component,
            MAV_CMD_NAV_LAND,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        await ws_manager.send_status("Landing...")
    except Exception as e:
        logger.error(f"Land error: {e}")
        await ws_manager.send_status(f"Land error: {e}")


async def goto(latitude: float, longitude: float, altitude: float):
    if not vehicle or not state["connected"]:
        await ws_manager.send_status("Vehicle not connected")
        return

    try:
        # Switch to GUIDED mode first
        await set_mode("GUIDED")
        await asyncio.sleep(1)

        # Convert to MAVLink units
        lat_int = int(latitude * 1e7)
        lon_int = int(longitude * 1e7)
        alt_int = int(altitude * 1000)

        # Type mask: only position valid, no velocity/accel/yaw
        type_mask = 0b0000111111111000

        vehicle.mav.set_position_target_global_int_send(
            0,  # time_boot_ms
            target_system,
            target_component,
            MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            type_mask,
            lat_int,
            lon_int,
            alt_int,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        await ws_manager.send_status(
            f"Going to {latitude:.6f}, {longitude:.6f}, {altitude}m"
        )
    except Exception as e:
        logger.error(f"Goto error: {e}")
        await ws_manager.send_status(f"Goto error: {e}")


async def set_mode(mode_name: str):
    if not vehicle or not state["connected"]:
        await ws_manager.send_status("Vehicle not connected")
        return

    try:
        mode_id = vehicle.mode_mapping().get(mode_name)
        if mode_id is None:
            await ws_manager.send_status(f"Unknown mode: {mode_name}")
            return

        vehicle.set_mode(mode_id)
        await ws_manager.send_status(f"Mode changed to {mode_name}")
    except Exception as e:
        logger.error(f"Mode change error: {e}")
        await ws_manager.send_status(f"Mode change error: {e}")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=SERVER_PORT)
