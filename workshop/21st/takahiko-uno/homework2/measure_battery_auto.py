# -*- coding: utf-8 -*-
"""
全自動フライト + 区間別バッテリー消費量計測スクリプト
WayPointファイルで作成した、上昇、下降、南、西、北、東の四角形ミッションを自動で実行し、
各区間ごとのバッテリー消費量(mAh)を計測する
※専用に作成したWayPointファイルが必要。 機体の向きは、常に北向きで飛行するようにしている

前提:
  - 計測開始、終了のトリガは、サーボ9番のPWM信号を1900と1100に変化させることで本プログラム側から検知する
    よって、サーボ9番が未使用チャンネルであること。使用済の場合、他の未使用チャンネルに変更し、W
    ayPointファイルのCMD:183行の値とそろえること
  - 専用に作成したWayPoint が Mission Planner等で機体にあらかじめ書き込まれていること
    ホームポイントを参照するため、実行環境と同一のカレントディレクトリに .waypoints ファイルが存在すること
  - GPSフィックス、EKF、コンパス等の事前チェックに問題がないこと

安全対策
  - ARM前にバッテリー残量が20%未満の場合、ARM/離陸せずに終了する
  - バッテリー残量が20%未満になった場合、強制的にRTLする（RTL_ALTITUDE[15m]まで上昇して帰還）
  - 電圧ベースの保険（残量%が取得できない機体への保険）として、起動時にオペレーターが手動でセル数を入力し、
    LOW_CELL_VOLTAGE[V/セル]を下回った場合に強制RTLする

流れ:
  1. 接続、バッテリーセル数の手動入力（3Sデフォルト）
  2. アーミング可能になるまで待機
  3. GUIDEDモードでARM
     -> ARM後、WayPointファイルNo.0行(seq=0)の緯度経度を強制的にホームポイントに設定
        （MissionPlannerでの機体の現在位置に関わらず、No.0の緯度経度をホームとする）
        高度はホーム設定時の機体の実測値（GPS絶対高度）を使用する
  4. ARM完了後、コンソールで離陸(ミッション実行)の可否を確認
  5. 許可されたら、まずGUIDEDモードで垂直に10m上昇（低高度での水平移動を避ける安全対策）
     -> その後AUTOモードに切替
     -> ミッション先頭の NAV_TAKEOFF により機体が離陸（既に10m上昇済み）
     
     以下は WayPointファイルの内容に依存する
     -> 10mで5秒待機
     -> 区間1: 上昇 (10m -> 25m)
     -> 区間2: 下降 (25m -> 10m)
     -> 区間3〜7: 既存の四角形ミッション（各脚に開始/終了マーカー）
     -> 最終脚でホームポイント上空に帰還
     -> LOITER_UNLIM でホーム上空にてホバリング待機（自動着陸はしない）

  6. 飛行中、servo9_raw の値変化を監視して区間ごとのバッテリー消費量(mAh)を記録
     区間が終了するたびに CSV を都度保存（ホーム上空帰還時点でも確実に記録される）
  7. 全区間（TOTAL_LEGS区間）の計測が完了したら、コンソールで着陸の実行可否を確認
  8. 確認が取れたら LAND モードに切り替えて着陸、ディスアームを検知して終了
"""

from dronekit import connect, VehicleMode, LocationGlobal
import time
import csv
import datetime
import sys
import select
import math
import os
import glob

# ==== 接続設定 ====
CONNECTION_STRING = "tcp:192.168.3.210:5762"  # ※※※接続方法毎に変更※※※
#BAUD = 57600

