# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------- #
#      PythonでDroneKitを使用してMAV_CMD_CONDITION_YAWコマンドを送信するデモ
# ---------------------------------------------------------------------------- #
import time # timeモジュールを追加
from dronekit import connect
from pymavlink import mavutil
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
# 注：上記はconfig.jsonから接続文字列を読み込む方法です。
# 以下のように直接接続文字列を指定することも可能です（コメントアウトされています）。
# vehicle = connect('127.0.0.1:14551', wait_ready=True, timeout=60) # SITL/Gazeboなどローカルシミュレータ用
# vehicle = connect('tcp:127.0.0.1:5762', wait_ready=True, timeout=60) # UDP/TCP経由での接続用


# --- ヨー制御コマンドの送信 ---
# MAV_CMD_CONDITION_YAW を使用して機体のヨー(旋回)を制御します。
# command_long_encodeは、汎用的なMAVLinkコマンドをエンコードするために使用されます。
msg = vehicle.message_factory.command_long_encode(
    0, 1,    # ターゲットシステム、コンポーネントID (通常は0,1でOK)
    mavutil.mavlink.MAV_CMD_CONDITION_YAW,  # コマンドID: ヨー(旋回)を制御するコマンド
    0,       # confirmation: 確認応答 (通常0)
    180,    # param 1: ヨー角度 (度数)。北を0度として時計回りに0-359度。ここでは180度(南)に設定。
    0,      # param 2: 旋回速度 (度/秒)。0の場合、最大速度で旋回。
    1,      # param 3: 方向 -1:反時計回り, 1:時計回り。ここでは時計回り。
    1,      # param 4: オフセット 1:相対角度, 0:絶対角度。ここでは現在の機首方向からの相対角度。
    0, 0, 0) # param 5 ~ 7: 未使用

# MAVLinkメッセージ送信
vehicle.send_mavlink(msg)
print("Yaw command sent. Waiting for 5 seconds...")
time.sleep(5)
print("Yaw command execution finished.")

# --- 接続解除 ---
# 使用が終わったら、車両との接続を閉じます。
vehicle.close()
print("Connection closed.")
