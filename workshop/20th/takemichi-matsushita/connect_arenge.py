from pymavlink import mavutil
import time

# ==========================
# ★ SITL（シミュレーター）の接続設定
# ==========================
# MAVProxy が中継している UDP ポート 14551 に接続
master: mavutil.mavfile = mavutil.mavlink_connection(
    "udp:127.0.0.1:14551",
    source_system=1,
    source_component=90
)

print("ハートビート待機中...")
master.wait_heartbeat()
print("接続成功!")

#ターゲットシステムID、コンポーネントIDを表示
print('target_system: {}, target_compoent: {}'
      .format(master.target_system, master.target_component))

while True:
    master.mav.heartbeat_send(
        mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
        mavutil.mavlink.MAV_AUTOPILOT_GENERIC,
        0, 0, 0
    )
    time.sleep(1)
    

print(f"target_system: {master.target_system}")
print(f"target_component: {master.target_component}")
