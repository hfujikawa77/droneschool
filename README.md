# droneschool
ドローンソフトウェアエンジニア養成塾用のサンプルコード

## dronekit-scripts
DroneKitスクリプトサンプル

## mp-scripts
Mission Planner用スクリプトサンプル

## pymavlink_scripts
Pymavlinkスクリプトサンプル

ーーーーーーーーーーーーーー
作業
11/19
 dronekit_scriptsを試す
 ■シンプル
sim_vehicle.py -v Copter -L Kawachi --map --console 
■ミニマム（MP前提）
sim_vehicle.py -v Copter -L Kawachi 
■Output
sim_vehicle.py -v Copter -L Kawachi --map --console --out=udp:127.0.0.1:14550 --out=udp:<PiのIP>:14550　

動くまで
・mode guided
・arm throttle
・takeoff 20
・(GUIで)Flyto　
