# ドローンWeb制御アプリケーション 構築＋起動用プロンプト

以下の指示に従って、ドローンをWebブラウザから操作できる最小構成のアプリケーションを新規実装し、さらに **SITL の起動 → Web アプリの起動 → 動作確認** までを一気通貫で行ってください。コードを書いて終わりではなく、ブラウザで操作できる状態まで到達することがゴールです。

## 全体の流れ

| ステップ | 内容 | 完了の目安 |
| --- | --- | --- |
| 1. ビルド（生成） | 本プロンプトの仕様どおりにアプリを実装する | 全ファイルが保存され、そのまま実行できる形になっている |
| 2. SITL 起動 | ArduPilot SITL を起動し、`tcp:127.0.0.1:5762` で待ち受けさせる | ポート 5762 への TCP 接続が受け付けられる |
| 3. Web アプリ起動 | バックエンドを起動する（ポート **9999**） | `http://127.0.0.1:9999/` が応答する |
| 4. 動作確認 | UI から機体に接続し、状態表示とコマンドを確認する | 「起動後の動作確認」の項目をすべて満たす |

- ステップ2と3は**別々のターミナル（別プロセス）で起動したままにする**こと。起動確認が終わるまで、どちらも停止しない。
- 途中で詰まった場合は「トラブルシュート」を先に確認すること。

## 事前確認（実装を始める前に必須）

実装を開始する前に、次の2点を確定すること。

- **名前**: アプリのルートフォルダ名（例: `drone-web-app`）。未指定なら、勝手に決めずユーザーに質問する。
- **パス**: 作成先フォルダ。未指定なら、このプロンプトファイルがあるフォルダとする。

最終的なルートは `<パス>/<名前>/` となる。以降の「ディレクトリ構成」はこのルート直下の構成を指す。

## あなたの役割

あなたは、Python とブラウザフロントエンドに強いシニアエンジニアです。FastAPI、WebSocket、pymavlink、HTML、JavaScript、CSS を使い、ローカルで動作するドローンWeb制御アプリケーションを構築してください。

## プロジェクトの目的

既存の CLI ベースのドローン制御体験を、Web ブラウザから操作できるように置き換えます。ユーザーはブラウザ上でドローンへ接続し、状態をリアルタイムに確認しながら、アーム、離陸、着陸、モード変更、指定座標への移動を実行できる必要があります。

## 技術制約

- バックエンドは Python + FastAPI、リアルタイム通信は WebSocket
- MAVLink 通信は `pymavlink`
- フロントエンドは素の `HTML + JavaScript + CSS`（ビルドツール不要）
- 地図表示は Leaflet + OpenStreetMap タイル
- 単一リポジトリ内に `backend` と `frontend` を分ける

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

## 機能仕様

### コマンド（Web UI から WebSocket 経由で送信）

JSON コマンドの `type` と挙動は以下。`takeoff`/`goto` は実行前に `GUIDED` への切替を試みる（最大5秒待機。`mode` は対象外）。モード変更は `set_mode()` を使い、`command_long` の `MAV_CMD_DO_SET_MODE` は ArduPilot で反映保証がないため使わない。

| `type` | 挙動 | 入力 |
| --- | --- | --- |
| `connect` | 未接続なら機体への接続を開始（サーバー起動時には自動実行せず、接続ボタン契機） | — |
| `arm` | `MAV_CMD_COMPONENT_ARM_DISARM` を `param1=1` で送信 | — |
| `disarm` | `MAV_CMD_COMPONENT_ARM_DISARM` を `param1=0` で送信 | — |
| `takeoff` | `MAV_CMD_NAV_TAKEOFF` を送信（`param7=目標高度`） | 目標高度 |
| `land` | `MAV_CMD_NAV_LAND` を送信 | — |
| `goto` | `set_position_target_global_int_send` で目標位置を送信 | 緯度・経度・高度 |
| `mode` | `set_mode()` でモード変更（選択肢 `GUIDED`/`AUTO`/`RTL`/`LOITER`/`STABILIZE`） | モード名 |

### リアルタイム状態

MAVLink を継続受信し、以下を状態オブジェクトとして保持・更新する。ステータスパネルの表示項目もこれに一致させること。初期値は接続/アーム=false、モード=`UNKNOWN`、数値=0。

| 項目 | キー | 表示形式 |
| --- | --- | --- |
| 接続状態 | `connected` | — |
| アーム状態 | `armed` | — |
| フライトモード | `mode` | — |
| 緯度 | `latitude` | 小数6桁 |
| 経度 | `longitude` | 小数6桁 |
| 高度 | `altitude` | 小数2桁 |
| ヘディング | `heading` | 整数 |

### 地図

- Leaflet で表示。初期中心は東京駅付近 `35.681236, 139.767125`
- 機体位置をマーカーで表示し、位置更新のたびに移動・地図中心を追従
- 飛行軌跡をポリラインで表示し、WebSocket 再接続時にクリア
- マーカーのポップアップに緯度・経度・高度を表示

