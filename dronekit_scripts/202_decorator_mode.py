from dronekit import Vehicle, connect
import time
import json
import os # osモジュールを追加

# --- 設定ファイルの読み込み ---
# スクリプトのディレクトリから相対パスでconfig.jsonを特定する
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, '..', 'config.json')

with open(config_path) as f:
    config = json.load(f)
connection_string = config['connection_string']

# --- ドローンに接続 ---
# 指定された接続文字列を使用してドローンに接続します。
# wait_ready=True は、車両からの初期パラメータと属性のダウンロードが完了するまで待機します。
vehicle = connect(connection_string, wait_ready=True, timeout=60)

# --- デコレータを使用したリスナーの登録 ---
# @vehicle.on_attribute('属性名') デコレータを使用すると、
# その直下の関数を、指定された属性の変更を監視するコールバックとして自動的に登録できます。
# これは vehicle.add_attribute_listener() と同じ機能を提供しますが、より簡潔に記述できます。

@vehicle.on_attribute('mode')
def location_callback(self, attr_name, value):
    # 'mode' の値が更新されるたびにこの関数が呼び出されます。
    # ここでは、新しいモード名を表示しています。
    # 'value' は VehicleMode オブジェクトなので、.name でモード名を取得
    print(f"--- モードが {value.name} に変更されました！ ---")

# --- スクリプトの実行維持とリスナーの動作確認 ---
# リスナーがバックグラウンドで動作し続けるために、スクリプトのメインスレッドを一定時間維持します。
time.sleep(60)

# --- 終了 ---
# このスクリプトではデコレータで登録されたリスナーを明示的に解除するコードがありません。
# スクリプト自体が終了するとリスナーも停止します。
# 実行を停止するには、Ctrl+C を押してプロセスを終了させる必要があります。
# （add_attribute_listener の場合は remove_attribute_listener で解除可能でした）