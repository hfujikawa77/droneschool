import time
from dronekit import connect, TimeoutError
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

# vehicle = connect('127.0.0.1:14551', wait_ready=True, timeout=60)
# vehicle = connect('tcp:127.0.0.1:5762', wait_ready=True, timeout=60)

try:
    vehicle.wait_for_mode("GUIDED")
    vehicle.wait_for_armable()
    vehicle.arm()
    time.sleep(1)
    vehicle.wait_simple_takeoff(20, timeout=60)
    # vehicle.wait_simple_takeoff(20,0.5,15)
    print("Takeoff is successful!")

except TimeoutError as takeoffError:
    print("Takeoff is timeout!!!")
    # フェールセーフコード