## バックエンド要件

### ライブラリ

`backend/requirements.txt` に最低限 `fastapi` / `uvicorn` / `websockets` / `pymavlink` を含める。

### FastAPI / WebSocket の責務

- `/static` に `frontend` をマウント、`GET /` で `frontend/index.html` を返す、`WebSocket /ws` を提供
- 起動ポートは **9999**
- WebSocket 接続直後に現在の状態を JSON で即時送信
- クライアントから上表のコマンドを受信。結果は `{"type":"status","message":"..."}` で返し、テレメトリー更新時は `{"type":"state","state":{...}}` で送る（生の状態オブジェクトをそのまま送らない。フロントは `msg.type` で判定）

### MAVLink 処理

- 接続先は既定で `tcp:127.0.0.1:5762`
- `mavutil.mavlink_connection(connection_string)` で接続し、`vehicle.wait_heartbeat()` を呼ぶ
- 接続成功後に位置系データストリーム要求を送る
- `recv_match(blocking=True, timeout=0.1)` で受信し、**executor 経由でイベントループをブロックしない**（接続待ちも同様）
- `GLOBAL_POSITION_INT` → 緯度・経度・高度・ヘディング、`HEARTBEAT` → アーム状態・モードを更新。モード名は `vehicle.mode_mapping()` で逆引き
- **単位変換を必ず行う（変換漏れは典型バグ）**: 緯度経度 `msg.lat/1e7`・`msg.lon/1e7`（送信時 `int(×1e7)`）、高度 `msg.relative_alt/1000`（mm→m、無ければ `msg.alt`。送信時 `int(×1000)`）、ヘディング `msg.hdg/100`（`65535` は不明値として除外）、アーム判定 `bool(msg.base_mode & MAV_MODE_FLAG_SAFETY_ARMED)`
- **HEARTBEAT は発生源を選別する（チラつき防止）**: SITL では GCS 等の `HEARTBEAT` も届くため、`msg.type==MAV_TYPE_GCS` や `msg.autopilot==MAV_AUTOPILOT_INVALID` を除外し、本物のオートパイロットのみでアーム/モードを更新。採用した発生源（`get_srcSystem()`/`get_srcComponent()`）に `target_system`/`target_component` を合わせ、コマンド送信先もそこへ向ける
- `goto` の `set_position_target_global_int_send` は `MAV_FRAME_GLOBAL_RELATIVE_ALT_INT` と、位置のみ有効な type_mask `0b0000111111111000`（速度・加速度・yaw を無効化）を指定する

## フロントエンド要件

### UI 構成

1. **ステータスパネル** … 上表のリアルタイム状態を表示
2. **コントロールパネル** … 接続ボタン、アームボタン、ディスアームボタン、着陸ボタン、離陸高度入力＋離陸ボタン、GoTo の緯度/経度/高度入力＋ボタン、モード選択ドロップダウン＋設定ボタン
3. **地図領域**

### WebSocket クライアント

- 接続先は `ws://${window.location.host}/ws`、ページロード時に自動接続
- 切断時は 3 秒後に再接続し、再接続時に飛行軌跡をクリア
- 機体への接続は接続ボタン操作で `{"type":"connect"}` を送る（ページを開いただけでは機体に繋がない）

## デザイン要件

- シンプルでよい。2カラムのパネル配置、地図は十分な高さを確保
- スマートフォン幅では縦並びに崩れるレスポンシブ対応を入れる

## ドキュメント

- **README.md**: 概要 / 機能一覧 / 技術スタック / 前提条件（Python 3.7 以上、SITL（シミュレータ）が `tcp:127.0.0.1:5762` で待ち受け）/ 起動手順（SITL 起動 `sim_vehicle.py -v Copter --console -L Kawachi` → `backend` へ移動 → `pip install -r requirements.txt` → `uvicorn main:app --port 9999 --reload` → `http://127.0.0.1:9999/`）/ 使い方
- **REQUIREMENTS.md**: 概要 / 目的 / ターゲットユーザー / 機能要件 / 非機能要件 / 将来拡張案

## エラーハンドリング・実装ニュアンス

- 未接続時に制御コマンドを送っても致命的に落ちないこと
- WebSocket 切断時は受信タスクを安全に停止し、MAVLink 受信の例外はログを残す
- コマンド送信の成否は即断せず、状態更新はテレメトリー受信ベースで反映する（状態更新とコマンド送信は疎結合に）
- `recv_match` の無限ブロックや接続待ちで WebSocket／イベントループが停止しないこと

## SITL の準備と起動（ステップ2）

前提: ArduPilot の SITL 環境が構築済みであること（`ardupilot` のクローンと SITL 向けビルド）。未構築の場合は、先に次を行う。

```bash
cd ~/ardupilot   # クローン先は環境に合わせる
./waf configure --board sitl
./waf copter
```

起動は**アプリとは別のターミナル**で行い、起動したままにすること。

