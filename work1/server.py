import socket
import time
import json
import sys

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
host_name = socket.gethostname()
address = (host_name, PORT)
server_socket.bind(address)
server_socket.settimeout(10)  # 设置监听最长时间为 20 s


class host_state:
    def __init__(self):
        self.next_frame_to_send = 0
        self.frame_expected = 1
        self.file_handle = None


# 设置发送缓冲区
buffer = ["" for _ in range(SW_size)]
file_cnt = 0
host = dict()


def to_network_layer(data):
    seq_num = data[0]
    ack_num = data[1]
    info = data[2:]
    return seq_num, ack_num, info


def send_ack_data(seq_num, ack_num, to_address):
    data = ""
    data += str(seq_num)
    data += str(ack_num)
    server_socket.sendto(data, to_address)


while True:
    try:
        receive_data, client = server_socket.recvfrom(data_size + 5)
        if client not in host:
            host[client] = host_state()
            host[client].file_handle = open(host_name + ':' + str(PORT) + '_' + str(file_cnt) + '.txt', "wb")
            file_cnt = file_cnt + 1

        seq_num, ack_num, info = to_network_layer(receive_data)
        if seq_num + 1 == host[client].frame_expected:
            host[client].file_handle.write(info)
            if seq_num + 1 == ack_num:
                send_ack_data(host[client].next_frame_to_send, ack_num % SW_size, client)
                host[client].next_frame_to_send = (host[client].next_frame_to_send + 1) % SW_size
            host[client].frame_expected = (host[client].frame_expected + 1) % (SW_size + 1)

    except socket.timeout:
        print("time out")

for x in host:
    x.file_handle.close()
