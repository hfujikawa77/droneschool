from pymavlink import mavutil
import sys
import time

# 機体への接続
master: mavutil.mavfile = mavutil.mavlink_connection(
    "tcp:127.0.0.1:5762", source_system=1, source_component=90)
master.wait_heartbeat()

# ホーム位置は、待っているだけでは届かない。
# MAV_CMD_GET_HOME_POSITION コマンドで要求すると、HOME_POSITION が返ってくる。
# ホーム位置は EKF / GPS の準備ができた時点で確定するので、アームは要らない
master.mav.command_long_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_CMD_GET_HOME_POSITION, 0,
    0, 0, 0, 0, 0, 0, 0)

deadline = time.time() + 10  # 返事を待つ時間（秒）
while True:
    # HOME_POSITIONメッセージを受信
    msg = master.recv_match(type='HOME_POSITION', blocking=True, timeout=1)
    if msg is None and time.time() > deadline:
        print("HOME_POSITION が届きませんでした")
        sys.exit(1)
    if msg is not None:
        # ホームロケーション情報を設定
        home_latitude = msg.latitude / 1.0e7
        home_longitude = msg.longitude / 1.0e7
        home_altitude = msg.altitude / 1000.0  # メートル単位に変換

        print(
            f"ホームロケーション: lat={home_latitude},lon={home_longitude},alt={home_altitude}")
        break  # ホームロケーションを取得したら終了