```bash
sim_vehicle.py -v Copter --console -L Kawachi
```

- この起動で MAVProxy が立ち上がり、SITL が `tcp:127.0.0.1:5762` で接続待ち受けを始める（このアプリの接続先）。
- 起動直後は待ち受けが始まるまで時間がかかる。**ポート 5762 への TCP 接続が受け付けられることを確認してから**次のステップへ進む（例: `ss -ltn | grep 5762`、または Python で `socket.create_connection(('127.0.0.1', 5762), timeout=3)` を試す）。
- `-L Kawachi` は開始位置の指定（コースで使う飛行場所）。環境に無い場所名だと起動に失敗するので、その場合は `-L` を外してよい。

## Web アプリの起動（ステップ3）

**SITL とは別のターミナル**で、生成したアプリの `backend` から起動する。

```bash
cd <パス>/<名前>/backend
pip install -r requirements.txt
MAV_ENDPOINT=tcp:127.0.0.1:5762 uvicorn main:app --port 9999
```

- 接続先の既定は `tcp:127.0.0.1:5762`。実装が環境変数 `MAV_ENDPOINT` に対応している場合は上記のように明示する（未対応の実装では無視されるので付けてよい）。
- 起動ログに `Application startup complete` が出て、`http://127.0.0.1:9999/` へ HTTP リクエストが成功することを確認する（例: `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:9999/` が `200`）。
- 起動したターミナルは開いたままにする。ユーザーにはブラウザで `http://127.0.0.1:9999/` を開くよう案内すること。

## 起動後の動作確認（ステップ4）

アプリと SITL の両方が起動した状態で、次を確認する。自動化できる項目はスクリプト等で確認し、UI 操作が必要な項目はユーザーに操作を案内して結果を確認すること。

1. ブラウザで `http://127.0.0.1:9999/` を開くと UI（ステータスパネル／コントロールパネル／地図）が表示される
2. **接続ボタン**を押すと MAVLink 接続が始まり、ステータスパネルの接続状態が「接続済み」になり、モード・位置・高度が SITL の値で更新され始める
3. 地図上のマーカーが SITL の開始位置（Kawachi 付近）に表示され、軌跡の記録が始まる
4. コマンドの疎通確認（**対象は SITL であり実機ではない**）: モードを `GUIDED` に変更 → アーム → 離陸（高度 10m 程度）→ 着陸、の順に実行し、状態表示（アーム状態・モード・高度）が追随して変わること
5. 確認が終わったら、着陸とディスアームまで済ませてから終了手順に進むこと

## 終了方法

1. Web アプリ: 起動したターミナルで `Ctrl+C`（uvicorn を停止）
2. SITL: 起動したターミナルで `Ctrl+C`（sim_vehicle / MAVProxy を停止）
3. ポート 9999 と 5762 が解放されたことを確認する

この終了手順は、生成する README.md の「起動手順」にも含めること。

## トラブルシュート

| 症状 | 確認すること |
| --- | --- |
| 接続ボタンを押しても繋がらない | SITL が起動しているか、ポート 5762 が待ち受けているか（ステップ2の確認をやり直す）。SITL の起動直後は待ち受け開始まで待つ |
| `Address already in use`（ポート 9999） | 既に uvicorn が起動していないか確認し、重複起動を止める |
| `ModuleNotFoundError`（fastapi / pymavlink 等） | `backend` で `pip install -r requirements.txt` を実行したか。仮想環境の有効化漏れにも注意 |
| ブラウザで UI が開けない | uvicorn の起動ログとポート 9999 の応答（curl）を確かめる。WSL の場合は Windows 側ブラウザから `http://localhost:9999/` で開く |
| 接続できたのに位置や高度が 0 のまま | SITL 側で GPS ロック前の可能性がある。少し待ってから再確認する。HEARTBEAT の発生源選別が効いているかも疑う |

## 受け入れ条件

1. サーバー起動後に `http://127.0.0.1:9999/` で UI が表示される
2. 接続ボタンで MAVLink 接続が始まる
3. アーム・ディスアーム・離陸・着陸・GoTo・モード変更の各コマンドを送れる
4. 状態（接続・アーム・モード・緯度・経度・高度・ヘディング）がリアルタイムに更新される
5. 地図上のマーカーと軌跡が更新される
6. モバイル幅でも UI が破綻しない
7. SITL が `tcp:127.0.0.1:5762` で待ち受け、アプリ起動後に接続ボタンで接続でき、状態がリアルタイムに更新される
8. 「起動後の動作確認」のコマンド疎通（GUIDED → アーム → 離陸 → 着陸）が SITL 上で完了する
9. 終了手順（アプリと SITL の停止）まで README に記載されている

## 出力指示

- 必要な全ファイルを、そのまま保存して実行できる形で実装すること
- 余計な抽象化は避け、理解しやすい最小構成にすること
- ただし、WebSocket 処理と MAVLink 受信処理のブロッキング問題には確実に対処すること
