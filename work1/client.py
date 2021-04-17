import socket
import time
import json
import random

with open("setting.json", 'r') as f:
    param = json.load(f)
PORT = param["UDP_port"]
data_size = param["data_size"]
error_rate = param["error_rate"]
lost_rate = param["lost_rate"]
SW_size = param["SW_size"]
init_seq_no = param["init_seq_no"]
time_out = param["time_out"]


client_port = random.randint(10000,20000)
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
host = socket.gethostname()
address = (host, client_port)
client_socket.bind(address)
client_socket.settimeout(10)  # 设置监听最长时间为 20 s
server_address = (host, PORT)

while True:
    start = time.time()
    msg = b"asdssssss"
    
    client_socket.sendto(msg, server_address)
    now = time.time()
    run_time = now - start
    print(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now)))
    print("run_time: %d seconds\n" % run_time)
    time.sleep(5)
