import threading
import time
from pymavlink import mavutil


# ホームポジション取得処理
def receive_home_position(master: mavutil.mavfile):
    # 10秒待っても届かなければ、あきらめて終了する
    end = time.time() + 10
    while time.time() < end:
        msg = master.recv_match(type="HOME_POSITION", blocking=True, timeout=1)
        if msg is not None:
            home_latitude = msg.latitude / 1.0e7
            home_longitude = msg.longitude / 1.0e7
            home_altitude = msg.altitude / 1000.0

            print(
                f"ホームロケーション: lat={home_latitude}, lon={home_longitude}, alt={home_altitude}"
            )
            return
    print("HOME_POSITION が届きませんでした")


# 機体への接続
master: mavutil.mavfile = mavutil.mavlink_connection(
    "tcp:127.0.0.1:5762", source_system=1, source_component=90
)
master.wait_heartbeat()

# メッセージレート変更
msg = master.mav.request_data_stream_encode(
    master.target_system, master.target_component, 0, 10, 1
)
master.mav.send(msg)

# 別スレッドでホームポジション取得処理を呼び出し
thread = threading.Thread(target=receive_home_position, args=(master,), daemon=True)
thread.start()

# 機体のARM（送信しただけで、ARM の完了は待たない。実行後は ARM したままなので、あとで DISARM する）
master.arducopter_arm()
print("ARM を送信しました")

# スレッド終了待ち
thread.join()
