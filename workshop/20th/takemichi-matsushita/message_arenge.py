from pymavlink import mavutil
import time

# =============================
# ★ MAVProxy が中継している UDP に接続
# =============================
master = mavutil.mavlink_connection(
    "udp:127.0.0.1:14551",   # MAVProxy が中継している UDP ポート
    source_system=1,
    source_component=90
)

print("ハートビート待機中...")
master.wait_heartbeat()
print("接続成功！")


# =============================
# ★ メッセージ受信（受け取り）
# =============================
print("HEARTBEAT を受信します...")
received_msg = master.recv_match(type="HEARTBEAT", blocking=True)
print("受信したメッセージ：")
print(received_msg)


# =============================
# ★ メッセージ直接送信
# =============================
print("\nHEARTBEAT を直接送信します...")
master.mav.heartbeat_send(
    mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,   # type
    mavutil.mavlink.MAV_AUTOPILOT_GENERIC,         # autopilot
    0,                                             # base_mode
    0,                                             # custom_mode
    mavutil.mavlink.MAV_STATE_ACTIVE               # system_status
)

print("送信完了！")


# =============================
# ★ メッセージ作成 → 送信
# =============================
print("\nHEARTBEAT メッセージを作成して送信します...")
to_send_msg = master.mav.heartbeat_encode(
    mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
    mavutil.mavlink.MAV_AUTOPILOT_GENERIC,
    0,
    0,
    mavutil.mavlink.MAV_STATE_ACTIVE
)
print("作成したメッセージ：")
print(to_send_msg)

# 実際に送信
master.mav.send(to_send_msg)
print("送信完了！")
