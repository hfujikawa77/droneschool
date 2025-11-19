from dronekit import connect
vehicle = connect('tcp:172.30.98.2:5762', wait_ready=True, timeout=60)
vehicle.wait_for_mode("AUTO")