# ==== WayPointファイル設定 ====
# No.0行(seq=0)の座標を強制的にホームポイントに設定するために参照する。
# 機体をMissionPlanner等でどこにいる状態でも、このファイルのNo.0座標をホームにする。
# 実行時のカレントディレクトリにある .waypoints ファイルを参照する。
def find_waypoint_file():
    """
    実行時のカレントディレクトリ内の .waypoints ファイルを探して返す。
    参照するファイルを一意に決めるため、見つからない場合・複数ある場合はエラーにする。
    """
    candidates = sorted(glob.glob(os.path.join(os.getcwd(), "*.waypoints")))
    if not candidates:
        raise FileNotFoundError(
            "カレントディレクトリに .waypoints ファイルが見つかりません: %s" % os.getcwd())
    if len(candidates) > 1:
        raise ValueError(
            "カレントディレクトリに .waypoints ファイルが複数あります。参照するファイルを1つにしてください:\n  %s"
            % "\n  ".join(candidates))
    return candidates[0]


WAYPOINT_FILE = find_waypoint_file()

# ==== バッテリー計測トリガー設定（WPファイルの CMD:183と合わせる） ====
SERVO_CHANNEL = 9           # ※※※空きチャンネルにすること※※※
PWM_THRESHOLD = 1500        # これを超えたら開始、下回ったら終了

# Square11.waypoints の区間数（上昇・下降・南西北東の4方向 = 6）
TOTAL_LEGS = 6

# バッテリー残量がこの値[%]未満になったら強制的にRTLする
LOW_BATTERY_THRESHOLD = 20

# 強制RTL時に上昇する高度[m]（ArduPilotのRTL_ALTパラメータに設定する）
RTL_ALTITUDE = 15

# AUTO(ミッション)開始前に、GUIDEDモードで垂直に上昇する高度[m]
# WayPoint先頭座標と現在地が離れていても、低高度での水平移動を避けるため一旦真上へ上昇する
TAKEOFF_ALTITUDE = 10.0   ##### デモ時は低めにする　　実運用では周囲の建物の高さ以上確保
# 垂直離陸の完了待ちタイムアウト[秒]
TAKEOFF_TIMEOUT = 30.0

# 着陸確認前に、ホームポイント上空への到達とみなす水平距離[m]
HOME_ARRIVAL_RADIUS = 3.0
# ホーム到達待ちのタイムアウト[秒]（超過しても着陸確認へ進む）
HOME_ARRIVAL_TIMEOUT = 120.0

# ==== 電圧ベースの保険RTL設定（残量%が取得できない機体への保険） ====
# セル数はARM前にオペレーターが手動入力する。空入力（space/Enter）時の既定セル数。
DEFAULT_CELL_COUNT = 3
# このセル電圧[V/セル]を下回ったら強制RTL（下限電圧 = 入力セル数 × この値）
LOW_CELL_VOLTAGE = 3.4
# 電圧は負荷変動(サグ)で瞬間的に落ちるため、この秒数連続で下回った場合のみ発動する
LOW_VOLTAGE_TIMER = 5.0

# ファイル名: battery_consumed_YYYYMMDD_HHMM.csv（実行時の日付・時刻を使用）
OUTPUT_CSV = "battery_consumed_%s.csv" % datetime.datetime.now().strftime("%Y%m%d_%H%M")


def wait_until_armable(vehicle):
    print("機体の状態確認中（GPS/EKF/コンパス等）...")
    while not vehicle.is_armable:
        print("  is_armable=False ... 待機中 (GPS: %s, EKF OK: %s)" % (
            vehicle.gps_0.fix_type, vehicle.ekf_ok))
        time.sleep(1)
    print("アーミング可能な状態になりました。")


def ensure_auto_options(vehicle):
    """
    ArduPilot Copterはデフォルトで、AUTOモード中に地上からミッションを開始する際、
    RC送信機のスロットルを上げないと離陸(ミッション)が始まらない安全設計になっている。
    DroneKit(MAVLink)のみで完全自動運用する場合、このチェックが永久に満たされず
    「ARM済み・AUTOモードだが離陸しない」状態になるため、AUTO_OPTIONSパラメータで
    この挙動を無効化する。
      bit0 (1) = AUTOモード中のアーミングを許可
      bit1 (2) = スロットルを上げなくても離陸(ミッション)を開始することを許可
    """

    current = vehicle.parameters.get('AUTO_OPTIONS', 0)
    required_bits = 0b11  # bit0 + bit1 = 3
    new_value = int(current) | required_bits

    if int(current) != new_value:
        print("AUTO_OPTIONS を %d -> %d に変更します（スロットル操作なしでの自動離陸を許可）。" % (
            current, new_value))
        vehicle.parameters['AUTO_OPTIONS'] = new_value
        # パラメータ反映待ち
        time.sleep(2)
        readback = vehicle.parameters.get('AUTO_OPTIONS', None)
        print("AUTO_OPTIONS 設定後の値: %s" % readback)
    else:
        print("AUTO_OPTIONS は既に必要なビットが立っています（値=%d）。" % current)


