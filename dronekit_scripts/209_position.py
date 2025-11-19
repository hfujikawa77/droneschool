# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------- #
#      PythonでDroneKitとMAVLinkを使用してローカル位置/速度制御コマンドを送信するデモ
# ---------------------------------------------------------------------------- #
import time
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


# --- 位置・速度制御コマンドの設定 ---
# SET_POSITION_TARGET_LOCAL_NEDメッセージを作成します。
# このメッセージは、ローカルNEDフレームでの目標位置、速度、加速度、ヨーを設定するために使用されます。
msg = vehicle.message_factory.set_position_target_local_ned_encode(
    0,      # ブートからの時間 (今回未使用なので0)
    0,0,    # ターゲットシステム、コンポーネントID (通常は0,0でOK)
    mavutil.mavlink.MAV_FRAME_LOCAL_NED,    # フレーム: ローカルNED (North-East-Down)
    # タイプマスク: どのパラメータを無視するかを指定します。
    # 0bABCDEFGHIJKLMN (各ビットがパラメータに対応)
    # 0b0000111111000111 の場合、以下のようになります。
    # - N (bit 0): X位置を無視 (1)
    # - M (bit 1): Y位置を無視 (1)
    # - L (bit 2): Z位置を無視 (1)
    # - K (bit 3): X速度を使用 (0)
    # - J (bit 4): Y速度を使用 (0)
    # - I (bit 5): Z速度を使用 (0)
    # - H (bit 6): X加速度を無視 (1)
    # - G (bit 7): Y加速度を無視 (1)
    # - F (bit 8): Z加速度を無視 (1)
    # - E (bit 9): ヨーを無視 (1)
    # - D (bit 10): ヨーレートを無視 (1)
    # 結果として、X, Y, Z速度のみが有効になります。
    0b0000111111000111, 
    0,0,0,  # x, y, z位置 (タイプマスクで無視されるため、値は無関係)
    2, -2, 1, # x, y, z速度m/s (北に2m/s, 東に-2m/s, 下に1m/s)
    0,0,0,  # x, y, z加速度 (タイプマスクで無視されるため、値は無関係)
    0,0)    # ヨー, ヨーレート (タイプマスクで無視されるため、値は無関係)

# --- コマンドの繰り返し送信 ---
# コマンドは継続的に送信しないと車両が元の状態に戻ろうとするため、
# ループ内で繰り返し送信して速度を維持します。
for x in range(0, 100):
    vehicle.send_mavlink(msg)
    time.sleep(0.1)

# --- 接続解除 ---
# 使用が終わったら、車両との接続を閉じます。
vehicle.close()
print("Connection closed.")