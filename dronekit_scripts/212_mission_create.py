# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------- #
#             PythonでDroneKitを使用して新しいミッションを作成するデモ
# ---------------------------------------------------------------------------- #
from dronekit import Command, connect
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
# vehicle = connect('127.0.0.1:14551', wait_ready=True, timeout=60)
# vehicle = connect('tcp:127.0.0.1:5762', wait_ready=True, timeout=60)

# --- ミッションコマンドの操作 ---
# vehicle.commandsオブジェクトを取得
print("Get vehicle commands")
cmds = vehicle.commands

# ドローンから既存のミッションをダウンロード
print("Downloading missions from vehicle")
cmds.download()
cmds.wait_ready()
print("Missions downloaded")

# 新しいミッションを作成するために、一度ローカルのコマンドリストをクリア
print("Clearing local mission buffer")
cmds.clear()

# --- 新しいコマンドの作成 ---
# Commandオブジェクトを使用して、MAVLinkコマンドを作成します。
# ここでは、離陸(TAKEOFF)コマンドを作成しています。
print("Creating new takeoff command")
cmd = Command(
    0, 0, 0,  # target_system, target_component, seq: これらは通常0で、DroneKitが自動で設定します。
    mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, # 座標フレーム: 地上からの相対高度
    mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, # コマンドID: NAV_TAKEOFF
    0, 0, # current, autocontinue: 通常は0でOK
    0, 0, 0, 0, # params 1-4: 離陸コマンドでは未使用
    0, 0, # latitude, longitude: 離陸コマンドでは未使用
    10      # altitude: 目標高度 (メートル)
)

# 作成したコマンドをローカルのコマンドリストに追加
print("Adding new command to mission list")
cmds.add(cmd)

# 新しいミッション（コマンドリスト）を機体にアップロード
print("Uploading new mission to vehicle")
cmds.upload()
print("New mission uploaded")

# --- 接続解除 ---
vehicle.close()
print("Connection closed")