def ensure_rtl_altitude(vehicle):
    """
    強制RTL時の上昇高度を RTL_ALTITUDE[m] に設定する。
    ArduPilotの RTL_ALT パラメータは単位が cm のため、100倍して設定する。
    """
    target_cm = RTL_ALTITUDE * 100
    current = vehicle.parameters.get('RTL_ALT', None)

    if current is None or int(current) != target_cm:
        print("RTL_ALT を %s -> %d (=%dm) に設定します。" % (
            current, target_cm, RTL_ALTITUDE))
        vehicle.parameters['RTL_ALT'] = target_cm
        # パラメータ反映待ち
        time.sleep(2)
        readback = vehicle.parameters.get('RTL_ALT', None)
        print("RTL_ALT 設定後の値: %s (cm)" % readback)
    else:
        print("RTL_ALT は既に %dm(%dcm) に設定されています。" % (RTL_ALTITUDE, target_cm))


def read_home_from_waypoints(path):
    """
    WayPointファイル(QGC WPL 110形式)のNo.0行(seq=0)から
    ホームポイントの緯度・経度・高度を読み取って返す。
    フィールドはタブ区切りで、seq lat lon alt はそれぞれ 0,8,9,10列目。
    """
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 1行目はヘッダ("QGC WPL 110")なので2行目以降を走査
    for line in lines[1:]:
        parts = line.strip().split("\t")
        if len(parts) < 12:
            continue
        if int(parts[0]) == 0:  # seq == 0 がホーム行
            lat = float(parts[8])
            lon = float(parts[9])
            alt = float(parts[10])
            return lat, lon, alt

    raise ValueError("WayPointファイルにNo.0行(seq=0)が見つかりません: %s" % path)


def set_home_location(vehicle, lat, lon):
    """
    ホームポイントの緯度・経度をWayPointファイルNo.0行の座標に強制設定する。
    高度は機体の実測値（GPSの絶対高度[m MSL]）を使用する。
    ArduPilotは通常アーミング時の現在地をホームにするため、機体の実際の位置に
    関わらず指定座標をホームにしたい場合に使用する（DO_SET_HOME相当）。
    アーミング時の自動上書きを避けるため、ARM後に呼び出すこと。
    """
    # home_location はコマンドをダウンロードしないと取得/設定できない
    cmds = vehicle.commands
    cmds.download()
    cmds.wait_ready()

    # 高度は機体の実測値（絶対高度）を使用する
    alt = vehicle.location.global_frame.alt
    if alt is None:
        raise ValueError("機体の高度(実測値)を取得できませんでした。")

    print("ホームポイントを設定します（緯度経度=WayPoint No.0, 高度=機体実測値）: "
          "lat=%.8f, lon=%.8f, alt=%.2f" % (lat, lon, alt))
    vehicle.home_location = LocationGlobal(lat, lon, alt)

    # 反映を待って読み戻す
    time.sleep(2)
    cmds.download()
    cmds.wait_ready()
    home = vehicle.home_location
    if home is not None:
        print("設定後のホームポイント: lat=%.8f, lon=%.8f, alt=%.2f" % (
            home.lat, home.lon, home.alt))
    else:
        print("ホームポイントの読み戻しに失敗しましたが、設定コマンドは送信済みです。")


