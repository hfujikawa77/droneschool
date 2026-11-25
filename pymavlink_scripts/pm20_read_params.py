# Import mavutil
from pymavlink import mavutil

# Create the connection
master :mavutil.mavfile = mavutil.mavlink_connection(
    "tcp:127.0.0.1:5762", source_system=1, source_component=90)

# Wait a heartbeat before sending commands
master.wait_heartbeat()

# Request all parameters
master.mav.param_request_list_send(
    master.target_system, master.target_component
)
# 3秒間 PARAM_VALUE が届かなくなったら、全部受信したとみなして終了する
count = 0
while True:
    message = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
    if message is None:
        break
    count += 1
    print('name: %s\tvalue: %g' % (message.param_id, message.param_value))
print(f"{count} 個のパラメータを受信しました")
