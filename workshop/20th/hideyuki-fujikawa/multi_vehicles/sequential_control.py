#!/usr/bin/env python3
"""
複数機体順次制御スクリプト

ローバー → ボート → コプター の順で制御を実行します。
前の機体がミッション完了したら、次の機体がスタートします。

各機体の動作:
- ローバー、ボート: アーム → ミッション開始 → ミッション完了待機
- コプター: アーム → 離陸 → ミッション開始 → ミッション完了待機

前提条件:
- 各機体にミッションが事前にアップロードされていること
- SITL が起動していること（multi_vehicle.bat または multi_vehicle_dialog.bat で起動）
"""

from pymavlink import mavutil
import time
import os
import math

# 定数定義
MESSAGE_RATE_HZ = 10  # メッセージ受信レート（Hz）
MESSAGE_INTERVAL_US = 100000  # メッセージ間隔（マイクロ秒）
WAYPOINT_REACHED_THRESHOLD_M = 5.0  # ウェイポイント到達判定距離（メートル）
REQUIRED_CONFIRMATION_COUNT = 5  # 到達確認に必要な連続カウント
EARTH_RADIUS_M = 6371000  # 地球の半径（メートル）
DEFAULT_TAKEOFF_ALTITUDE_M = 3.0  # デフォルト離陸高度（メートル）


def load_mission_from_file(filepath):
    """
    QGC WPL 110形式のミッションファイルを読み込む

    Args:
        filepath: ミッションファイルのパス

    Returns:
        list: ミッションアイテムのリスト
    """
    mission_items = []

    if not os.path.exists(filepath):
        print(f"警告: ミッションファイルが見つかりません: {filepath}")
        return mission_items

    with open(filepath, 'r') as f:
        lines = f.readlines()

    # 最初の行はヘッダー（QGC WPL 110）
    if not lines or not lines[0].startswith('QGC WPL'):
        print(f"警告: 無効なミッションファイル形式: {filepath}")
        return mission_items

    # 2行目以降がウェイポイント
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue

        parts = line.split('\t')
        if len(parts) < 12:
            continue

        # QGC WPL形式のパース
        # seq current frame command param1 param2 param3 param4 x y z autocontinue
        seq = int(parts[0])
        current = int(parts[1])
        frame = int(parts[2])
        command = int(parts[3])
        param1 = float(parts[4])
        param2 = float(parts[5])
        param3 = float(parts[6])
        param4 = float(parts[7])
        x = int(float(parts[8]) * 1e7)  # 緯度を整数に変換
        y = int(float(parts[9]) * 1e7)  # 経度を整数に変換
        z = float(parts[10])
        autocontinue = int(parts[11])

        mission_items.append({
            'seq': seq,
            'current': current,
            'frame': frame,
            'command': command,
            'param1': param1,
            'param2': param2,
            'param3': param3,
            'param4': param4,
            'x': x,
            'y': y,
            'z': z,
            'autocontinue': autocontinue
        })

    return mission_items


