import time
from dronekit import connect
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
# vehicle = connect('tcp:172.30.98.2:5762', wait_ready=True, timeout=60)



while True:
    print ("====================================")
    print ("home_location: %s" % vehicle.home_location )
    print ("heading: %s" % vehicle.heading )
    print ("gimbal: %s" % vehicle.gimbal )
    print ("airspeed: %s" % vehicle.airspeed )
    print ("groundspeed: %s" % vehicle.groundspeed )
    print ("mode: %s" % vehicle.mode )
    print ("armed: %s" % vehicle.armed )
    time.sleep(1)