def get_distance_metres(loc1, loc2):
    """2点の global_frame（緯度経度）間の水平距離[m]を近似計算する。"""
    dlat = loc2.lat - loc1.lat
    dlon = loc2.lon - loc1.lon
    # 緯度1度≒1.113195e5[m]の近似（数百m規模の距離では十分な精度）
    return math.sqrt((dlat * dlat) + (dlon * dlon)) * 1.113195e5


def wait_until_home(vehicle, state):
    """
    機体がホームポイント上空（水平距離 HOME_ARRIVAL_RADIUS[m] 以内）に
    到達するまで待機する。着陸確認プロンプトを出す前に呼び出す。
      - 低バッテリー強制RTLが発動した場合は即座に戻る（呼び出し側でRTL処理へ）
      - ホーム位置が取得できない/タイムアウトの場合は待機を打ち切って戻る
    """
    # home_location は commands.download() 後に得られる
    if vehicle.home_location is None:
        cmds = vehicle.commands
        cmds.download()
        cmds.wait_ready()
    home = vehicle.home_location
    if home is None:
        print("ホーム位置を取得できませんでした。到達判定をスキップして着陸確認へ進みます。")
        return

    print("ホームポイント上空への到達を待機します...")
    wait_start = time.time()
    while True:
        if state["low_battery_rtl"]:
            return
        if time.time() - wait_start > HOME_ARRIVAL_TIMEOUT:
            print("ホーム到達待ちがタイムアウトしました。着陸確認へ進みます。")
            return
        current = vehicle.location.global_frame
        if current is None or current.lat is None or current.lon is None:
            time.sleep(1)
            continue
        dist = get_distance_metres(current, home)
        print("  ホームまで %.1f m" % dist)
        if dist <= HOME_ARRIVAL_RADIUS:
            print("ホームポイント上空に到達しました。")
            return
        time.sleep(1)


def check_battery_before_arm(battery):
    """
    ARM前にバッテリー残量[%]を確認する。
    残量%が LOW_BATTERY_THRESHOLD 未満の場合は False を返し、離陸させない。
    残量%が取得できない機体では電圧ベースの保険で保護するため、
    残量%が不明（None）の場合はチェックをスキップして True を返す。
    """
    # BATTERY_STATUS がまだ届いていない可能性があるため、少しだけ受信を待つ
    wait_start = time.time()
    while battery["remaining"] is None and battery["voltage"] is None:
        if time.time() - wait_start > 5:
            print("バッテリー情報を取得できませんでした。残量%チェックはスキップします。")
            return True
        time.sleep(0.5)

    remaining = battery["remaining"]
    if remaining is None:
        print("バッテリー残量%が取得できない機体のため、ARM前の残量%チェックはスキップします。"
              "（電圧ベースの保険で保護します）")
        return True

    print("ARM前バッテリー残量チェック: 残量 %d%%（しきい値 %d%%）" % (
        remaining, LOW_BATTERY_THRESHOLD))
    if remaining < LOW_BATTERY_THRESHOLD:
        print("バッテリー残量が %d%% 未満（現在 %d%%）のため、ARM/離陸を中止します。" % (
            LOW_BATTERY_THRESHOLD, remaining))
        return False
    return True


def arm_vehicle(vehicle):
    print("モードを GUIDED に設定します。")
    vehicle.mode = VehicleMode("GUIDED")
    while vehicle.mode.name != "GUIDED":
        time.sleep(0.5)

    print("ARMします。")
    vehicle.armed = True
    arm_timeout = 30  # ARM完了までの最大待機時間[秒]
    arm_start = time.time()
    while not vehicle.armed:
        if time.time() - arm_start > arm_timeout:
            raise TimeoutError("ARMが%d秒以内に完了しませんでした。" % arm_timeout)
        print("  ARM待機中...")
        time.sleep(1)
    print("ARMしました。")


