from dronekit import connect

# vehicle = connect('127.0.0.1:14551', wait_ready=True, timeout=60)
vehicle = connect('tcp:192.168.3.210:5762', wait_ready=True, timeout=60)

# コマンドオブジェクトの取得
cmds = vehicle.commands

# ダウンロード実行
cmds.download()
cmds.wait_ready()

# クリア&アップロード
cmds.clear()
cmds.upload()
