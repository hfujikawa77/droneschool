# ドローン Web 制御アプリケーション

ブラウザからドローン（SITL / 実機）へ接続し、状態をリアルタイムに確認しながら
アーム・離陸・着陸・モード変更・指定座標への移動を実行できる最小構成の
Web アプリケーションです。

## 機能一覧

- 機体への接続（接続ボタン契機。サーバー起動時には自動接続しない）
- アーム / ディスアーム
- 離陸（目標高度指定）/ 着陸
- GoTo（緯度・経度・高度を指定して移動）
- フライトモード変更（`GUIDED` / `AUTO` / `RTL` / `LOITER` / `STABILIZE`）
- リアルタイム状態表示（接続・アーム・モード・緯度・経度・高度・ヘディング）
- 地図表示（Leaflet + OpenStreetMap）
  - 機体位置マーカー、地図中心の追従、飛行軌跡ポリライン
  - マーカーのポップアップに緯度・経度・高度を表示

## 技術スタック

- **バックエンド**: Python + FastAPI + WebSocket
- **MAVLink 通信**: pymavlink
- **フロントエンド**: 素の HTML + JavaScript + CSS（ビルドツール不要）
- **地図**: Leaflet + OpenStreetMap タイル

## 前提条件

- Python 3.7 以上
- SITL（シミュレータ）が `tcp:127.0.0.1:5762` で待ち受けていること
  - 実機・別ポートに接続する場合は `backend/main.py` の `CONNECTION_STRING` を変更

## 起動手順

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --port 9999 --reload
```

ブラウザで <http://127.0.0.1:9999/> を開きます。

## 使い方

1. ページを開くと自動でサーバー（WebSocket）に接続します。
2. **接続** ボタンを押すと機体（MAVLink）への接続を開始します。
   - 接続が確立すると、ステータスと地図がリアルタイムに更新されます。
3. **アーム** → **離陸**（目標高度を入力）で離陸します。
   - `離陸` / `GoTo` は実行前に自動で `GUIDED` への切替を試みます（最大 5 秒待機）。
4. **GoTo** に緯度・経度・高度を入力して移動を指示できます。
5. **モード設定** でフライトモードを変更できます。
6. **着陸** で着陸します。

## ディレクトリ構成

```text
drone-web-app/
  README.md
  REQUIREMENTS.md
  backend/
    main.py
    requirements.txt
  frontend/
    index.html
    script.js
    style.css
```

## 補足（実装上の注意点）

- MAVLink の受信（`recv_match`）はブロッキングするため、必ず executor 上で
  実行し、asyncio イベントループ／WebSocket を停止させません。
- 状態更新はテレメトリー受信ベースで反映し、コマンド送信とは疎結合です。
- SITL では GCS 等の HEARTBEAT も届くため、`MAV_TYPE_GCS` や
  `MAV_AUTOPILOT_INVALID` を除外し、本物のオートパイロットのみで
  アーム状態・モードを更新します（チラつき防止）。
