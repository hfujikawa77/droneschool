from pymavlink import mavutil
import time

CONNECTION_STRING = 'tcp:127.0.0.1:5762'  # 環境に合わせて変更
TARGET_ALTITUDE   = 20.0   # 目標高度 [m]  (相対高度)
YAW_RATE_DEG      = 72.0   # Yaw 回転速度 [deg/s]  (360° / 5秒 = 72 deg/s)
LOOP_INTERVAL     = 0.1    # メインループ間隔 [s]
TIMEOUT           = 120    # 離陸後のプログラムタイムアウト時間 [s]

total_yaw_rotated = 0.0   # 累積回転量 [deg]
yaw_complete      = False # 回転完了
take_complete     = False # 離陸完了＆目標高度到達
prev_yaw          = None  # 過去の回転コマンド送信後のYAWの値
start_time        = time.time() # 現在時刻
yaw_cntrl_delta   = 360/(TARGET_ALTITUDE - 3)  #  高さ当たりの回転角度

# 接続
master: mavutil.mavfile = mavutil.mavlink_connection(
    "tcp:127.0.0.1:5762",  source_system=1, source_component=90)
master.wait_heartbeat()
print("接続完了")

# GUIDEDにモード変更
mode = 'GUIDED'
master.set_mode_apm(master.mode_mapping()[mode])

# モード変更を確認
while True:
    if master.flightmode == mode:
        break
    master.recv_msg()
print("モード変更完了")

# アーム
master.arducopter_arm()
master.motors_armed_wait()
print("アーム完了")

# 離陸
master.mav.command_long_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
    0, 0, 0, 0, 0, 0, 0, TARGET_ALTITUDE)
print("TAKE OFF")

# メッセージレート変更: GLOBAL_POSITION_INT(33)を10Hzで受信
master.mav.command_long_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
    0, 33, 100000, 0, 0, 0, 0, 0)

# 目標高度への到達を確認
while True:
    elapsed = time.time() - start_time
    # GLOBAL_POSITION_INT から相対高度を取得
    recieved_msg = master.recv_match(
        type='GLOBAL_POSITION_INT', blocking=True)
    current_altitude = recieved_msg.relative_alt / 1000
    current_yaw = recieved_msg.hdg / 100
    print("高度: {}".format(current_altitude) + ", Yaw: {}".format(current_yaw))

    # タイムアウト判定
    if elapsed >= TIMEOUT:
        print("[WARN] タイムアウト: 上昇フェーズを終了します")
        break
    if (current_altitude >= TARGET_ALTITUDE * 0.95) :
        if not take_complete:
            print("目標高度に到達")
            take_complete = True
        if yaw_complete: #目標高度到達＆回転完了で終了
            break

    # Yaw 1回転完了の判定 (360° 以上回ったか)
    if prev_yaw is not None and not yaw_complete:
        delta = (current_yaw - prev_yaw) % 360
        if delta > 180:
            delta -= 360 #hdgが359.99degを超えた場合、360引いて0からの角度に元に戻す

        total_yaw_rotated += delta  # 正 or 負
        if abs(total_yaw_rotated) >= 359.0:  
            yaw_complete = True
            print(f"[INFO] Yaw 1回転完了! (累積={total_yaw_rotated:.1f}deg)")
    
    if (not yaw_complete) and (current_altitude > 3):
        if take_complete:
            yaw_cntrl = 1  #目標高度に到達したら、1度に変更
        else:
            #目標高度に到達前であれば、上昇分の回転角度を計算
            yaw_cntrl = yaw_cntrl_delta * (current_altitude - prev_altitude)

        msg = master.mav.command_long_encode(
            0, 1,   # ターゲットシステム、コンポーネント
            mavutil.mavlink.MAV_CMD_CONDITION_YAW,  # コマンド
            0,
            yaw_cntrl,    # 角度指定（degrees）
            YAW_RATE_DEG,      # スピード指定（deg/s）
            1,      # 方向 -1:反時計周り, 1:時計回り
            1,      # オフセット 1:相対, 0:絶対
            0, 0, 0)
        master.mav.send(msg)

    prev_yaw = current_yaw
    prev_altitude = current_altitude
    time.sleep(LOOP_INTERVAL)

# 切断
master.close()
print("プログラム終了")