class VehicleController:
    """機体制御クラス"""

    def __init__(self, name: str, connection_string: str, vehicle_type: str, mission_file: str = None):
        """
        Args:
            name: 機体名（表示用）
            connection_string: 接続文字列（例: "tcp:127.0.0.1:5762"）
            vehicle_type: 機体タイプ（"rover", "boat", "copter"）
            mission_file: ミッションファイルのパス（オプション）
        """
        self.name = name
        self.connection_string = connection_string
        self.vehicle_type = vehicle_type
        self.mission_file = mission_file
        self.master = None

    def connect(self):
        """機体に接続"""
        print(f"\n[{self.name}] 接続中: {self.connection_string}")
        self.master = mavutil.mavlink_connection(
            self.connection_string, source_system=1, source_component=90)
        self.master.wait_heartbeat()
        print(f"[{self.name}] 接続完了 (sysid: {self.master.target_system}, compid: {self.master.target_component})")

    def _change_mode(self, mode: str):
        """
        フライトモードを変更

        Args:
            mode: 変更先のモード（例: "GUIDED", "AUTO"）
        """
        self.master.set_mode_apm(self.master.mode_mapping()[mode])
        while self.master.flightmode != mode:
            self.master.recv_msg()
        print(f"[{self.name}] モード変更完了: {mode}")

    def arm(self):
        """機体をアーム"""
        print(f"[{self.name}] アーム開始...")
        self._change_mode('GUIDED')
        self.master.arducopter_arm()
        self.master.motors_armed_wait()
        print(f"[{self.name}] アーム完了")

    def _set_message_interval(self, message_id: int):
        """
        メッセージ受信間隔を設定

        Args:
            message_id: メッセージID（例: 33 = GLOBAL_POSITION_INT）
        """
        self.master.mav.command_long_send(
            self.master.target_system, self.master.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
            0, message_id, MESSAGE_INTERVAL_US, 0, 0, 0, 0, 0)

    def takeoff(self, target_altitude: float = DEFAULT_TAKEOFF_ALTITUDE_M):
        """
        離陸（コプターのみ）

        Args:
            target_altitude: 目標高度（メートル）
        """
        if self.vehicle_type != "copter":
            print(f"[{self.name}] 離陸スキップ（コプター以外）")
            return

        print(f"[{self.name}] 離陸開始（目標高度: {target_altitude}m）...")

        # 離陸コマンド送信
        self.master.mav.command_long_send(
            self.master.target_system, self.master.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0, 0, 0, 0, 0, 0, 0, target_altitude)

        # GLOBAL_POSITION_INTメッセージの受信レートを設定
        self._set_message_interval(33)

        # 目標高度への到達を確認
        while True:
            received_msg = self.master.recv_match(
                type='GLOBAL_POSITION_INT', blocking=True)
            current_altitude = received_msg.relative_alt / 1000

            print(f"[{self.name}] 高度: {current_altitude:.2f}m")

            if current_altitude >= target_altitude * 0.95:
                print(f"[{self.name}] 目標高度に到達")
                break

            time.sleep(0.1)

    def start_mission(self):
        """ミッション開始"""
        print(f"[{self.name}] ミッション開始...")
        self._change_mode('AUTO')

    def upload_mission(self, mission_items):
        """
        ミッションをアップロード

        Args:
            mission_items: ミッションアイテムのリスト
        """
        if not mission_items:
            print(f"[{self.name}] ミッションアイテムがありません")
            return

        print(f"[{self.name}] ミッションアップロード開始（{len(mission_items)}個のウェイポイント）")

        # ミッションをクリア
        self.master.mav.mission_clear_all_send(
            self.master.target_system, self.master.target_component)
        time.sleep(0.5)

        # ミッション数を送信
        self.master.mav.mission_count_send(
            self.master.target_system, self.master.target_component, len(mission_items))

        # 各ミッションアイテムを送信
        for item in mission_items:
            # MISSION_REQUEST または MISSION_REQUEST_INT を待機
            ack = self.master.recv_match(type=['MISSION_REQUEST', 'MISSION_REQUEST_INT'], blocking=True, timeout=5)
            if not ack:
                print(f"[{self.name}] タイムアウト: ミッションリクエストを受信できませんでした")
                return

            # ミッションアイテムを送信
            self.master.mav.mission_item_int_send(
                self.master.target_system,
                self.master.target_component,
                item['seq'],
                item['frame'],
                item['command'],
                item['current'],
                item['autocontinue'],
                item['param1'],
                item['param2'],
                item['param3'],
                item['param4'],
                item['x'],
                item['y'],
                item['z'],
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION
            )

        # アップロード完了を待機
        ack = self.master.recv_match(type='MISSION_ACK', blocking=True, timeout=5)
        if ack and ack.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
            print(f"[{self.name}] ミッションアップロード完了")
        else:
            print(f"[{self.name}] ミッションアップロード失敗")

    def get_mission_count(self):
        """ミッションアイテム数を取得"""
        self.master.mav.mission_request_list_send(
            self.master.target_system, self.master.target_component)
        mission_count_msg = self.master.recv_match(
            type='MISSION_COUNT', blocking=True, timeout=5)
        if mission_count_msg:
            return mission_count_msg.count
        return 0

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        2地点間の距離を計算（Haversine公式）

        Args:
            lat1: 地点1の緯度（度）
            lon1: 地点1の経度（度）
            lat2: 地点2の緯度（度）
            lon2: 地点2の経度（度）

        Returns:
            float: 距離（メートル）
        """
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

        return EARTH_RADIUS_M * c

    def get_distance_to_waypoint(self, target_lat: float, target_lon: float) -> float:
        """
        現在位置から目標ウェイポイントまでの距離を計算（メートル）

        Args:
            target_lat: 目標緯度（度）
            target_lon: 目標経度（度）

        Returns:
            float: 距離（メートル）、取得失敗時はinf
        """
        msg = self.master.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=3)
        if not msg:
            return float('inf')

        current_lat = msg.lat / 1e7
        current_lon = msg.lon / 1e7

        return self._calculate_distance(current_lat, current_lon, target_lat, target_lon)

    def _get_last_waypoint_position(self):
        """
        最後のウェイポイントの座標を取得

        Returns:
            tuple: (緯度, 経度, ウェイポイント番号) または (None, None, None)
        """
        mission_count = self.get_mission_count()
        print(f"[{self.name}] ミッションアイテム数: {mission_count}")

        if mission_count == 0:
            print(f"[{self.name}] 警告: ミッションがアップロードされていません")
            return None, None, None

        last_waypoint_seq = mission_count - 1

        self.master.mav.mission_request_int_send(
            self.master.target_system, self.master.target_component, last_waypoint_seq)
        last_wp = self.master.recv_match(type='MISSION_ITEM_INT', blocking=True, timeout=5)

        if not last_wp:
            print(f"[{self.name}] 警告: 最後のウェイポイント情報を取得できませんでした")
            return None, None, None

        target_lat = last_wp.x / 1e7
        target_lon = last_wp.y / 1e7
        print(f"[{self.name}] 最後のウェイポイント座標: ({target_lat:.6f}, {target_lon:.6f})")

        return target_lat, target_lon, last_waypoint_seq

    def wait_mission_complete(self):
        """ミッション完了を待機（位置情報ベース）"""
        print(f"[{self.name}] ミッション完了待機中...")

        target_lat, target_lon, last_waypoint_seq = self._get_last_waypoint_position()
        if target_lat is None:
            return

        self._set_message_interval(33)  # GLOBAL_POSITION_INT
        time.sleep(1)

        last_distance = float('inf')
        within_threshold_count = 0

        print(f"[{self.name}] 最後のウェイポイント({last_waypoint_seq})への到達を待機中（距離ベース）...")

        while True:
            msg = self.master.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=1)

            if msg:
                current_lat = msg.lat / 1e7
                current_lon = msg.lon / 1e7
                distance = self._calculate_distance(current_lat, current_lon, target_lat, target_lon)

                # 距離が大きく変わったらログ出力
                if abs(distance - last_distance) > 5:
                    print(f"[{self.name}] 最終WPまで: {distance:.1f}m")
                    last_distance = distance

                # 距離ベースの到達判定
                if distance < WAYPOINT_REACHED_THRESHOLD_M:
                    within_threshold_count += 1
                    if within_threshold_count >= REQUIRED_CONFIRMATION_COUNT:
                        print(f"[{self.name}] ★★★ 位置判定: 最終WP({last_waypoint_seq})に到達 ({distance:.1f}m) ★★★")
                        time.sleep(2)
                        self.master.recv_msg()
                        current_mode = self.master.flightmode
                        print(f"[{self.name}] ミッション完了（最終モード: {current_mode}）")
                        return
                    else:
                        print(f"[{self.name}] 最終WPに接近中: {distance:.1f}m (確認: {within_threshold_count}/{REQUIRED_CONFIRMATION_COUNT})")
                else:
                    within_threshold_count = 0

            time.sleep(0.1)

    def close(self):
        """接続を閉じる"""
        if self.master:
            print(f"[{self.name}] 接続を閉じます")
            self.master.close()


def main():
    """メイン処理"""

    print("=" * 60)
    print("複数機体順次制御スクリプト")
    print("ローバー → ボート → コプター")
    print("=" * 60)

    # 接続先ホストの設定（環境変数またはデフォルト）
    # 環境変数 SITL_HOST を設定することで変更可能
    # 例: export SITL_HOST=192.168.1.100
    sitl_host = os.environ.get('SITL_HOST', '127.0.0.1')
    print(f"接続先ホスト: {sitl_host}")

    # スクリプトのディレクトリを取得
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 機体定義（ミッションファイル付き）
    vehicles = [
        VehicleController("ローバー", f"tcp:{sitl_host}:5762", "rover",
                         os.path.join(script_dir, "rover_mission.waypoints")),
        VehicleController("ボート", f"tcp:{sitl_host}:5772", "boat",
                         os.path.join(script_dir, "boat_mission.waypoints")),
        VehicleController("コプター", f"tcp:{sitl_host}:5782", "copter",
                         os.path.join(script_dir, "copter_mission.waypoints")),
    ]

    try:
        for vehicle in vehicles:
            print(f"\n{'=' * 60}")
            print(f"[{vehicle.name}] 制御開始")
            print(f"{'=' * 60}")

            # 接続
            vehicle.connect()
            time.sleep(1)

            # ミッションファイルがある場合はアップロード
            if vehicle.mission_file:
                mission_items = load_mission_from_file(vehicle.mission_file)
                if mission_items:
                    vehicle.upload_mission(mission_items)
                    time.sleep(1)
                else:
                    print(f"[{vehicle.name}] 警告: ミッションファイルの読み込みに失敗しました")

            # アーム
            vehicle.arm()
            time.sleep(1)

            # 離陸（コプターのみ）
            if vehicle.vehicle_type == "copter":
                vehicle.takeoff()
                time.sleep(1)

            # ミッション開始
            vehicle.start_mission()

            # ミッション完了待機
            vehicle.wait_mission_complete()

            print(f"\n[{vehicle.name}] 制御完了")

            # 次の機体に進む前に少し待機
            time.sleep(2)

        print("\n" + "=" * 60)
        print("全機体の制御が完了しました")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\nユーザーによる中断")

    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 全機体の接続を閉じる
        print("\n接続をクローズ中...")
        for vehicle in vehicles:
            vehicle.close()


if __name__ == '__main__':
    main()
