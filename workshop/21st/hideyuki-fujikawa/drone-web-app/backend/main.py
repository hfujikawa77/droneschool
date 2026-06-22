"""ドローンWeb制御アプリケーション バックエンド.

FastAPI + WebSocket + pymavlink で、ブラウザからドローン(SITL/実機)を
操作するための最小構成サーバー。

ポイント:
- MAVLink の受信(`recv_match`)はブロッキングするため、必ず executor 上で
  実行し、asyncio イベントループ／WebSocket を止めない。
- 状態更新はテレメトリー受信ベースで行い、コマンド送信とは疎結合にする。
"""

import asyncio
import json
import logging
import os
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pymavlink import mavutil

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("drone-web-app")

# ---- 設定 -----------------------------------------------------------------
# 接続先。BlueOS では bridge から Router へ host.docker.internal 経由(udpout)で繋ぐ。
# ローカル SITL 確認時は MAV_ENDPOINT=tcp:127.0.0.1:5762 で上書きする運用。
CONNECTION_STRING = os.environ.get(
    "MAV_ENDPOINT", "udpout:host.docker.internal:14550"
)
PORT = 9999

# 本物のオートパイロット HEARTBEAT を待つ最大時間（GCS の HEARTBEAT は除外）
HEARTBEAT_WAIT_SECONDS = 30

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")

# GUIDED への切替を待つ最大時間（takeoff/goto の前処理）
GUIDED_WAIT_SECONDS = 5.0


