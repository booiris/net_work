import socket
import time
import json
import sys
import threading
from queue import Queue
import os

# 加载参数
with open("setting.json", 'r') as f:
    param = json.load(f)
port = param["UDP_port"]
data_size = param["data_size"]
error_rate = param["error_rate"]
lost_rate = param["lost_rate"]
SW_size = param["SW_size"]
init_seq_no = param["init_seq_no"]
time_out = param["time_out"] / 1000

if len(sys.argv) > 1:
    port = int(sys.argv[1])

# 下面为绑定端口代码
server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
host_name = socket.gethostname()
host_name = socket.gethostbyname(host_name)
address = (host_name, port)
server_socket.bind(address)
server_socket.settimeout(120)  # 设置监听最长时间为 20 s

# 设置发送缓冲区
buffer = [b'' for _ in range(SW_size + 1)]
buffer_state = [1 for _ in range(SW_size + 1)]
host_state = dict()
thread_msg = Queue()
send_lock = Queue(1)
send_msg_lock = Queue(1)
send_buffer_index = dict()
timer_list = dict()
buffer_cnt = Queue(SW_size)
for i in range(SW_size):
    buffer_cnt.put(i)


class state:
    def __init__(self):
        self.next_frame_to_send = init_seq_no
        self.frame_expected = init_seq_no
        self.ack_expected = init_seq_no
        self.recv_file_name = ""
        # 对于不同的主机，每一个帧下标对应一个计时器线程和缓冲区位置
        self.frame_index_timer = dict()
        self.frame_index_buffer = dict()
        self.time_out_cnt = 0
        self.send_file_handle = None
        self.is_end = False
        self.is_start = True


def inc(num):
    return (num + 1) % (SW_size + 1)


def between(a, b, c):
    if ((a <= b) and (b < c)) or ((c < a) and (a <= b)) or ((b < c) and (c < a)):
        return True
    else:
        return False


def from_physical_layer(data):
    seq_num = int(data[0])
    ack_num = int(data[1])
    file_state = int(data[2])
    info = data[3:]
    return seq_num, ack_num, file_state, info


def recv_data():
    while True:
        receive_data, client = server_socket.recvfrom(data_size + 5)
        # print("receive:", receive_data)
        check_data(receive_data)
        thread_msg.put(("recv_data", receive_data, client))


recv_thread = threading.Thread(target=recv_data)
recv_thread.setDaemon(True)
recv_thread.start()


def send_time_out(client):
    thread_msg.put(("time_out", client))


def start_timer(client, frame_num):
    stop_timer(client, frame_num)
    timer = threading.Timer(time_out, send_time_out, args=(client, ))
    timer.setDaemon(True)
    host_state[client].frame_index_timer[frame_num] = timer
    timer.start()


def stop_timer(client, frame_num):
    if frame_num not in host_state[client].frame_index_timer:
        return
    timer = host_state[client].frame_index_timer[frame_num]
    timer.cancel()


def send_data(frame_num, frame_expected, file_state, info, client_address):
    data = b""
    data += chr(frame_num).encode()
    data += chr((frame_expected + SW_size) % (SW_size + 1)).encode()
    data += chr(file_state).encode()
    data += info
    # print("send:", data)
    server_socket.sendto(data, client_address)
    start_timer(client_address, frame_num)


def check_data(data):
    pass


def send_part():
    while True:
        print("当前端口为", address)
        send_to_address = input("发送端口")
        send_to_address = send_to_address.strip()
        send_to_address = send_to_address.rstrip(')')
        send_to_address = send_to_address.lstrip('(')
        send_to_address = send_to_address.split(',')
        send_to_address[0] = send_to_address[0].strip("'")
        send_to_address = (send_to_address[0], int(send_to_address[1]))

        send_file_name = input("文件地址")
        send_lock.put(0)
        send_msg_lock.put(0)
        if send_to_address not in host_state:
            host_state[send_to_address] = state()
            host_state[send_to_address].recv_file_name = str(address) + '_to_' + str(send_to_address)
            if os.path.exists(host_state[send_to_address].recv_file_name):
                os.remove(host_state[send_to_address].recv_file_name)
        if host_state[send_to_address].send_file_handle != None:
            host_state[send_to_address].send_file_handle.close()
        host_state[send_to_address].is_end = False
        host_state[send_to_address].is_start = True
        host_state[send_to_address].send_file_handle = open(send_file_name, "rb")
        send_msg_lock.get()
        send_lock.get()


