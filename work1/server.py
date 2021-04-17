import socket
import time
import json

# 加载参数
with open("setting.json", 'r') as f:
    param = json.load(f)
PORT = param["UDP_port"]
data_size = param["data_size"]
error_rate = param["error_rate"]
lost_rate = param["lost_rate"]
SW_size = param["SW_size"]
init_seq_no = param["init_seq_no"]
time_out = param["time_out"]

# 下面为绑定端口代码
server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
host = socket.gethostname()
address = (host, PORT)
server_socket.bind(address)
server_socket.settimeout(20)  # 设置监听最长时间为 20 s

# 设置接收端缓冲区
buffer_size = 20 # 接收端的缓冲区大小
buffer = ["" for _ in range(buffer_size)]

def inc(num, max_num):
    num = (num + 1) % max_num
    return num

while True:
    try:
        now = time.time()
        receive_data, client = server_socket.recvfrom(1024)
        print(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now)))
        print("来自客户端%s,发送的%s\n" % (client, receive_data))
    except socket.timeout:
        print("time out")
