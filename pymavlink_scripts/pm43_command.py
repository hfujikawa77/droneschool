import sys
import time
from pymavlink import mavutil

# 機体への接続
master: mavutil.mavfile = mavutil.mavlink_connection(
    device="tcp:127.0.0.1:5762", source_system=1, source_component=90)
master.wait_heartbeat()

# ヨー制御コマンドを送信する
command = mavutil.mavlink.MAV_CMD_CONDITION_YAW
master.mav.command_long_send(
    master.target_system, master.target_component,
    command,
    0,
    180,    # 角度指定（degrees）
    0,      # スピード指定（deg/s）
    1,      # 方向 -1:反時計周り, 1:時計回り
    1,      # オフセット 1:相対, 0:絶対
    0, 0, 0)

# コマンドの結果（COMMAND_ACK）を確認する（3秒待つ）
# 受理されない例: Rover / ボートでは UNSUPPORTED
ack = None
end = time.time() + 3
while ack is None and time.time() < end:
    msg = master.recv_match(type='COMMAND_ACK', blocking=True, timeout=1)
    if msg is not None and msg.command == command:
        ack = msg
accepted = (mavutil.mavlink.MAV_RESULT_ACCEPTED, mavutil.mavlink.MAV_RESULT_IN_PROGRESS)
if ack is None or ack.result not in accepted:
    result = mavutil.mavlink.enums['MAV_RESULT'][ack.result].name if ack else 'ACKなし'
    print(f"コマンドが受理されませんでした: {result}")
    sys.exit(1)
print("コマンドが受理されました")
