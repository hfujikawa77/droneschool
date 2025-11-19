# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------- #
#           PythonでDroneKitを使用して基本的なミッション操作を行うデモ
# ---------------------------------------------------------------------------- #
from dronekit import connect
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
# これを通じて、ドローンに保存されているミッション（コマンドシーケンス）にアクセスできます。
print("Get vehicle commands")
cmds = vehicle.commands


# ドローンからミッションをダウンロード
# これにより、機体に保存されている既存のミッションがcmdsオブジェクトに読み込まれます。
print("Downloading missions from vehicle")
cmds.download()
# ダウンロードが完了するまで待機
cmds.wait_ready()
print("Missions downloaded")

# cmdsオブジェクト内のミッションをクリア
# これだけでは機体のミッションはクリアされません。
print("Clearing missions in local buffer")
cmds.clear()

# クリアした状態（空のミッションリスト）を機体にアップロード
# これにより、機体上のすべてのミッションが削除されます。
print("Uploading cleared mission to vehicle")
cmds.upload()
print("Missions cleared on vehicle")

# --- 接続解除 ---
vehicle.close()
print("Connection closed")
