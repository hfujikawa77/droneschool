・アプリケーション（autopilot_demo.py）実行手順

1, MissionPlaner起動

2, MissionPlanerのSITL起動（その際ホームポイント座標を”--home 35.8791167,140.
3358445,10,0”に指定）

3, Visual Studio Codeを起動し、WSL（Ubuntu22.04）に接続

4, ターミナルでMAVProxyに接続

5, autopilot_demo.pyを実行

・機体の挙動

a) ホームポイントから10m上昇

b) 3つのWPを順に結ぶ、その際各WPで5秒待機し次のWPへ

c) 3つ目のWP到達後10秒待機しRTL(高度20m)

d) ホームポイント到達し着陸
