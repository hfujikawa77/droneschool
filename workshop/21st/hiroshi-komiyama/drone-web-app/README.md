# Drone Web Controller

FastAPI + WebSocket + pymavlink を使った、ブラウザからドローンを操作する最小構成アプリです。

## 機能
- Connect / Arm / Disarm
- Takeoff / Land
- GoTo
- Mode change
- Forward / Back / Left / Right relative movement
- Real-time status panel
- Leaflet map with marker and flight track

## 前提条件
- Python 3.7+
- SITL or a real MAVLink vehicle listening at tcp:127.0.0.1:5762

## 起動手順
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 9999 --reload
```

Then open:
```text
http://127.0.0.1:9999/
```

## 使い方
- Connect ボタンで MAVLink 接続を開始します。
- Arm / Takeoff / Land / GoTo / Mode で制御できます。
- Forward / Back / Left / Right は押下中のみ移動し、離すと停止します。
