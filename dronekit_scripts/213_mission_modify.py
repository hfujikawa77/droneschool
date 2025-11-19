# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------- #
#             PythonでDroneKitを使用して既存のミッションを編集するデモ
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

# --- ミッションの編集 ---
# 編集のために、ダウンロードしたミッションをPythonのリストにコピーします。
# vehicle.commandsオブジェクトを直接編集することも可能ですが、
# 安全のため一度別のリストにコピーする方が良い場合があります。
missionList = []
for cmd in cmds:
    missionList.append(cmd)

# ミッションリストの最初のコマンドを編集
# 例として、最初のコマンドを強制的に離陸(TAKEOFF)コマンドに書き換えます。
print("Modifying mission list...")
if len(missionList) > 0:
    print("Changing first command to MAV_CMD_NAV_TAKEOFF")
    missionList[0].command = mavutil.mavlink.MAV_CMD_NAV_TAKEOFF
    missionList[0].param7 = 20 # 高度を20mに設定
else:
    print("No mission to modify.")

# --- 編集したミッションのアップロード ---
# 機体上の既存ミッションを一度クリア
print("Clearing vehicle's current mission")
cmds.clear()

# 編集したミッションリストをローカルバッファに追加
print("Adding modified commands to local buffer")
for cmd in missionList:
    cmds.add(cmd)

# 変更したミッションリストを機体にアップロード
print("Uploading modified mission to vehicle")
cmds.upload()
print("Modified mission uploaded")

# --- 接続解除 ---
vehicle.close()
print("Connection closed")
