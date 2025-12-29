from pymavlink import mavutil
import time

#機体への接続
master: mavutil.mavfile = mavutil.mavlink_connection(
    "127.0.0.1:14551", source_system=1, source_component=90)
master.wait_heartbeat()

#モードARMED
master.arducopter_arm()
master.motors_armed_wait()
print("ARMED")

time.sleep(5)

#モードDISARMED
master.arducopter_arm()
master.motors_disarmed_wait()
print("DISARMED")