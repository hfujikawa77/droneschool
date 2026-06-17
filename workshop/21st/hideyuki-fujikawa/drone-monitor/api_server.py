import os
import time
import threading
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.openapi.docs import get_swagger_ui_html
from pymavlink import mavutil

# 既定の /docs は openapi_url を絶対パス /openapi.json で埋め込むため、
# BlueOS のリバースプロキシ配下（/extensionv2/<name>/）ではホスト直下を指して 404 になる。
# 下の custom_swagger_ui で openapi.json を相対参照にして差し替える。
#
# さらに Swagger の「Try it out」は OpenAPI の servers を基にリクエスト先を組み立てるが、
# BlueOS の nginx はサブパス（/extensionv2/<name>）をアプリに伝えない。
# root_path を与えると openapi.json に servers が入り、正しいサブパスへ送信される（405 回避）。
# BlueOS では ROOT_PATH=/extensionv2/dronemonitor を環境変数で渡す（Dockerfile の ENV）。
# ローカルでは未指定（空）でホスト直下のまま動く。
ROOT_PATH = os.environ.get("ROOT_PATH", "")
app = FastAPI(title="Drone API", root_path=ROOT_PATH, docs_url=None, redoc_url=None)


@app.get("/docs", include_in_schema=False)
def custom_swagger_ui():
    # openapi_url を相対パスにすることで、サブパス配下でもローカルでも正しく解決される
    return get_swagger_ui_html(openapi_url="openapi.json", title="Drone API - Swagger UI")

# MAVLink 接続先は環境変数で切り替える（未指定なら BlueOS Extension 用の既定値）。
#   WSL でローカルテスト : MAV_ENDPOINT=tcp:127.0.0.1:5762
#   BlueOS Extension(bridge): host.docker.internal 経由（既定）
MAV_ENDPOINT = os.environ.get("MAV_ENDPOINT", "udpout:host.docker.internal:14550")

master = None
MODE_MAP = {}


def _recv_autopilot_heartbeat(m, timeout=30):
    """autopilot（非GCS）からの HEARTBEAT を返す。

    MAVLink Router 経由では Mission Planner などの GCS の HEARTBEAT も流れてくる。
    target 未確定時は autopilot のみ採用し、確定後は target 一致のものだけ返す。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if hb is None:
            continue
        # GCS / 非autopilot コンポーネント（MAVLink2REST 等）を除外
        if hb.autopilot == mavutil.mavlink.MAV_AUTOPILOT_INVALID:
            continue
        if m.target_system and hb.get_srcSystem() != m.target_system:
            continue
        return hb
    return None


def _connect():
    global master, MODE_MAP
    # bridge では BlueOS-core のネットワークを共有しないため localhost は使えない。
    # 既定は host.docker.internal 経由（ExtraHosts で host-gateway に解決）。
    # bind すると競合するため client（udpout）で接続する。
    m = mavutil.mavlink_connection(MAV_ENDPOINT)
    # UDP Server はクライアントから最初のパケットを受け取るまで送ってこないため、
    # 先に heartbeat を送って自分のアドレスを登録させる。
    m.mav.heartbeat_send(
        mavutil.mavlink.MAV_TYPE_GCS,
        mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0
    )
    # Router 経由では GCS の HEARTBEAT も混ざるため、autopilot の HEARTBEAT を特定して
    # target を固定する（wait_heartbeat() だと GCS にロックオンしうる）。
    hb = _recv_autopilot_heartbeat(m)
    if hb is None:
        raise RuntimeError("autopilot heartbeat not received")
    m.target_system = hb.get_srcSystem()
    m.target_component = hb.get_srcComponent()
    # 機体タイプから明示的にモードマップを作る。
    # m.mode_mapping() は「直近に受信した HEARTBEAT」の機体タイプを見るため、
    # Router 経由だと GCS や別機体の HEARTBEAT を拾って誤ったマップ（例: Plane）を返す。
    MODE_MAP = mavutil.mode_mapping_byname(hb.type)
    # 直接 SITL(TCP) 接続ではテレメトリが自動送出されないため、ストリーム要求を送る。
    # （MAVLink Router 経由では無害。両環境で /status を動かすために常時送る）
    m.mav.request_data_stream_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1
    )
    master = m

threading.Thread(target=_connect, daemon=True).start()

def _master():
    if master is None:
        raise HTTPException(status_code=503, detail="MAVLink not connected")
    return master

# BlueOS の Helper は GET / が 200 を返すサービスのみ「有効」と判定し、
# その後 /register_service を呼んで左メニューに登録する。
# / が 404 だとメニューに表示されないため、最小のトップページを返す。
@app.get("/", response_class=HTMLResponse)
def index():
    return """<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8"><title>Drone Monitor</title></head>
<body><h2>Drone Monitor</h2><p>API ドキュメント: <a href="docs">/docs</a></p></body></html>"""

@app.get("/register_service")
def register_service():
    return {
        "name": "Drone Monitor",
        "description": "ドローン状態監視・制御パネル",
        "icon": "mdi-drone",
        "company": "",
        "version": "1.0.0",
        "webpage": "",
        "api": "/docs",
        "new_page": False,
        "works_in_relative_paths": True,
    }

@app.get("/status")
def get_status():
    m = _master()
    msg = m.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=3)
    if msg:
        return {"alt": msg.relative_alt / 1000, "lat": msg.lat / 1e7, "lon": msg.lon / 1e7}
    return {"error": "timeout"}

@app.post("/arm")
def arm():
    m = _master()
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0
    )
    return {"result": "arm command sent"}

@app.post("/disarm")
def disarm():
    m = _master()
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 0, 0, 0, 0, 0, 0, 0
    )
    return {"result": "disarm command sent"}

@app.post("/takeoff/{altitude}")
def takeoff(altitude: float):
    m = _master()

    # 現在のモードを確認し、GUIDED でなければ GUIDED に切り替える
    # （autopilot 限定で HEARTBEAT を取得。GCS の HEARTBEAT だとモード判定を誤る）
    hb = _recv_autopilot_heartbeat(m, timeout=3)
    current_mode = mavutil.mode_string_v10(hb) if hb else None

    if current_mode != "GUIDED":
        m.mav.set_mode_send(
            m.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            MODE_MAP["GUIDED"],
        )
        # GUIDED へ切り替わるのを HEARTBEAT で確認する（最大 3 秒）
        deadline = time.time() + 3
        while time.time() < deadline:
            hb = _recv_autopilot_heartbeat(m, timeout=1)
            if hb and mavutil.mode_string_v10(hb) == "GUIDED":
                current_mode = "GUIDED"
                break
        if current_mode != "GUIDED":
            raise HTTPException(status_code=409, detail="failed to switch to GUIDED")

    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, altitude
    )
    return {"result": f"takeoff command sent (alt={altitude}m)"}

@app.post("/land")
def land():
    m = _master()
    m.mav.set_mode_send(
        m.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        MODE_MAP["LAND"]
    )
    return {"result": "land command sent"}
