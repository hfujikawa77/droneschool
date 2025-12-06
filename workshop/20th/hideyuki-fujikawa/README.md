# 第20回ドローンスクール - hideyuki-fujikawa

## 概要
ArduPilotとMAVLinkを使用したドローン制御のワークショップ課題です。
Node.js (TypeScript) と Python の両方で MAVLink 通信を実装しています。

## ディレクトリ構成

### nm_scripts/
Node.js + node-mavlink を使用した TypeScript スクリプト

- **nm01_message_dump.ts**: MAVLink メッセージのダンプとメッセージ間隔設定
  - 192.168.3.38:5762 に TCP 接続
  - GLOBAL_POSITION_INT メッセージを 10Hz で取得
  - 受信メッセージをコンソールに出力

- **nm02_arm_disarm_compact.ts**: ARM/DISARM コマンドの実装（コンパクト版）
  - メッセージダンプ機能に ARM コマンドを追加

- **nm02_arm_disarm_full.ts**: ARM/DISARM コマンドの完全版
  - フル実装版のスクリプト

### pm_scripts/
Python + pymavlink を使用したスクリプト

- **pm_scripts.py**: GUIDED モードでの離陸制御
  - 127.0.0.1:14551 に接続
  - GUIDED モードに設定
  - ARM してから 10m まで離陸
  - 高度到達まで監視

- **pm_scripts_control.py**: モード設定と離陸の簡易版
  - モード 4 (GUIDED) に設定
  - ARM して 10m 離陸コマンド送信

### その他のファイル

- **pm_workshop.py**: Heartbeat 送信サンプル
  - 127.0.0.1:14551 に接続
  - 定期的に Heartbeat を送信

- **package.json**: Node.js プロジェクト設定
  - node-mavlink ^2.3.0 を使用

- **.gitignore**: Git 除外設定
  - node_modules, dump.log などを除外

## 実行方法

### Node.js スクリプト
```bash
npm install
npx ts-node nm_scripts/nm01_message_dump.ts
```

### Python スクリプト
```bash
python3 pm_workshop.py
python3 pm_scripts/pm_scripts.py
```

## 学習内容
- MAVLink プロトコルによるドローン通信
- ARM/DISARM コマンド
- モード切り替え (GUIDED)
- 離陸制御
- メッセージ間隔設定
- 位置情報取得