def guided_takeoff(vehicle, target_alt):
    """
    GUIDEDモードで垂直に target_alt[m](対地高度)まで上昇する。
    WayPoint先頭座標と現在地が離れている場合に、低高度での水平移動で人物等へ
    接触するのを避けるため、AUTO(ミッション)開始前に真上へ離陸させる。
    """
    # simple_takeoff はGUIDEDモード・ARM済みが前提
    if vehicle.mode.name != "GUIDED":
        print("モードを GUIDED に設定します。")
        vehicle.mode = VehicleMode("GUIDED")
        while vehicle.mode.name != "GUIDED":
            time.sleep(0.5)

    print("GUIDEDモードで垂直に %.1fm まで離陸します。" % target_alt)
    vehicle.simple_takeoff(target_alt)

    # 目標高度の95%に達するまで待機（タイムアウトあり）
    takeoff_start = time.time()
    while True:
        alt = vehicle.location.global_relative_frame.alt
        if alt is not None:
            print("  高度 %.1f m" % alt)
            if alt >= target_alt * 0.95:
                print("目標高度に到達しました。")
                return
        if time.time() - takeoff_start > TAKEOFF_TIMEOUT:
            print("垂直離陸が%.0f秒以内に完了しませんでした（現在高度 %s m）。処理を継続します。" % (
                TAKEOFF_TIMEOUT, alt))
            return
        time.sleep(1)


def switch_to_auto(vehicle):
    print("モードを AUTO に切り替えます。ミッション先頭の NAV_TAKEOFF により自動離陸します。")
    vehicle.mode = VehicleMode("AUTO")
    while vehicle.mode.name != "AUTO":
        time.sleep(0.5)
    print("AUTOモードに入りました。ミッションを実行します。")


def disarm_vehicle(vehicle):
    print("ディスアームします。")
    vehicle.armed = False
    while vehicle.armed:
        time.sleep(1)
    print("ディスアームしました。")


def save_csv(results):
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=[
                "leg", "elapsed_sec", "consumed_mah", "start_voltage", "end_voltage",
                "start_temp_c", "end_temp_c",
                "start_lat", "start_lon", "end_lat", "end_lon",
            ]
        )
        writer.writeheader()
        writer.writerows(results)


