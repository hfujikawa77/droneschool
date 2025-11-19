# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------- #
#         PythonでDroneKitを使用して車両のパラメータを読み書きするデモ
# ---------------------------------------------------------------------------- #
import time
from dronekit import Vehicle, connect

# vehicle = connect('127.0.0.1:14551', wait_ready=True, timeout=60)
# vehicle = connect('tcp:127.0.0.1:5762', wait_ready=True, timeout=60)
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

# --- パラメータの読み込み ---
# 'RTL_ALT' (Return to Launch Altitude) パラメータの現在の値を取得し表示します。
# この値は、RTLモード時にドローンが上昇する高度を示します。
print("変更前 RTL_ALT: %s" % vehicle.parameters['RTL_ALT'])

# --- パラメータの更新 ---
# 'RTL_ALT' パラメータの値を100に設定します。
# この変更はドローンに即座に適用されます。
vehicle.parameters['RTL_ALT'] = 10
print("変更後 RTL_ALT: %s" % vehicle.parameters['RTL_ALT'])

time.sleep(5)

# --- 全パラメータの参照 ---
# vehicle.parametersコレクションをイテレートし、すべてのパラメータのキーと値を出力します。
# これにより、車両に設定されているすべてのパラメータを確認できます。
for key, value in vehicle.parameters.items():
    print("Key:%s Value:%s" % (key, value))

# --- 接続解除 ---
# 使用が終わったら、車両との接続を閉じます。
vehicle.close()
print("Connection closed.")

