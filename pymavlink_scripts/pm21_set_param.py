import sys
import time
from pymavlink import mavutil

# 機体への接続
master: mavutil.mavfile = mavutil.mavlink_connection(
    "tcp:127.0.0.1:5762", source_system=1, source_component=90)
master.wait_heartbeat()

print(
    "Heartbeat from system (system %u component %u)"
    % (master.target_system, master.target_component)
)

def wait_param(param_id, timeout=5):
    """PARAM_VALUE を待つ。timeout 秒以内に届かなければ None を返す"""
    end = time.time() + timeout
    while time.time() < end:
        message = master.recv_match(type="PARAM_VALUE", blocking=True, timeout=1)
        if message is not None and message.param_id == param_id:
            return message.to_dict()
    return None


def read_param(param_id):
    """パラメータの現在値を要求して待つ。見つからなければ None を返す"""
    master.mav.param_request_read_send(
        master.target_system, master.target_component, param_id.encode("ascii"), -1
    )
    return wait_param(param_id)


# RTL の高度パラメータは、ArduPilot の版で名前と単位が違う
# 新しい版: RTL_ALT_M（単位 m）、古い版: RTL_ALT（単位 cm）
# まず RTL_ALT_M を試し、なければ RTL_ALT に切り替える
param_id = "RTL_ALT_M"
delta = 2.0  # 増やす量（m）
param_type = mavutil.mavlink.MAV_PARAM_TYPE_REAL32  # Assuming RTL_ALT_M is of type REAL32

message = read_param(param_id)
if message is None:
    param_id = "RTL_ALT"
    delta = 200.0  # 増やす量（cm）
    message = read_param(param_id)
if message is None:
    # パラメータ名は機体種別ごとに違う（例: Rover にはどちらのパラメータもない）
    print(f"{param_id} が見つかりません。この機体にないパラメータの可能性があります")
    sys.exit(1)
current_value = message["param_value"]
print(f"Current value of {param_id}: {current_value}")

# Define the new value for the parameter
# 実行のたびに増え、SITL の eeprom.bin に残る
# 元に戻すには、SITL を -w 付きで起動し直すか、current_value に書き戻す
new_value = current_value + delta

# Send a request to set the parameter
master.mav.param_set_send(
    master.target_system, master.target_component,
    param_id.encode("ascii"), new_value, param_type,
)

# Wait for the ACK of the set parameter request
message = wait_param(param_id)
if message is None:
    print(f"{param_id} の設定結果が届きませんでした")
    sys.exit(1)
print(f"Parameter {param_id} set to {message['param_value']}")

# Request the updated value of the parameter
master.mav.param_request_read_send(
    master.target_system, master.target_component, param_id.encode("ascii"), -1
)

# Wait for the updated value of the parameter
message = wait_param(param_id)
if message is None:
    print(f"{param_id} の更新後の値が届きませんでした")
    sys.exit(1)
updated_value = message["param_value"]
print(f"Updated value of {param_id}: {updated_value}")

# Close the connection
master.close()
