"""Rover / ボート: 離陸の代わりに、GUIDED で約 90 m 北の目標へ走る。

起動: sim_vehicle.py -v Rover -w -L Kawachi （ボートは --frame motorboat を付ける）
"""
import math
import sys
import time

from pymavlink import mavutil

# 機体への接続
master: mavutil.mavfile = mavutil.mavlink_connection(
    "tcp:127.0.0.1:5762", source_system=1, source_component=90)
master.wait_heartbeat()
print("接続完了")


def set_mode(name, timeout=60):
    """モードを変更し、実際に変わるまで待つ（モード番号は機体ごとに違うので mode_mapping() で引く）

    SITL の起動直後は、位置が定まらず GUIDED などが拒否されるので、変わるまで送り直す。
    """
    end = time.time() + timeout
    while master.flightmode != name:
        if time.time() > end:
            sys.exit(f"モードを {name} に変更できませんでした（現在: {master.flightmode}）")
        master.set_mode_apm(master.mode_mapping()[name])
        master.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
    print(f"モード: {name}")


def arm(timeout=60):
    """ARM する。SITL の起動直後は拒否されるので、できるまで繰り返す"""
    end = time.time() + timeout
    while time.time() < end:
        master.arducopter_arm()
        retry = time.time() + 3
        while time.time() < retry:
            master.recv_match(blocking=True, timeout=1)
            if master.motors_armed():
                print("ARM 完了")
                return
    sys.exit("ARM できませんでした")


def get_position():
    """現在の位置（GLOBAL_POSITION_INT）を受け取る"""
    msg = master.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=5)
    if msg is None:
        sys.exit("位置が届きません")
    return msg


def send_target(lat, lon, alt):
    """目標の緯度・経度・高度を 1 回送る（lat, lon は 1e7 倍の整数）"""
    master.mav.set_position_target_global_int_send(
        0, master.target_system, master.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        0b0000111111111000,                 # 位置だけを使う
        lat, lon, alt,
        0, 0, 0, 0, 0, 0, 0, 0)

# GLOBAL_POSITION_INT(33) を 5Hz で受信する
master.mav.command_long_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
    0, 33, 200000, 0, 0, 0, 0, 0)

set_mode("GUIDED")
arm()

start = get_position()
target_lat = start.lat + 8000      # 緯度 0.0008 度（約 90 m）北
target_lon = start.lon
send_target(target_lat, target_lon, 0)
print("目標を送りました")

end = time.time() + 120
shown = 0
while time.time() < end:
    now = get_position()
    # 緯度・経度の差を、m に直す
    north = (target_lat - now.lat) / 1e7 * 111000
    east = (target_lon - now.lon) / 1e7 * 111000 * math.cos(math.radians(now.lat / 1e7))
    distance = math.hypot(north, east)
    if time.time() - shown >= 1:
        print(f"  目標まで: {distance:.0f} m")
        shown = time.time()
    if distance < 3:
        print("目標に到着しました（ARM のまま。MAVProxy で disarm）")
        break
else:
    sys.exit("目標に着きませんでした")
