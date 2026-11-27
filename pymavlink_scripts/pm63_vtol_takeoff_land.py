"""VTOL（QuadPlane）: GUIDED で 3 m まで垂直に離陸し、QLAND でその場に着陸する。

起動: sim_vehicle.py -v Plane --frame quadplane -w -L Kawachi
"""
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


def wait_until(condition, message, timeout):
    """位置を見ながら、condition(位置) が真になるまで待つ"""
    end = time.time() + timeout
    shown = 0
    while time.time() < end:
        msg = get_position()
        if time.time() - shown >= 1:
            print(f"  高度: {msg.relative_alt / 1000:.1f} m")
            shown = time.time()
        if condition(msg):
            print(message)
            return
    sys.exit(f"時間内に完了しませんでした: {message}")


def wait_disarmed(timeout=120):
    """着陸して、自動で DISARM されるのを待つ"""
    end = time.time() + timeout
    while master.motors_armed():
        if time.time() > end:
            sys.exit("DISARM されません")
        master.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
    print("着陸して DISARM されました")

# GLOBAL_POSITION_INT(33) を 5Hz で受信する
master.mav.command_long_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
    0, 33, 200000, 0, 0, 0, 0, 0)

set_mode("GUIDED")
arm()

command = mavutil.mavlink.MAV_CMD_NAV_TAKEOFF
master.mav.command_long_send(
    master.target_system, master.target_component,
    command, 0, 0, 0, 0, 0, 0, 0, 3)          # 高度 3 m

# 離陸コマンドの結果（COMMAND_ACK）を確認する
ack = None
end = time.time() + 3
while ack is None and time.time() < end:
    msg = master.recv_match(type="COMMAND_ACK", blocking=True, timeout=1)
    if msg is not None and msg.command == command:
        ack = msg
if ack is None or ack.result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
    sys.exit("離陸コマンドが受理されませんでした")
wait_until(lambda p: p.relative_alt / 1000 >= 2.8, "離陸完了", 30)

time.sleep(5)
set_mode("QLAND")                  # その場に降りる。QRTL は離陸地点に戻って降りる
wait_disarmed()