# ---- WebSocket 接続管理 ----------------------------------------------------
class ConnectionManager:
    """接続中の全クライアントへ状態をブロードキャストする."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict):
        dead = []
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


# ---- ドローン制御本体 ------------------------------------------------------
class Drone:
    def __init__(self, manager: ConnectionManager):
        self.manager = manager
        self.vehicle = None
        # コマンド送信先（本物のオートパイロットを採用後に上書き）
        self.target_system = 1
        self.target_component = 1
        # 機体タイプから明示生成するモードマップ（name -> id）
        self.mode_map: dict[str, int] = {}
        self._connecting = False
        self._recv_task: asyncio.Task | None = None
        self.state = {
            "connected": False,
            "armed": False,
            "mode": "UNKNOWN",
            "latitude": 0.0,
            "longitude": 0.0,
            "altitude": 0.0,
            "heading": 0,
        }

    @property
    def connected(self) -> bool:
        return self.vehicle is not None and self.state["connected"]

    # -- 接続 ---------------------------------------------------------------
    async def connect(self) -> str:
        if self.connected:
            return "すでに接続済みです"
        if self._connecting:
            return "接続処理中です"

        self._connecting = True
        loop = asyncio.get_running_loop()
        try:
            # 接続待ちもブロッキングするため executor で実行
            self.vehicle = await loop.run_in_executor(None, self._connect_blocking)
        except Exception as e:
            logger.exception("MAVLink 接続に失敗しました")
            self.vehicle = None
            return f"接続失敗: {e}"
        finally:
            self._connecting = False

        self.state["connected"] = True
        self._recv_task = asyncio.create_task(self._recv_loop())
        await self._broadcast_state()
        return f"{CONNECTION_STRING} に接続しました"

    def _connect_blocking(self):
        """ブロッキングする接続処理（executor 上で実行）.

        BlueOS の Router 経由では GCS(MAVProxy 等) の HEARTBEAT も混ざるため、
        本物のオートパイロット(autopilot != INVALID)を特定して送信先に採用する。
        """
        vehicle = mavutil.mavlink_connection(CONNECTION_STRING)
        # udpout(client) の場合、こちらの存在を Router に知らせるため GCS HB を送る
        vehicle.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_GCS,
            mavutil.mavlink.MAV_AUTOPILOT_INVALID,
            0, 0, 0,
        )

        hb = None
        deadline = time.time() + HEARTBEAT_WAIT_SECONDS
        while time.time() < deadline:
            msg = vehicle.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
            if msg and msg.autopilot != mavutil.mavlink.MAV_AUTOPILOT_INVALID:
                hb = msg
                break
        if hb is None:
            vehicle.close()
            raise TimeoutError("オートパイロットの HEARTBEAT を受信できませんでした")

        # 送信先を本物のオートパイロットに固定
        self.target_system = hb.get_srcSystem()
        self.target_component = hb.get_srcComponent()
        vehicle.target_system = self.target_system
        vehicle.target_component = self.target_component
        # 機体タイプから明示生成（mode_mapping() は直近 HEARTBEAT 依存で誤判定しうる）
        self.mode_map = mavutil.mode_mapping_byname(hb.type) or {}
        self._request_data_streams(vehicle)
        return vehicle

    def _request_data_streams(self, vehicle):
        """位置系・ステータス系を含む全データストリームを要求する."""
        vehicle.mav.request_data_stream_send(
            self.target_system,
            self.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL,
            4,
            1,
        )

    # -- 受信ループ ---------------------------------------------------------
    async def _recv_loop(self):
        loop = asyncio.get_running_loop()
        while self.connected:
            try:
                msg = await loop.run_in_executor(None, self._recv_one)
            except Exception:
                logger.exception("MAVLink 受信中に例外が発生しました")
                await asyncio.sleep(0.5)
                continue

            if msg is None:
                await asyncio.sleep(0)  # 他タスクへ譲る
                continue

            if self._handle_message(msg):
                await self._broadcast_state()

    def _recv_one(self):
        """1メッセージ受信（ブロッキング, executor 上で実行）."""
        return self.vehicle.recv_match(blocking=True, timeout=0.1)

    def _handle_message(self, msg) -> bool:
        """状態を更新し、変化があれば True を返す.

        Router 経由では GCS(MAVProxy 等) の HEARTBEAT も届く。自機
        (target_system/target_component) 以外のメッセージは無視し、
        mode/armed の点滅を防ぐ。
        """
        if (
            msg.get_srcSystem() != self.target_system
            or msg.get_srcComponent() != self.target_component
        ):
            return False

        mtype = msg.get_type()

        if mtype == "GLOBAL_POSITION_INT":
            self.state["latitude"] = msg.lat / 1e7
            self.state["longitude"] = msg.lon / 1e7
            relative_alt = getattr(msg, "relative_alt", None)
            raw_alt = relative_alt if relative_alt is not None else msg.alt
            self.state["altitude"] = raw_alt / 1000.0  # mm -> m
            if msg.hdg != 65535:  # 65535 は不明値
                self.state["heading"] = int(msg.hdg / 100)
            return True

        if mtype == "HEARTBEAT":
            # ARM は system_status ではなく SAFETY_ARMED ビットで判定する
            armed = bool(
                msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
            )
            mode = self._mode_name(msg.custom_mode)
            changed = armed != self.state["armed"] or mode != self.state["mode"]
            self.state["armed"] = armed
            self.state["mode"] = mode
            return changed

        return False

    def _mode_name(self, custom_mode) -> str:
        """custom_mode をモード名に逆引きする（機体タイプ別の明示マップ）."""
        for name, mode_id in self.mode_map.items():
            if mode_id == custom_mode:
                return name
        return "UNKNOWN"

    async def _broadcast_state(self):
        await self.manager.broadcast({"type": "state", "state": dict(self.state)})

    def _send_mode(self, mode_name: str) -> bool:
        """機体タイプ別マップで解決した mode_id でモード変更を送る."""
        mode_id = self.mode_map.get(mode_name)
        if mode_id is None:
            logger.warning("未知のモード: %s（mode_map=%s）", mode_name, self.mode_map)
            return False
        # MAV_CMD_DO_SET_MODE は ArduPilot で反映保証がないため set_mode() を使う。
        # mode_id(数値)を渡して機体タイプ別の正しいモードを指定する。
        self.vehicle.set_mode(mode_id)
        return True

    # -- GUIDED 切替（takeoff/goto の前処理）-------------------------------
    async def ensure_guided(self) -> bool:
        if self.state["mode"] == "GUIDED":
            return True
        try:
            if not self._send_mode("GUIDED"):
                return False
        except Exception:
            logger.exception("GUIDED への切替要求に失敗しました")
            return False
        # テレメトリーで GUIDED 反映を最大 5 秒待つ
        deadline = asyncio.get_running_loop().time() + GUIDED_WAIT_SECONDS
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.1)
            if self.state["mode"] == "GUIDED":
                return True
        return False

    # -- コマンド -----------------------------------------------------------
    def _command_long(self, command, *params):
        # param1..param7 を 0 埋めして送信
        params = list(params) + [0] * (7 - len(params))
        self.vehicle.mav.command_long_send(
            self.target_system, self.target_component, command, 0, *params[:7]
        )

    async def arm(self, value: int) -> str:
        if not self.connected:
            return "未接続です。先に接続してください"
        self._command_long(
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, value
        )
        return "アーム要求を送信しました" if value else "ディスアーム要求を送信しました"

    async def takeoff(self, altitude: float) -> str:
        if not self.connected:
            return "未接続です。先に接続してください"
        guided = await self.ensure_guided()
        prefix = "" if guided else "(GUIDED 切替を確認できませんでしたが) "
        # param7 に目標高度
        self._command_long(
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, altitude
        )
        return f"{prefix}離陸コマンドを送信しました（高度 {altitude} m）"

    async def land(self) -> str:
        if not self.connected:
            return "未接続です。先に接続してください"
        self._command_long(mavutil.mavlink.MAV_CMD_NAV_LAND)
        return "着陸コマンドを送信しました"

    async def goto(self, lat: float, lon: float, alt: float) -> str:
        if not self.connected:
            return "未接続です。先に接続してください"
        guided = await self.ensure_guided()
        prefix = "" if guided else "(GUIDED 切替を確認できませんでしたが) "
        # 位置のみ有効（速度・加速度・yaw を無効化）
        type_mask = 0b0000111111111000
        self.vehicle.mav.set_position_target_global_int_send(
            0,
            self.target_system,
            self.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            type_mask,
            int(lat * 1e7),
            int(lon * 1e7),
            float(alt),
            0, 0, 0,  # vx, vy, vz
            0, 0, 0,  # afx, afy, afz
            0, 0,     # yaw, yaw_rate
        )
        return f"{prefix}GoTo を送信しました（{lat:.6f}, {lon:.6f}, {alt} m）"

    async def set_flight_mode(self, mode_name: str) -> str:
        if not self.connected:
            return "未接続です。先に接続してください"
        if not mode_name:
            return "モードが指定されていません"
        try:
            if not self._send_mode(mode_name):
                return f"未知のモードです: {mode_name}"
        except Exception as e:
            logger.exception("モード変更に失敗しました")
            return f"モード変更に失敗: {e}"
        return f"モードを {mode_name} に変更要求しました"


# ---- アプリ初期化 ----------------------------------------------------------
app = FastAPI(title="Drone Web App")
manager = ConnectionManager()
drone = Drone(manager)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.middleware("http")
async def no_cache_for_app_assets(request, call_next):
    """index/JS/CSS をキャッシュさせない（再デプロイ後の stale JS を防ぐ）."""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.get("/")
async def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/register_service")
async def register_service():
    """BlueOS Extension 登録情報.

    WebSocket は BlueOS のプロキシ非対応のため avoid_iframes=True とし、
    新ウィンドウで http://<IP>:<port>/ を直接開かせる。
    """
    return {
        "name": "Drone Web App",
        "description": "ブラウザからドローンを制御する MAVLink Web アプリ",
        "icon": "mdi-drone",
        "company": "",
        "version": "1.0.0",
        "webpage": "",
        "api": "/docs",
        "avoid_iframes": True,
    }


async def handle_command(msg: dict) -> str:
    """JSON コマンドを解釈して実行し、結果メッセージを返す."""
    cmd_type = msg.get("type")
    try:
        if cmd_type == "connect":
            return await drone.connect()
        if cmd_type == "arm":
            return await drone.arm(1)
        if cmd_type == "disarm":
            return await drone.arm(0)
        if cmd_type == "takeoff":
            return await drone.takeoff(float(msg.get("altitude", 0)))
        if cmd_type == "land":
            return await drone.land()
        if cmd_type == "goto":
            return await drone.goto(
                float(msg.get("latitude")),
                float(msg.get("longitude")),
                float(msg.get("altitude")),
            )
        if cmd_type == "mode":
            return await drone.set_flight_mode(msg.get("mode"))
        return f"不明なコマンド: {cmd_type}"
    except Exception as e:
        logger.exception("コマンド処理中にエラーが発生しました: %s", cmd_type)
        return f"コマンドエラー({cmd_type}): {e}"


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    # 接続直後に現在の状態を即時送信
    try:
        await ws.send_json({"type": "state", "state": dict(drone.state)})
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await ws.send_json(
                    {"type": "status", "message": "不正な JSON を受信しました"}
                )
                continue
            result = await handle_command(msg)
            if result:
                await ws.send_json({"type": "status", "message": result})
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        logger.exception("WebSocket でエラーが発生しました")
        manager.disconnect(ws)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