def main():
    print("Connecting to vehicle on: %s" % CONNECTION_STRING)
    vehicle = connect(CONNECTION_STRING, wait_ready=True)
    print("Connected.")

    # ---- バッテリー計測用の状態管理 ----
    state = {
        "measuring": False,
        "leg_number": 0,
        "start_time": None,
        "start_consumed_mah": None,
        "start_voltage": None,
        "last_pwm": None,
        "all_legs_done": False,
        "low_battery_rtl": False,
        "low_voltage_threshold": None,   # 起動時に自動判定する電圧下限[V]（Noneなら電圧保護は無効）
        "low_voltage_since": None,       # 電圧が下限を連続で下回り始めた時刻
    }
    battery = {"current_consumed": None, "voltage": None, "temp_c": None, "remaining": None}
    results = []

    def battery_status_listener(self, name, message):
        battery["current_consumed"] = message.current_consumed
        if message.voltages and message.voltages[0] not in (0, 65535):
            battery["voltage"] = message.voltages[0] / 1000.0
        else:
            battery["voltage"] = None
        # temperature: 単位はセンチ度(0.01degC)。INT16_MAX(32767)は未対応/不明を示す
        if message.temperature is not None and message.temperature != 32767:
            battery["temp_c"] = message.temperature / 100.0
        else:
            battery["temp_c"] = None
        # battery_remaining: 残量[%]。-1 は不明を示す
        if message.battery_remaining is not None and message.battery_remaining >= 0:
            battery["remaining"] = message.battery_remaining
        else:
            battery["remaining"] = None

        # ---- 全工程共通: 残量%または電圧下限を下回ったら強制RTL（ARM中のみ） ----
        if vehicle.armed and not state["low_battery_rtl"]:
            trigger_reason = None

            # (1) 主軸: 残量%ベース（セル数に依存しない）
            if battery["remaining"] is not None and battery["remaining"] < LOW_BATTERY_THRESHOLD:
                trigger_reason = "残量 %d%%（%d%%未満）" % (battery["remaining"], LOW_BATTERY_THRESHOLD)

            # (2) 保険: 電圧ベース（起動時に自動判定した下限）。負荷サグ誤発動を避けるため継続時間で判定
            elif state["low_voltage_threshold"] is not None and battery["voltage"] is not None:
                if battery["voltage"] < state["low_voltage_threshold"]:
                    if state["low_voltage_since"] is None:
                        state["low_voltage_since"] = time.time()
                    elif time.time() - state["low_voltage_since"] >= LOW_VOLTAGE_TIMER:
                        trigger_reason = "電圧 %.2fV（下限 %.2fV を %.0f秒継続で下回り）" % (
                            battery["voltage"], state["low_voltage_threshold"], LOW_VOLTAGE_TIMER)
                else:
                    # 下限を上回ったら継続タイマーをリセット
                    state["low_voltage_since"] = None

            if trigger_reason is not None:
                state["low_battery_rtl"] = True
                print("\n[警告] バッテリー低下を検知（%s）。強制的にRTLします。" % trigger_reason)
                vehicle.mode = VehicleMode("RTL")

    def servo_output_listener(self, name, message):
        attr_name = "servo%d_raw" % SERVO_CHANNEL
        pwm = getattr(message, attr_name, None)
        if pwm is None:
            return

        last_pwm = state["last_pwm"]
        state["last_pwm"] = pwm

        # 立ち上がりエッジ -> 区間「開始」
        if pwm >= PWM_THRESHOLD and (last_pwm is None or last_pwm < PWM_THRESHOLD) and not state["measuring"]:
            state["leg_number"] += 1
            state["measuring"] = True
            state["start_time"] = time.time()
            state["start_consumed_mah"] = battery["current_consumed"]
            state["start_voltage"] = battery["voltage"]
            state["start_temp_c"] = battery["temp_c"]
            loc = vehicle.location.global_frame
            state["start_lat"] = loc.lat
            state["start_lon"] = loc.lon

            print("[区間 %d/%d] 計測開始  起点消費電力=%s[mAh]" % (
                state["leg_number"], TOTAL_LEGS, state["start_consumed_mah"])) 

        # 立ち下がりエッジ -> 区間「終了」
        elif pwm < PWM_THRESHOLD and (last_pwm is None or last_pwm >= PWM_THRESHOLD) and state["measuring"]:
            state["measuring"] = False
            end_time = time.time()
            end_consumed_mah = battery["current_consumed"]
            end_voltage = battery["voltage"]
            end_temp_c = battery["temp_c"]
            end_loc = vehicle.location.global_frame
            end_lat = end_loc.lat
            end_lon = end_loc.lon

            elapsed = end_time - state["start_time"]

            consumed = None
            start_c = state["start_consumed_mah"]
            if start_c is not None and end_consumed_mah is not None \
                    and start_c >= 0 and end_consumed_mah >= 0:
                consumed = end_consumed_mah - start_c

            print("[区間 %d/%d] 計測終了  経過時間=%.1f[sec]  消費電力量=%s[mAh]  "
                  "電圧=%s[V] -> %s[V]" % (
                state["leg_number"], TOTAL_LEGS, elapsed, consumed,
                state["start_voltage"], end_voltage ))

            results.append({
                "leg": state["leg_number"],
                "elapsed_sec": round(elapsed, 1),
                "consumed_mah": consumed,
                "start_voltage": state["start_voltage"],
                "end_voltage": end_voltage,
                "start_lat": state["start_lat"],
                "start_lon": state["start_lon"],
                "end_lat": end_lat,
                "end_lon": end_lon,
                "start_temp_c": state["start_temp_c"],
                "end_temp_c": end_temp_c,
            })

            # 区間が終わるたびに都度保存（ホーム上空帰還時点でも確実にファイルに残る）
            save_csv(results)

            if state["leg_number"] >= TOTAL_LEGS:
                state["all_legs_done"] = True
                print("\n全区間（%d区間）の計測が完了しました。" % TOTAL_LEGS)
                print("計測結果を %s に保存しました。" % OUTPUT_CSV)

    vehicle.add_message_listener("BATTERY_STATUS", battery_status_listener)
    vehicle.add_message_listener("SERVO_OUTPUT_RAW", servo_output_listener)

    # ---- ARM前にバッテリーのセル数を手動入力（電圧ベース保護の下限[V]算出に使用） ----
    # 機体（セル数）が固定できないため、オペレーターが 1〜5 の数字でセル数を指定する。
    # spaceまたはEnter（空入力）はデフォルト 3S とする。
    while True:
        raw = input("バッテリーのセル数(S)を入力してください [1-5]（space/Enterで既定 %dS）: " % DEFAULT_CELL_COUNT)
        text = raw.strip()
        if text == "":
            cell_count = DEFAULT_CELL_COUNT
            break
        if text.isdigit() and 1 <= int(text) <= 5:
            cell_count = int(text)
            break
        print("1〜5 の数字、またはspace/Enter（既定 %dS）で入力してください。" % DEFAULT_CELL_COUNT)

    state["low_voltage_threshold"] = cell_count * LOW_CELL_VOLTAGE
    print("セル数=%dS で設定しました。電圧下限=%.2fV（%.2fV/セル×%dS）で保護します。" % (
        cell_count, state["low_voltage_threshold"], LOW_CELL_VOLTAGE, cell_count))

    # ---- ホーム座標をWayPointファイルNo.0行から読み取り（ARM前に検証しておく） ----
    # 緯度・経度のみ使用する。高度はARM後に機体の実測値を使う。
    home_lat, home_lon, _ = read_home_from_waypoints(WAYPOINT_FILE)
    print("WayPointファイルNo.0のホーム座標(緯度経度): lat=%.8f, lon=%.8f" % (
        home_lat, home_lon))

    # ---- 自動飛行シーケンス ----
    try:
        wait_until_armable(vehicle)

        # ---- ARM前のバッテリー残量チェック（20%未満なら離陸せず終了） ----
        if not check_battery_before_arm(battery):
            print("バッテリー残量不足のため、ARMせずに処理を終了します。CSVファイルは生成していません。")
            vehicle.close()
            return

        ensure_auto_options(vehicle)
        ensure_rtl_altitude(vehicle)
        arm_vehicle(vehicle)

        # ---- ホームポイントをWayPointファイルNo.0の緯度経度に強制設定（高度は実測値） ----
        # ArduPilotはアーミング時に現在地をホームへ上書きするため、ARM後に設定する。
        set_home_location(vehicle, home_lat, home_lon)

        # ---- 離陸confirmationを求める ----
        # ARM完了後は1秒間隔でビープ音を鳴らしつつ y/n 入力を待つ。
        # 入力を待っている間にディスアーム状態に変化した場合は、その場で終了する。
        print("\nARMが完了しました（プロペラは低速回転中の可能性があります）。")
        print("\n離陸してミッション（計測）を実行しますか？\n（space または Enter で実行、"
              "その他の文字を入力してEnterでキャンセル）: ", end="", flush=True)
        takeoff_confirmed = None
        last_beep = 0.0
        while takeoff_confirmed is None:
            # y/n 入力前にディスアーム状態へ変化したら終了
            if not vehicle.armed:
                print("\nディスアーム状態を検知しました。処理を終了します。")
                vehicle.close()
                return

            # 低バッテリーで強制RTLが発動したら離陸せず終了
            if state["low_battery_rtl"]:
                print("\nバッテリー低下により離陸を中止します。RTL/ディスアームを待機します。")
                while vehicle.armed:
                    time.sleep(1)
                print("ディスアームを確認しました。処理を終了します。")
                vehicle.close()
                return

            # 1秒間隔でビープ音（端末ベル）を鳴らす
            now = time.time()
            if now - last_beep >= 1.0:
                sys.stdout.write("\a")
                sys.stdout.flush()
                last_beep = now

            # 標準入力を非ブロッキングで確認（0.1秒待ち）
            # space または Enter（空入力）= 実行(yes)、それ以外 = キャンセル(no)
            ready, _, _ = select.select([sys.stdin], [], [], 0.1)
            if ready:
                answer = sys.stdin.readline().strip()
                takeoff_confirmed = (answer == "")

        print("\n ")
        if not takeoff_confirmed:
            print("離陸を中止します。")
            disarm_vehicle(vehicle)
            print("ディスアームして終了しました。CSVファイルは生成していません。")
            vehicle.close()
            return

        # ---- AUTO開始前にGUIDEDで垂直離陸 ----
        # WayPoint先頭座標と現在地が離れていても、低高度での水平移動を避けるため、
        # 一旦真上へ TAKEOFF_ALTITUDE[m] 上昇してからミッションを開始する。
        guided_takeoff(vehicle, TAKEOFF_ALTITUDE)

        switch_to_auto(vehicle)

        print("ミッション実行中... 全区間の計測完了まで待機します。")
        print("(Ctrl+Cで途中終了した場合は、手動でRTL/LANDを実行してください)\n")

        while not state["all_legs_done"] and not state["low_battery_rtl"]:
            time.sleep(1)

        # ---- バッテリー低下による強制RTLの場合 ----
        if state["low_battery_rtl"]:
            print("バッテリー低下によりRTL中です。着陸・ディスアームを待機します。")
            while vehicle.armed:
                time.sleep(1)
            print("ディスアームを確認しました。RTL完了です。")
            save_csv(results)
            print("結果を %s に保存しました。" % OUTPUT_CSV)
            vehicle.close()
            return

        # ---- ホームポイント上空への到達を待機 ----
        print("\n機体はホームポイントへ移動します。")
        wait_until_home(vehicle, state)

        # ホーム到達待ちの間に低バッテリー強制RTLが発動した場合の処理
        if state["low_battery_rtl"]:
            print("バッテリー低下によりRTL中です。着陸・ディスアームを待機します。")
            while vehicle.armed:
                time.sleep(1)
            print("ディスアームを確認しました。RTL完了です。")
            save_csv(results)
            print("結果を %s に保存しました。" % OUTPUT_CSV)
            vehicle.close()
            return

        # ---- 着陸confirmationを求める ----
        landing_prompt = ("着陸を実行しますか？（space または Enter で着陸、"
                          "その他の文字を入力してEnterで保留）: ")
        print(landing_prompt, end="", flush=True)
        while True:
            # 待機中に低バッテリー強制RTLが発動したら着陸確認を打ち切る
            if state["low_battery_rtl"]:
                print("\nバッテリー低下によりRTL中です。着陸・ディスアームを待機します。")
                while vehicle.armed:
                    time.sleep(1)
                print("ディスアームを確認しました。RTL完了です。")
                save_csv(results)
                print("結果を %s に保存しました。" % OUTPUT_CSV)
                vehicle.close()
                return

            ready, _, _ = select.select([sys.stdin], [], [], 0.5)
            if not ready:
                continue
            # space または Enter（空入力）= 着陸(yes)、それ以外 = 保留(no)
            answer = sys.stdin.readline().strip()
            if answer == "":
                break
            else:
                print("着陸を保留しています。着陸するときは space または Enter を入力してください。")
                print(landing_prompt, end="", flush=True)

        print("LANDモードに切り替えます。")
        vehicle.mode = VehicleMode("LAND")
        while vehicle.mode.name != "LAND":
            time.sleep(0.5)

        print("着陸中... ディスアームを待機します。")
        while vehicle.armed:
            time.sleep(1)
        print("ディスアームを確認しました。着陸完了です。")

    except TimeoutError as e:
        print("\nタイムアウトが発生しました: %s" % e)
        print("安全のためディスアームして終了します。")
        disarm_vehicle(vehicle)
        print("ディスアームして終了しました。CSVファイルは生成していません。")
        vehicle.close()
        return

    except KeyboardInterrupt:
        print("\n手動で中断されました。ここまでの結果を保存します。")

    # ---- 最終的な結果をCSVに保存（念のため再保存） ----
    save_csv(results)
    print("結果を %s に保存しました。" % OUTPUT_CSV)

    vehicle.close()


if __name__ == "__main__":
    main()