input_thread = threading.Thread(target=send_part)
input_thread.setDaemon(True)
input_thread.start()


def send_msg():
    while True:
        send_msg_lock.put(0)
        buffer_index = buffer_cnt.get()
        flag = False
        for key, x in host_state.items():
            if x.send_file_handle != None and (not x.is_end):
                flag = True
                if x.is_start:
                    buffer[buffer_index] = b''
                    buffer_state[buffer_index] = 0
                    host_state[key].is_start = False
                    thread_msg.put(("send_msg", key, buffer_index))
                else:
                    buffer[buffer_index] = x.send_file_handle.read(data_size)
                    if not buffer[buffer_index]:
                        host_state[key].send_file_handle.close()
                        host_state[key].send_file_handle = None
                        buffer_state[buffer_index] = 2
                        print("send end")
                        thread_msg.put(("send_msg", key, buffer_index))
                    else:
                        buffer_state[buffer_index] = 1
                        thread_msg.put(("send_msg", key, buffer_index))
                break
        # TODO 改良空ack的发送时机
        if not flag:
            for key, x in host_state.items():
                if x.time_out_cnt < 5 and (not x.is_end):
                    flag = True
                    buffer[buffer_index] = b''
                    thread_msg.put(("send_msg", key, buffer_index))
                    break
        if not flag:
            buffer_cnt.put(buffer_index)
        send_msg_lock.get()


send_thread = threading.Thread(target=send_msg)
send_thread.setDaemon(True)
send_thread.start()


def delet_host(client):
    pass


def wait_for_event():
    global host_state, buffer_cnt
    msg = thread_msg.get()
    send_lock.put(0)
    if msg[0] == "recv_data":
        data = msg[1]
        client = msg[2]
        if client not in host_state:
            host_state[client] = state()
            host_state[client].recv_file_name = str(address) + '_to_' + str(client)
            if os.path.exists(host_state[client].recv_file_name):
                os.remove(host_state[client].recv_file_name)

        seq_num, ack_num, file_state, info = from_physical_layer(data)
        if seq_num == host_state[client].frame_expected:
            host_state[client].time_out_cnt = 0
            host_state[client].frame_expected = inc(host_state[client].frame_expected)
            if info:
                f = open(host_state[client].recv_file_name, "ab")
                f.write(info)  # to_network_layer，就是保存数据
                f.close

            if file_state == 2:
                host_state[client].is_end = True
            elif file_state == 0:
                host_state[client].is_end = False

            while between(host_state[client].ack_expected, ack_num, host_state[client].next_frame_to_send):
                stop_timer(client, host_state[client].ack_expected)
                buffer_cnt.put(host_state[client].frame_index_buffer[host_state[client].ack_expected])
                host_state[client].frame_index_buffer.pop(host_state[client].ack_expected)
                host_state[client].ack_expected = inc(host_state[client].ack_expected)

    elif msg[0] == "time_out":
        client = msg[1]
        if host_state[client].time_out_cnt < 5:
            host_state[client].time_out_cnt = host_state[client].time_out_cnt + 1
            frame_index = host_state[client].ack_expected
            for x in host_state[client].frame_index_buffer.values():
                send_data(frame_index, host_state[client].frame_expected, buffer_state[x], buffer[x], client)
                frame_index = inc(frame_index)
            host_state[client].next_frame_to_send = frame_index

    elif msg[0] == "send_msg":
        client = msg[1]
        buffer_index = msg[2]
        host_state[client].frame_index_buffer[host_state[client].next_frame_to_send] = buffer_index
        send_data(host_state[client].next_frame_to_send, host_state[client].frame_expected, buffer_state[buffer_index], buffer[buffer_index], client)
        host_state[client].next_frame_to_send = inc(host_state[client].next_frame_to_send)

    send_lock.get()


while True:
    try:
        wait_for_event()
    except socket.timeout:
        for x in host_state.values():
            for i in x.frame_index_timer:
                i.cancel()
        print("time out")