from dronekit import Vehicle, connect
import json
import os # osモジュールを追加

# --- 設定ファイルの読み込み ---
# スクリプトのディレクトリから相対パスでconfig.jsonを特定する
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, '..', 'config.json')

with open(config_path) as f:
    config = json.load(f)
connection_string = config['connection_string']
vehicle = connect(connection_string, wait_ready=True, timeout=60)

# --- ドローンに接続 ---
# vehicle = connect('tcp:127.0.0.1:5762', wait_ready=True, timeout=60)
# vehicle = connect('tcp:127.0.0.1:5762', wait_ready=True, timeout=60)

# vehicle.home_locationに値が設定されるまで
# downloadを繰り返し実行する
while not vehicle.home_location:
    cmds = vehicle.commands
    cmds.download()
    cmds.wait_ready()

    if not vehicle.home_location:
        print("ホームロケーションを待っています…")

# ホームロケーションの取得完了
print("ホームロケーション: %s" % vehicle.home_location)
