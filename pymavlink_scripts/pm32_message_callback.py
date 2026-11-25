import threading
import time
from pymavlink import mavutil

# 受信スレッド + コールバック
# メッセージ名ごとに「届いたら呼ぶ関数」を登録しておき、
# 受信スレッドが recv_match() で受け取るたびに、その関数を呼ぶ。
#
# 注意: master（接続）を複数のスレッドで同時に使うと、受信の状態が壊れることがある。
#       このスクリプトでは、受信は受信スレッドだけが行い、
#       メインスレッドは master を使わず待つだけにしている。
#       送信（コマンドなど）もしたいときは、別の接続を作って使う。

# メッセージ名 -> 呼び出す関数のリスト
callbacks = {}


def on_message(name):
    """メッセージ名にコールバックを登録するデコレータ"""
    def register(func):
        callbacks.setdefault(name, []).append(func)
        return func
    return register


@on_message('GLOBAL_POSITION_INT')
def show_position(master, msg):
    print(f"位置: lat={msg.lat / 1e7:.7f}, lon={msg.lon / 1e7:.7f}, "
          f"高度={msg.relative_alt / 1000:.1f} m")


@on_message('HEARTBEAT')
def show_status(master, msg):
    # 地上局（Mission Planner や MAVProxy）の HEARTBEAT は無視し、機体のものだけを見る
    if msg.type == mavutil.mavlink.MAV_TYPE_GCS:
        return
    armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
    print(f"ステータス: {'ARM' if armed else 'DISARM'}, モード={master.flightmode}")


def receive_loop(master, stop_event):
    """メッセージを受信して、登録されたコールバックを呼ぶ（受信スレッドで動く）"""
    while not stop_event.is_set():
        msg = master.recv_match(blocking=True, timeout=1)
        if msg is None:
            continue
        for func in callbacks.get(msg.get_type(), []):
            try:
                func(master, msg)
            except Exception as error:
                # コールバックの失敗で、受信スレッドを止めない
                print(f"コールバックでエラー: {error}")


# 機体への接続
master: mavutil.mavfile = mavutil.mavlink_connection(
    "tcp:127.0.0.1:5762", source_system=1, source_component=90)
master.wait_heartbeat()
print("接続完了。Ctrl+C で終了します")

# GLOBAL_POSITION_INT(33)を 2Hz（500000 マイクロ秒ごと）で受信する
master.mav.command_long_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
    0, 33, 500000, 0, 0, 0, 0, 0)

# 受信スレッドを開始する（daemon=True: メインが終わればスレッドも終わる）
stop_event = threading.Event()
thread = threading.Thread(
    target=receive_loop, args=(master, stop_event), daemon=True)
thread.start()

# メインスレッドは待つだけ。Ctrl+C で止める
try:
    while True:
        time.sleep(0.5)
except KeyboardInterrupt:
    print("終了します")
finally:
    stop_event.set()
    thread.join(timeout=3)
    master.close()
