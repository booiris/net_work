import socket
import time
import json
import sys
import threading
from queue import Queue

# 加载参数
with open("setting.json", 'r') as f:
    param = json.load(f)
port = param["UDP_port"]
data_size = param["data_size"]
error_rate = param["error_rate"]
lost_rate = param["lost_rate"]
SW_size = param["SW_size"]
init_seq_no = param["init_seq_no"]
time_out = param["time_out"]

if len(sys.argv) > 1:
    port = int(sys.argv[1])
print(port)

# 下面为绑定端口代码
server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
host_name = socket.gethostname()
address = (host_name, port)
server_socket.bind(address)
server_socket.settimeout(10)  # 设置监听最长时间为 20 s

# 设置发送缓冲区
buffer = ["" for _ in range(SW_size + 1)]
file_cnt = 0
recv_state = dict()
ack_cnt = 0
thread_msg = Queue()
buffer_cnt = Queue(SW_size + 1)
send_buffer_index = dict()
timer_list = dict()


class host_state:
    def __init__(self):
        self.next_frame_to_send = init_seq_no
        self.frame_expected = init_seq_no
        self.ack_expected = init_seq_no
        self.file_name = ""
        # 对于不同的主机，每一个帧下标对应一个计时器线程和缓冲区位置
        self.frame_index_timer = dict()
        self.frame_index_buffer = dict()


def inc(num):
    return (num + 1) % (SW_size + 1)


def between(a, b, c):
    if ((a <= b) and (b < c)) or ((c < a) and (a <= b)) or ((b < c) and (c < a)):
        return True
    else:
        return False


def from_physical_layer(data):
    seq_num = data[0]
    ack_num = data[1]
    info = data[2:]
    return seq_num, ack_num, info


def recv_data():
    while True:
        receive_data, client = server_socket.recvfrom(data_size + 5)
        check_data(receive_data)
        thread_msg.put(("recv_data", receive_data, client))


recv_thread = threading.Thread(target=recv_data)
recv_thread.setDaemon(True)
recv_thread.start()


def send_time_out(client):
    thread_msg.put(("time_out", client))


def start_timer(client, frame_num):
    stop_timer(client, frame_num)
    timer = threading.Timer(time_out, send_time_out, client)
    recv_state[client].frame_index_timer[frame_num] = timer
    timer.start()


def stop_timer(client, frame_num):
    if frame_num not in recv_state[client].frame_index_timer:
        return
    timer = recv_state[client].frame_index_timer[frame_num]
    timer.cancel()


def send_data(frame_num, frame_expected, buffer, client_address):
    data = ""
    data += frame_num
    data += (frame_expected + SW_size) % (SW_size + 1)
    server_socket.sendto(data, client_address)
    start_timer(client_address, frame_num)


def check_data(data):
    pass


def send_msg():
    while True:
        buffer_index = buffer_cnt.get()
        client = 0
        for x in recv_state:
            pass
        thread_msg.put(("send_msg", client, buffer_index))


def wait_for_event():
    global file_cnt, recv_state, buffer_cnt
    msg = thread_msg.get()
    if msg[0] == "recv_data":
        data = msg[1]
        client = msg[2]
        if client not in recv_state:
            recv_state[client] = host_state()
            recv_state[client].file_name = host_name + ':' + str(port) + '_' + str(file_cnt)
            f = open(recv_state[client].file_name, "wb")
            f.close
            file_cnt = file_cnt + 1

        seq_num, ack_num, info = from_physical_layer(data)
        if seq_num == recv_state[client].frame_expected:
            recv_state[client].frame_expected = inc(recv_state[client].frame_expected)
            f = open(recv_state[client].file_name, "ab")
            f.write(info)  # to_network_layer，就是保存数据
            f.close

        while between(recv_state[client].ack_expected, ack_num, recv_state[client].next_frame_to_send):
            stop_timer(client, recv_state[client].ack_expected)
            buffer_cnt.put(recv_state[client].frame_index_buffer)
            recv_state[client].ack_expected = inc(recv_state[client].ack_expected)

    elif msg[0] == "time_out":
        client = msg[1]
        frame_index = recv_state[client].ack_expected
        for x in recv_state[client].frame_index_buffer:
            send_data(frame_index, recv_state[client].frame_expected, buffer[x], client)
            frame_index = inc(frame_index)
        recv_state[client].next_frame_to_send = frame_index

    elif msg[0] == "send_msg":
        client = msg[1]
        buffer_index = msg[2]
        if client not in recv_state:
            recv_state[client] = host_state()
            recv_state[client].file_name = host_name + ':' + str(port) + '_' + str(file_cnt)
            f = open(recv_state[client].file_name, "wb")
            f.close
            file_cnt = file_cnt + 1
        send_data(recv_state[client].next_frame_to_send, recv_state[client].frame_expected, buffer[buffer_index], client)
        recv_state[client].next_frame_to_send = inc(recv_state[client].next_frame_to_send)


def send_part():
    while True:
        print("当前端口为%s", address)
        send_to_address = input("发送端口")
        send_file_name = input("文件地址")


send_thread = threading.Thread(target=send_part)
send_thread.setDaemon(True)
send_thread.start()

while True:
    try:
        wait_for_event()
    except socket.timeout:
        print("time out")