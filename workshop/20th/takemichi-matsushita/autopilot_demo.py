import math
import sys
import time
from typing import Optional

from pymavlink import mavutil


def to_quaternion(roll: float = 0.0, pitch: float = 0.0, yaw: float = 0.0):
    """ロール・ピッチ・ヨー(度)をクオータニオンに変換して返す。"""
    # 角度(deg)からクオータニオンを生成
    t0 = math.cos(math.radians(yaw * 0.5))
    t1 = math.sin(math.radians(yaw * 0.5))
    t2 = math.cos(math.radians(roll * 0.5))
    t3 = math.sin(math.radians(roll * 0.5))
    t4 = math.cos(math.radians(pitch * 0.5))
    t5 = math.sin(math.radians(pitch * 0.5))

    w = t0 * t2 * t4 + t1 * t3 * t5
    x = t0 * t3 * t4 - t1 * t2 * t5
    y = t0 * t2 * t5 + t1 * t3 * t4
    z = t1 * t2 * t4 - t0 * t3 * t5

    return [w, x, y, z]


def wait_mode(master: mavutil.mavfile, mode: str, timeout: float = 10) -> bool:
    """指定モードに切り替わるまでハートビートを確認しつつ待機する。"""
    # HEARTBEATから現在のモード文字列を復元して確認する
    mode_lookup = {v: k for k, v in master.mode_mapping().items()}
    start = time.time()
    while time.time() - start < timeout:
        msg = master.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if not msg:
            continue
        current_mode = master.flightmode
        if current_mode == mode:
            return True
        # flightmodeに反映されないケースに備えてcustom_modeからデコード
        custom_mode = getattr(msg, "custom_mode", None)
        if custom_mode is not None and mode_lookup.get(custom_mode) == mode:
            return True
        time.sleep(0.1)
    return False


def wait_altitude(master: mavutil.mavfile, target_alt: float, tolerance: float = 0.5, timeout: float = 30) -> bool:
    """目標高度に達するまで位置情報を受信し続けて確認する。"""
    start = time.time()
    while time.time() - start < timeout:
        msg = master.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=1)
        if not msg:
            continue
        current_alt = msg.relative_alt / 1000.0
        print(f"高度: {current_alt:.2f} m")
        if current_alt >= target_alt - tolerance:
            return True
    return False


def wait_position(
    master: mavutil.mavfile,
    lat: float,
    lon: float,
    alt: float,
    tolerance_latlon: float = 0.00005,
    tolerance_alt: float = 0.5,
    timeout: float = 60,
) -> bool:
    """緯度経度・高度が目標値に入るまで待機する。"""
    start = time.time()
    while time.time() - start < timeout:
        msg = master.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=1)
        if not msg:
            continue
        current_lat = msg.lat / 1e7
        current_lon = msg.lon / 1e7
        current_alt = msg.relative_alt / 1000.0
        print(f"現在位置 lat={current_lat:.6f}, lon={current_lon:.6f}, alt={current_alt:.2f}")
        if (
            abs(current_lat - lat) < tolerance_latlon
            and abs(current_lon - lon) < tolerance_latlon
            and abs(current_alt - alt) < tolerance_alt
        ):
            return True
    return False


def wait_disarm(master: mavutil.mavfile, timeout: float = 120) -> bool:
    """モーターがディスアームされるまでハートビートを待ちながら確認する。"""
    start = time.time()
    while time.time() - start < timeout:
        # ハートビートを確実に受信してarmed状態を更新する
        master.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if not master.motors_armed():
            return True
        time.sleep(0.5)
    return False


