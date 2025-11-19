import time
from dronekit import connect, VehicleMode
import json
import os # osモジュールを追加

# 設定ファイルから接続文字列を読み込む
# スクリプトのディレクトリから相対パスでconfig.jsonを特定する
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, '..', 'config.json')

with open(config_path) as f:
    config = json.load(f)
connection_string = config['connection_string']
vehicle = connect(connection_string, wait_ready=True, timeout=60)



# arm不可能なモードもしくはセーフティロックがかかっている場合はこの処理でスタックする可能性があります
while not vehicle.is_armable:
    print("初期化中です")
    time.sleep(1)

print("アームします")
vehicle.mode = VehicleMode("GUIDED")
vehicle.armed = True

while not vehicle.armed:
    print("アームを待ってます")
    time.sleep(1)

# 離陸高度を100mに設定
targetAltitude = 100

print("離陸！")
vehicle.simple_takeoff(targetAltitude)
while True:
    print("高度:",vehicle.location.global_relative_frame.alt)

    if vehicle.location.global_relative_frame.alt >= targetAltitude * 0.95:
        print("目標高度に到達しました")
        break

    time.sleep(1)