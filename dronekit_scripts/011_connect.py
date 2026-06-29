import time
from dronekit import connect

<<<<<<< HEAD
#vehicle = connect('tcp:127.0.0.1:5762', wait_ready=True, timeout=60)
vehicle = connect('tcp:10.16.119.100:5762', wait_ready=True, timeout=60)
=======
# vehicle = connect('127.0.0.1:14551', wait_ready=True, timeout=60)
vehicle = connect('tcp:127.0.0.1:5762', wait_ready=True, timeout=60) #WSL

>>>>>>> 5c04340466acc5ad7c95bbb6936ffa83b46046d3

while True:
    print ("====================================")
    print ("home_location: %s" % vehicle.home_location )
    print ("heading: %s" % vehicle.heading )
    print ("gimbal: %s" % vehicle.gimbal )
    print ("airspeed: %s" % vehicle.airspeed )
    print ("groundspeed: %s" % vehicle.groundspeed )
    print ("mode: %s" % vehicle.mode )
    print ("armed: %s" % vehicle.armed )
    time.sleep(1)
