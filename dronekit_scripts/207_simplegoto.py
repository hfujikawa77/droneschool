# このコードは離陸した後で実行してください。
from dronekit import LocationGlobalRelative, VehicleMode, connect
# vehicle = connect('127.0.0.1:14551', wait_ready=True, timeout=60)
# vehicle = connect('tcp:127.0.0.1:5762', wait_ready=True, timeout=60)

#------------- config.jsonから接続文字列を読み込むコードを追加 -------------
import json
import os # osモジュールを追加
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, '..', 'config.json')

with open(config_path) as f:
    config = json.load(f)
connection_string = config['connection_string']
vehicle = connect(connection_string, wait_ready=True, timeout=60)
# -----------------------------------------------------------------------------

# モードはGUIDED
vehicle.mode = VehicleMode("GUIDED")

# 目標の緯度・経度、高度を設定する
# https://maps.gsi.go.jp/#8/-35.3574950/149.1701826/&base=std&ls=std&disp=1&vs=c1j0h0k0l0u0t0z0r0s0m0f1
aLocation = LocationGlobalRelative(-35.3574950, 149.1701826, 20)

# simple_gotoを実行する
vehicle.simple_goto(aLocation, groundspeed=1000, airspeed=1000)

# 接続を閉じる
# vehicle.close()