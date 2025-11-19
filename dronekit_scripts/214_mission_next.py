# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------- #
#         PythonでDroneKitを使用して次に実行されるミッションを取得するデモ
# ---------------------------------------------------------------------------- #
import time
from dronekit import  connect
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

# --- 次のミッションコマンドの監視 ---
# vehicle.commands.nextは、AUTOモードで次に実行されるミッションコマンドのインデックス番号を返します。
# この値は、ドローンがミッションを遂行中に更新されます。
print("Press Enter to display the next mission item. Type 'q' to quit.")

while True:
    try:
        user_input = input() # ユーザーからの入力を待つ
        if user_input.lower() == 'q':
            print("Quitting monitor.")
            break
        # vehicle.commands.next は次に実行されるミッションのインデックス
        # vehicle.commands[index] でそのコマンドの詳細を取得できる
        next_mission_index = vehicle.commands.next
        if next_mission_index < len(vehicle.commands):
            next_cmd = vehicle.commands[next_mission_index]
            print(f"Next mission item index: {next_mission_index}")
            print(f"  -> Command: {next_cmd.command} (see MAV_CMD enum)")
            print(f"  -> Params: p1={next_cmd.param1}, p2={next_cmd.param2}, p3={next_cmd.param3}, p4={next_cmd.param4}")
            print(f"  -> Location: lat={next_cmd.x}, lon={next_cmd.y}, alt={next_cmd.z}")
        else:
            print(f"Next mission item index: {next_mission_index} (end of mission)")
    except Exception as e:
        print(f"An error occurred: {e}")
        break

# --- 接続解除 ---
vehicle.close()
print("Connection closed.")