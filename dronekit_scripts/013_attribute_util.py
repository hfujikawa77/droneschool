# import time
from dronekit import connect #, VehicleMode

# vehicle = connect('127.0.0.1:14551', wait_ready=True, timeout=60)
# vehicle = connect('tcp:127.0.0.1:5762', wait_ready=True, timeout=60)
vehicle = connect('tcp:172.30.98.2:5762', wait_ready=True, timeout=60)
# GUIDEDモード変更
# vehicle.mode = VehicleMode("GUIDED")
# vehicle.wait_for_mode("GUIDED")
vehicle.wait_for_mode("AUTO")

# アーム
# vehicle.armed = True
vehicle.arm()

# モードがGUIDEDになり、アーミングされるまで待つ
# while not vehicle.mode.name == 'GUIDED' and not vehicle.armed:
#     time.sleep(1)
