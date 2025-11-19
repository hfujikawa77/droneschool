# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------- #
#         PythonでDroneKitとMAVLinkを使用して姿勢制御コマンドを送信するデモ
# ---------------------------------------------------------------------------- #
import math
import time
from dronekit import connect
#------------- config.jsonから接続文字列を読み込むコードを追加 -------------
import json
import os # osモジュールを追加
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, '..', 'config.json')

with open(config_path) as f:
    config = json.load(f)
connection_string = config['connection_string']
# config.jsonから接続文字列を読み込み、ドローンに接続
print("Connecting to vehicle on: %s" % connection_string)
vehicle = connect(connection_string, wait_ready=True, timeout=60)
print("Connected to vehicle!")
# -----------------------------------------------------------------------------
# vehicle = connect('127.0.0.1:14551', wait_ready=True, timeout=60)
# vehicle = connect('tcp:127.0.0.1:5762', wait_ready=True, timeout=60)

def to_quaternion(roll = 0.0, pitch = 0.0, yaw = 0.0):
    """
    Euler角 (ロール, ピッチ, ヨー) をクォータニオンに変換します。
    MAVLinkのSET_ATTITUDE_TARGETメッセージで姿勢を設定する際に使用されます。
    """
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

def arm_and_takeoff(aTargetAltitude):
    """
    車両をアームし、指定された高度まで離陸させます。
    """
    print("Basic pre-arm checks")
    # is_armableになるまで待機
    while not vehicle.is_armable:
        print(" Waiting for vehicle to initialise...")
        time.sleep(1)

    print("Arming motors")
    # GUIDEDモードに設定
    vehicle.mode = 'GUIDED'
    vehicle.armed = True

    # アームされるまで待機
    while not vehicle.armed:
        print(" Waiting for arming...")
        time.sleep(1)

    print("Taking off!")
    vehicle.simple_takeoff(aTargetAltitude) # 目標高度まで離陸

    # 目標高度に到達するまで待機
    while True:
        print(" Altitude: ", vehicle.location.global_relative_frame.alt)
        # 目標高度の95%に達したらループを抜ける
        if vehicle.location.global_relative_frame.alt >= aTargetAltitude * 0.95:
            print("Reached target altitude")
            break
        time.sleep(1)




# 離陸して高度5mに到達
arm_and_takeoff(5)

try:
    # MAVLink ATTITUDE_TARGETメッセージを作成
    # このメッセージは、特定の姿勢（ロール、ピッチ、ヨー）とスラストを車両に指示するために使用されます。
    msg = vehicle.message_factory.set_attitude_target_encode(
        0,      # ブートからの時間（今回は未使用）。0でよい。
        0,0,    # ターゲットシステム、コンポーネント。通常は0,0でOK。
        0b00000000 if False else 0b00000100, # マスク。ここではヨーレートを無視し、クォータニオンを使用することを示す。
        to_quaternion(20, -20, 0),  # クオータニオン形式の目標姿勢 (ロール:20度, ピッチ:-20度, ヨー:0度)
        0,0, math.radians(0), # ロール,ピッチ,ヨーレート。今回は使用しないので0。
        0.5 # スラスト値 (0.0:最小スラスト, 1.0:最大スラスト)。機体を浮上させるために必要。
    )

    # MAVLink ATTITUDE_TARGETメッセージを繰り返し送信
    # 指定された姿勢を維持するために、メッセージを継続的に送信する必要があります。
    print("Sending attitude command for 10 seconds")
    for x in range(0, 100):
        vehicle.send_mavlink(msg)
        time.sleep(0.1)
    print("Attitude command sent")

finally:
    # --- 着陸 ---
    print("Landing...")
    vehicle.mode = 'LAND'

    # --- 接続解除 ---
    # 使用が終わったら、車両との接続を閉じます。
    vehicle.close()
    print("Connection closed.")
