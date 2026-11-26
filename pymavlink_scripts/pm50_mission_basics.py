import sys
import time
from pymavlink import mavutil

def download_mission(master):
    mission = []

    # ミッションアイテムの数を取得
    master.mav.mission_request_list_send(
        master.target_system, master.target_component)
    count_msg = master.recv_match(type='MISSION_COUNT', blocking=True, timeout=5)
    if count_msg is None:
        print("MISSION_COUNT が届きません")
        sys.exit(1)
    mission_count = count_msg.count

    # ミッションアイテムをダウンロード
    for i in range(mission_count):
        master.mav.mission_request_int_send(
            master.target_system, master.target_component, i)
        item = master.recv_match(type='MISSION_ITEM_INT', blocking=True, timeout=5)
        if item is None:
            print(f"ミッションアイテム {i} が届きません")
            sys.exit(1)
        new_waypoint = mavutil.mavlink.MAVLink_mission_item_int_message(
            master.target_system,
            master.target_component,
            item.seq,
            item.frame,
            item.command,
            item.current,
            item.autocontinue,
            item.param1, item.param2, item.param3, item.param4,
            item.x, item.y, item.z,
        )
        mission.append(new_waypoint)

    # ダウンロードの完了を機体に伝える
    master.mav.mission_ack_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_MISSION_ACCEPTED)

    return mission


def add_waypoint(master, mission, lat, lon, alt):
    # 新しいウェイポイントを追加
    # ミッションが空でも、接続先の ID を使って最初のウェイポイントを作る
    new_waypoint = mavutil.mavlink.MAVLink_mission_item_int_message(
        master.target_system,
        master.target_component,
        len(mission),
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
        mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
        0, 0, 0, 0, 0, 0,
        int(lat * 1e7),
        int(lon * 1e7),
        int(alt)
    )
    mission.append(new_waypoint)


def upload_mission(master, mission):
    # ミッションアイテムの数を送る
    master.mav.mission_count_send(
        master.target_system, master.target_component, len(mission))

    # 機体が要求したアイテムを、1つずつ送る。全部届くと MISSION_ACK が返る
    end = time.time() + 10
    while time.time() < end:
        msg = master.recv_match(
            type=['MISSION_REQUEST_INT', 'MISSION_REQUEST', 'MISSION_ACK'],
            blocking=True, timeout=1)
        if msg is None:
            continue
        if msg.get_type() == 'MISSION_ACK':
            accepted = msg.type == mavutil.mavlink.MAV_MISSION_ACCEPTED
            if not accepted:
                result = mavutil.mavlink.enums['MAV_MISSION_RESULT'][msg.type].name
                print(f"ミッションが受理されませんでした: {result}")
            return accepted
        master.mav.send(mission[msg.seq])

    print("MISSION_ACK が届きません")
    return False


def print_mission(mission):
    for element in mission:
        print(element)


if __name__ == '__main__':
    # 機体への接続
    master: mavutil.mavfile = mavutil.mavlink_connection(
        "tcp:127.0.0.1:5762", source_system=1, source_component=90)
    master.wait_heartbeat()

    # ミッションのダウンロード
    downloaded_mission = download_mission(master)
    print("ミッションダウンロード完了")
    print_mission(downloaded_mission)

    # ウェイポイントの追加
    add_waypoint(master, downloaded_mission, lat=35.8792449, lon=140.3394654, alt=5)
    print("ミッションへのウェイポイント追加完了")
    print_mission(downloaded_mission)

    # ウェイポイントの追加
    add_waypoint(master, downloaded_mission, lat=35.879, lon=140.339, alt=5)
    print("ミッションへのウェイポイント追加完了")
    print_mission(downloaded_mission)

    # アップロード
    if upload_mission(master, downloaded_mission):
        print("ミッションアップロード完了")
    else:
        sys.exit(1)
