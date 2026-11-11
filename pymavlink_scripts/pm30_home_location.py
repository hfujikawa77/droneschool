from pymavlink import mavutil
import sys
import time

# 機体への接続
master: mavutil.mavfile = mavutil.mavlink_connection(
    "tcp:127.0.0.1:5762", source_system=1, source_component=90)
master.wait_heartbeat()

# メッセージレート変更
# msg = master.mav.request_data_stream_encode(
#     master.target_system, master.target_component, 0, 10, 1)
# master.mav.send(msg)

deadline = time.time() + 10  # アームされるのを待つ時間（秒）
while True:
    # HOME_POSITIONメッセージを受信, アームのタイミングで受信できる
    msg = master.recv_match(type='HOME_POSITION', blocking=True, timeout=1)
    if msg is None and time.time() > deadline:
        print("HOME_POSITION が届きません。機体をアームすると届きます（ホーム位置はアーム時に確定します）")
        sys.exit(1)
    if msg is not None:
        # ホームロケーション情報を設定
        home_latitude = msg.latitude / 1.0e7
        home_longitude = msg.longitude / 1.0e7
        home_altitude = msg.altitude / 1000.0  # メートル単位に変換

        print(
            f"ホームロケーション: lat={home_latitude},lon={home_longitude},alt={home_altitude}")
        break  # ホームロケーションを取得したら終了