def send_attitude(master: mavutil.mavfile, roll: float, pitch: float, yaw: float, thrust: float, duration: float = 2.0):
    """指定時間、姿勢とスラストを維持するよう角度指令を周期送信する。"""
    # 一定時間態勢を保つため、短い周期で送信し続ける
    quat = to_quaternion(roll, pitch, yaw)
    end_time = time.time() + duration
    while time.time() < end_time:
        master.mav.set_attitude_target_send(
            0,
            master.target_system,
            master.target_component,
            0b00000100,  # 角速度は無視して角度のみ指令
            quat,
            0,
            0,
            0,
            thrust,
        )
        time.sleep(0.1)


def set_rtl_altitude(master: mavutil.mavfile, altitude_m: float, timeout: float = 5.0) -> bool:
    """RTL_ALTパラメータをメートル指定で設定し、反映を確認する。"""
    rtl_alt_cm = int(altitude_m * 100)
    master.mav.param_set_send(
        master.target_system,
        master.target_component,
        b"RTL_ALT",
        rtl_alt_cm,
        mavutil.mavlink.MAV_PARAM_TYPE_INT32,
    )
    start = time.time()
    while time.time() - start < timeout:
        msg = master.recv_match(type="PARAM_VALUE", blocking=True, timeout=1)
        if not msg:
            continue
        param_id = getattr(msg, "param_id", b"")
        if isinstance(param_id, (bytes, bytearray)):
            param_id = param_id.decode("utf-8", errors="ignore")
        param_id = str(param_id).strip("\x00")
        if param_id == "RTL_ALT":
            return True
    return False


def main():
    """GUIDED離陸から目標地点への移動、RTL帰還までのデモフローを実行する。"""
    # 機体への接続
    master: mavutil.mavfile = mavutil.mavlink_connection(
        device="127.0.0.1:14551", source_system=1, source_component=90
    )
    master.wait_heartbeat()
    print("接続完了")

    # GUIDEDモードへ変更
    mode = "GUIDED"
    if mode not in master.mode_mapping():
        print("GUIDEDモードが見つかりません")
        sys.exit(1)
    master.set_mode(master.mode_mapping()[mode])
    if not wait_mode(master, mode):
        print("モード変更に失敗しました")
        sys.exit(1)
    print("モード変更完了")

    # アームと離陸
    master.arducopter_arm()
    master.motors_armed_wait()
    target_altitude = 10
    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        target_altitude,
    )
    # 位置メッセージを高頻度で受信
    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
        0,
        mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT,
        200000,  # 5Hz
        0,
        0,
        0,
        0,
        0,
    )
    if not wait_altitude(master, target_altitude):
        print("指定高度に到達できませんでした")
        sys.exit(1)
    print("離陸完了")

    # 目標位置へ移動
    target_lat = 35.8782539
    target_lon = 140.3383577
    master.mav.set_position_target_global_int_send(
        0,
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        0b0000111111111000,  # 速度・加速度無視、位置のみ指令
        int(target_lat * 1e7),
        int(target_lon * 1e7),
        target_altitude,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    if not wait_position(master, target_lat, target_lon, target_altitude):
        print("目的地へ到達できませんでした")
        sys.exit(1)
    print("目的地に到達")
    print("10秒待機後にRTLで帰還します")
    time.sleep(10)

    # RTL高度をパラメータで設定（メートル指定）
    rtl_altitude = 50
    if not set_rtl_altitude(master, rtl_altitude):
        print(f"RTL高度({rtl_altitude}m)の設定確認に失敗しました。機体側の値が使用されます。")

    rtl_mode = "RTL"
    if rtl_mode not in master.mode_mapping():
        print("RTLモードが見つかりません")
        sys.exit(1)
    master.set_mode(master.mode_mapping()[rtl_mode])
    if not wait_mode(master, rtl_mode):
        print("RTLモードへの切替に失敗しました")
        sys.exit(1)
    print("RTL発動、離陸ポイントへ帰還します")
    if not wait_disarm(master):
        print("着陸・ディスアームを確認できませんでした")
    else:
        print("着陸完了、ディスアーム済み")

    master.close()
    print("終了")


if __name__ == "__main__":
    main()
