from __future__ import annotations

from pymavlink import mavutil
import math
import time


ROVER_PORT = 5762
BOAT_PORT = 5772
COPTER_PORT = 5782

# Fixed coordinates (lat, lon).
SLIPWAY_STATION = (35.876991, 140.348026)
RIVER_PORT = (35.879768, 140.348495)
MAIN_PORT = (35.878275, 140.338069)
SEVEN_ELEVEN = (35.877518, 140.295439)

# Add intermediate waypoints here (lat, lon).
ROVER_WAYPOINTS = [
    (35.8778975, 140.3488612),
    (35.8784538, 140.3482497),
    (35.8786451, 140.3480673),
    (35.8788624, 140.3483462),
    (35.8789841, 140.3482282),
    (35.8793405, 140.3485286),
    (35.8797665, 140.3483999),
]

BOAT_WAYPOINTS = [
    (35.8796882, 140.3486252),
    (35.8808966, 140.3474665),
    (35.8778888, 140.3413510),
    (35.8772107, 140.3395915),
    (35.8778192, 140.3384328),
    (35.8782191, 140.3380466),
]

COPTER_WAYPOINTS = [
    # (lat, lon),
]

ARRIVAL_RADIUS_M = 5.0
SURFACE_SPEED_M_S = 2.0
COPTER_ALT_M = 70.0
GLOBAL_POS_HZ = 5
WAIT_MSG_LOG_S = 5.0
LAND_TIMEOUT_S = 60.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class VehicleController:
    def __init__(self, name: str, port: int, source_system: int) -> None:
        self.name = name
        self.port = port
        self.source_system = source_system
        self.master = self._connect()

    def _connect(self) -> mavutil.mavfile:
        master = mavutil.mavlink_connection(
            f"tcp:127.0.0.1:{self.port}",
            source_system=self.source_system,
            source_component=90,
        )
        master.wait_heartbeat(timeout=10)
        print(f"[OK] heartbeat sys={master.target_system} comp={master.target_component} on {self.port}")
        return master

    def set_mode(self, mode: str) -> None:
        mapping = self.master.mode_mapping()
        if mode not in mapping:
            raise RuntimeError(f"mode {mode} not in mapping: {list(mapping.keys())}")
        self.master.set_mode(mapping[mode])
        deadline = time.time() + 10
        while time.time() < deadline:
            self.master.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
            if self.master.flightmode == mode:
                return
        raise TimeoutError(f"failed to enter mode {mode}")

    def arm(self) -> None:
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0,
            1,
            0, 0, 0, 0, 0, 0,
        )
        self.master.recv_match(type="COMMAND_ACK", blocking=True, timeout=3)
        print(f"[OK] {self.name} arm command sent")

    def wait_armed(self, timeout_s: float = 10.0) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            self.master.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
            if self.master.motors_armed():
                return
        raise TimeoutError(f"{self.name} failed to arm")

    def log_statustext(self, timeout_s: float = 3.0) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            msg = self.master.recv_match(type="STATUSTEXT", blocking=True, timeout=1)
            if msg:
                print(f"[{self.name}] {msg.text}")

    def request_global_pos(self) -> None:
        interval_us = int(1_000_000 / GLOBAL_POS_HZ)
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
            0,
            mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT,
            interval_us,
            0, 0, 0, 0, 0,
        )

    def set_groundspeed(self, speed_m_s: float) -> None:
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED,
            0,
            1,
            speed_m_s,
            0,
            0, 0, 0, 0,
        )

    def goto_latlon(self, lat: float, lon: float, alt_m: float | None) -> None:
        if alt_m is None:
            alt_m = 0.0
        self.master.mav.set_position_target_global_int_send(
            0,
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            0b0000111111111000,
            int(lat * 1e7),
            int(lon * 1e7),
            alt_m,
            0, 0, 0,
            0, 0, 0,
            0, 0,
        )

    def wait_arrival(self, lat: float, lon: float, radius_m: float) -> None:
        last_log = time.time()
        while True:
            msg = self.master.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=2)
            if not msg:
                now = time.time()
                if now - last_log >= WAIT_MSG_LOG_S:
                    print("waiting for GLOBAL_POSITION_INT...")
                    last_log = now
                continue
            clat = msg.lat / 1e7
            clon = msg.lon / 1e7
            dist = haversine_m(clat, clon, lat, lon)
            print(f"pos lat={clat:.6f} lon={clon:.6f} dist={dist:.1f}m")
            if dist <= radius_m:
                return

    def goto_and_wait(self, lat: float, lon: float, alt_m: float, radius_m: float) -> None:
        last_send = 0.0
        last_log = time.time()
        while True:
            now = time.time()
            if now - last_send >= 1.0:
                self.goto_latlon(lat, lon, alt_m=alt_m)
                last_send = now
            msg = self.master.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=2)
            if not msg:
                if now - last_log >= WAIT_MSG_LOG_S:
                    print("waiting for GLOBAL_POSITION_INT...")
                    last_log = now
                continue
            clat = msg.lat / 1e7
            clon = msg.lon / 1e7
            dist = haversine_m(clat, clon, lat, lon)
            print(f"pos lat={clat:.6f} lon={clon:.6f} dist={dist:.1f}m")
            if dist <= radius_m:
                return

    def wait_altitude(self, target_alt_m: float, timeout_s: float = 30.0) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            msg = self.master.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=2)
            if not msg:
                continue
            alt = msg.relative_alt / 1000.0
            print(f"alt={alt:.1f}m")
            if alt >= target_alt_m - 0.5:
                return
        raise TimeoutError("takeoff timeout (altitude did not increase)")

    def wait_disarm(self, timeout_s: float) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            msg = self.master.recv_match(type="HEARTBEAT", blocking=True, timeout=2)
            if not msg:
                continue
            armed = msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
            if not armed:
                return
        raise TimeoutError("landing timeout (still armed)")

    def run_surface_route(self, waypoints: list[tuple[float, float]]) -> None:
        print(f"[{self.name}] connect")
        self.set_mode("GUIDED")
        self.arm()
        self.set_groundspeed(SURFACE_SPEED_M_S)
        self.request_global_pos()
        for i, (lat, lon) in enumerate(waypoints, 1):
            print(f"[{self.name}] goto WP{i}")
            self.goto_latlon(lat, lon, alt_m=None)
            self.wait_arrival(lat, lon, ARRIVAL_RADIUS_M)
        print(f"[{self.name}] arrived")

    def run_copter_route(self, waypoints: list[tuple[float, float]]) -> None:
        print(f"[{self.name}] connect")
        self.set_mode("GUIDED")
        self.arm()
        try:
            self.wait_armed()
        except TimeoutError:
            self.log_statustext()
            raise
        self.request_global_pos()
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0,
            0, 0, 0, 0, 0, 0,
            COPTER_ALT_M,
        )
        ack = self.master.recv_match(type="COMMAND_ACK", blocking=True, timeout=5)
        print(f"[{self.name}] takeoff ack: {ack}")
        self.wait_altitude(COPTER_ALT_M)
        for i, (lat, lon) in enumerate(waypoints, 1):
            print(f"[{self.name}] goto WP{i}")
            self.goto_and_wait(lat, lon, alt_m=COPTER_ALT_M, radius_m=ARRIVAL_RADIUS_M)
        self.set_mode("LAND")
        print(f"[{self.name}] LAND")
        self.wait_disarm(LAND_TIMEOUT_S)
        print(f"[{self.name}] landed")


def main() -> None:
    rover_route = [SLIPWAY_STATION, *ROVER_WAYPOINTS, RIVER_PORT]
    boat_route = [RIVER_PORT, *BOAT_WAYPOINTS, MAIN_PORT]
    copter_route = [MAIN_PORT, *COPTER_WAYPOINTS, SEVEN_ELEVEN]

    rover = VehicleController("ROVER", ROVER_PORT, 201)
    boat = VehicleController("BOAT", BOAT_PORT, 202)
    copter = VehicleController("COPTER", COPTER_PORT, 203)

    rover.run_surface_route(rover_route)
    boat.run_surface_route(boat_route)
    copter.run_copter_route(copter_route)
    print("[DONE] all legs complete")


if __name__ == "__main__":
    main()
