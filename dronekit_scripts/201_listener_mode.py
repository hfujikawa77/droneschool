import time
from dronekit import connect, VehicleMode
import json
import os

# --- 設定ファイルの読み込み ---
# スクリプトのディレクトリから相対パスでconfig.jsonを特定する
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, '..', 'config.json')

with open(config_path) as f:
    config = json.load(f)
connection_string = config['connection_string']

# --- ドローンに接続 ---
print(f'Connecting to vehicle on: {connection_string}')
vehicle = connect(connection_string, wait_ready=True, timeout=60)
print("Vehicle connected!")

# --- モード変更を監視するコールバック関数 ---
def mode_callback(self, attr_name, value):
    # 'value' は VehicleMode オブジェクトなので、.name でモード名を取得
    print(f"--- モードが {value.name} に変更されました！ ---")

# --- リスナーの登録 ---
print("モード変更を監視するリスナーを登録中...")
vehicle.add_attribute_listener('mode', mode_callback)

# --- スクリプトを常駐させる ---
print("モード変更を監視しています (Ctrl+Cで終了)。")
while True:
    time.sleep(1)

# --- スクリプトが終了する際にリスナーを解除する（ここでは無限ループのため実質実行されない） ---
# vehicle.remove_attribute_listener('mode', mode_callback)
# vehicle.close()
