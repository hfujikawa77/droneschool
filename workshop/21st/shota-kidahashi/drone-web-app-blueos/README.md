# ドローンWeb制御アプリケーション（BlueOS Extension）

## 概要

本アプリケーションは、既存の Pymavlink を使用した CLI ドローン制御ツールを、
Webブラウザから操作できるように拡張したものです。

Python（FastAPI）バックエンドと HTML + JavaScript（Leaflet.js）フロントエンドで構成され、
ドローンの状態表示（地図上での位置表示を含む）と各種コマンド送信をリアルタイムで行います。

BlueOS Extension として動作するように Docker 化していますが、
こちらでBLUEOSができなかったためBlueOS 環境でのテストはできていません。

---

## 機能

* ドローンへの接続 / 切断  
* モーターのアーム / ディスアーム  
* 指定高度への離陸  
* 指定座標への移動（GUIDED モード）  
* 着陸コマンドの送信  
* フライトモードの変更  
* ドローンの現在位置を地図上にリアルタイム表示（Leaflet.js）  
* 緯度・経度・高度・モード・アーム状態のリアルタイム表示  
* WebSocket による高速ステータス更新  

---

## 技術スタック

* **バックエンド**: Python (FastAPI, Uvicorn, Pymavlink, WebSockets)  
* **フロントエンド**: HTML, JavaScript (Leaflet.js), CSS  
* **コンテナ**: Docker（BlueOS Extension 形式）  

---

## 起動方法（ローカル環境）

### 1. 前提条件

* Python 3.7 以上  
* Mission Planner などの SITL シミュレーターが起動しており、  
  `tcp:127.0.0.1:5762` で接続可能であること  

### 2. バックエンドのセットアップと起動

ローカル環境では、以下のコマンドでバックエンド（FastAPI）を起動し、
**正常に接続できることを確認しました。**

```bash
cd ~/drone-web-app-blueos/backend
uvicorn main:app --host 0.0.0.0 --port 9999
