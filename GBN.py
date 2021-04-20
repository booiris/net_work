import socket
import time
import json
import sys
import threading
from queue import Queue
import os

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
if not os.path.exists(str(address)):
    os.makedirs(str(address))


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


def check_data(data):
    return True


def send_data(frame_num, frame_expected, file_state, info, client_address):
    data = b""
    data += chr(frame_num).encode()
    data += chr((frame_expected + SW_size) % (SW_size + 1)).encode()
    data += chr(file_state).encode()
    data += info
    print("send:", data)
    if thread[client_address].lost_cnt != lost_rate:
        thread[client_address].lost_cnt += 1
        server_socket.sendto(data, client_address)
    else:
        thread[client_address].lost_cnt = 0
    thread[client_address].start_timer(frame_num)


def recv_data_thread():
    while True:
        receive_data, client = server_socket.recvfrom(data_size + 5)
        print("receive:", receive_data)
        file_state = int(receive_data[2])
        if client not in thread:
            if file_state != 0:
                return
            else:
                thread[client] = host(client)
        thread[client].msg.put(("recv_data", receive_data))


recv_thread = threading.Thread(target=recv_data_thread)
recv_thread.setDaemon(True)
recv_thread.start()


def send_data_thread():
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
        if send_to_address not in thread:
            thread[send_to_address] = host(send_to_address)

        if thread[send_to_address].send_file_handle != None:
            thread[send_to_address].send_file_handle.close()
        thread[send_to_address].is_sending = True
        thread[send_to_address].is_send_start = False
        thread[send_to_address].send_end_frame = None
        thread[send_to_address].send_file_handle = open(send_file_name, "rb")
        thread[send_to_address].msg.put(("sending_file"))


input_thread = threading.Thread(target=send_data_thread)
input_thread.setDaemon(True)
input_thread.start()

thread = dict()
del_thread = Queue()


class host(threading.Thread):
    def __init__(self, host_id):
        threading.Thread.__init__(self)
        self.host_id = host_id
        self.next_frame_to_send = init_seq_no
        self.frame_expected = init_seq_no
        self.ack_expected = init_seq_no
        self.recv_file_name = str(host_id) + '_to_' + str(address)
        if os.path.exists(self.recv_file_name):
            os.remove(self.recv_file_name)
        if os.path.exists(str(address) + "/" + "recvfrom_" + str(self.host_id)):
            os.remove(str(address) + "/" + "recvfrom_" + str(self.host_id))
        if os.path.exists(str(address) + "/" + "sendto_" + str(self.host_id)):
            os.remove(str(address) + "/" + "sendto_" + str(self.host_id))
        self.frame_timer = dict()
        self.buffer = dict()
        self.buffer_cnt = 0
        self.time_out_cnt = 0
        self.send_file_handle = None
        self.is_sending = False
        self.is_send_start = False
        self.send_end_frame = None
        self.is_recving = False
        self.msg = Queue()
        self.send_lock = Queue(1)
        self.isDaemon = True
        self.start()
        self.send_cnt = 0
        self.recv_cnt = 0
        self.lost_cnt = 0
        self.ack = [False for _ in range(SW_size + 1)]

    def send_time_out(self, frame_num):
        self.send_lock.put(0)
        if not self.ack[frame_num]:
            self.msg.put(("time_out", 0))
        self.send_lock.get()

    def start_timer(self, frame_num):
        self.stop_timer(frame_num)
        self.ack[frame_num] = False
        self.frame_timer[frame_num] = threading.Timer(time_out, self.send_time_out, (frame_num, ))
        self.frame_timer[frame_num].setDaemon(True)
        self.frame_timer[frame_num].start()

    def stop_timer(self, frame_num):
        if frame_num not in self.frame_timer:
            return
        self.frame_timer[frame_num].cancel()

    def wait_for_event(self):
        msg = self.msg.get()
        self.send_lock.put(0)
        if msg[0] == "recv_data":
            data = msg[1]
            seq_num, ack_num, file_state, info = from_physical_layer(data)

            status = "OK"
            if seq_num != self.frame_expected:
                status = "NumErr"
            if not check_data(data):
                status = "DataErr"

            with open(str(address) + "/" + "recvfrom_" + str(self.host_id), "a") as f:
                record = "pdu_recv = " + str(self.recv_cnt) + ' , '
                record += "staus = " + status + ' , '
                record += "pdu_exp = " + str(self.frame_expected) + ' , '
                record += "a1 = " + str(seq_num) + ' , '
                record += "a2 = " + str(ack_num) + '\n'
                f.writelines(record)
                self.recv_cnt += 1

            if seq_num == self.frame_expected:
                if file_state == 0:
                    self.is_recving = True
                elif file_state == 2:
                    print("receive end!")
                    self.is_recving = False
                self.time_out_cnt = 0
                self.frame_expected = inc(self.frame_expected)
                if info:
                    with open(self.recv_file_name, "ab") as f:
                        f.write(info)

                while between(self.ack_expected, ack_num, self.next_frame_to_send):
                    self.stop_timer(self.ack_expected)
                    self.ack[self.ack_expected] = True
                    self.buffer_cnt = self.buffer_cnt - 1
                    self.buffer.pop(self.ack_expected)
                    self.ack_expected = inc(self.ack_expected)

                if self.send_end_frame != None and self.ack_expected == self.send_end_frame:
                    self.is_sending = False

        elif msg[0] == "send_data":
            next_frame_to_send = msg[1]
            if self.buffer[next_frame_to_send] == 2:
                self.is_sending = False

            with open(str(address) + "/" + "sendto_" + str(self.host_id), "a") as f:
                record = "pdu_to_send = " + str(self.send_cnt) + ' , '
                record += "staus = " + "NEW" + ' , '
                record += "ackedNo = " + str(self.ack_expected) + ' , '
                record += "a1 = " + str(next_frame_to_send) + ' , '
                record += "a2 = " + str((self.frame_expected + SW_size) % (SW_size + 1)) + '\n'
                f.writelines(record)
                self.send_cnt += 1

            send_data(next_frame_to_send, self.frame_expected, self.buffer[next_frame_to_send][0], self.buffer[next_frame_to_send][1], self.host_id)

        elif msg[0] == "time_out":
            if self.time_out_cnt < 10:
                self.time_out_cnt = self.time_out_cnt + 1
                frame_index = self.ack_expected
                for _ in range(self.buffer_cnt):

                    with open(str(address) + "/" + "sendto_" + str(self.host_id), "a") as f:
                        record = "pdu_to_cnt = " + str(self.send_cnt) + ' , '
                        record += "staus = " + "TO" + ' , '
                        record += "ackedNo = " + str(self.ack_expected) + ' , '
                        record += "a1 = " + str(frame_index) + ' , '
                        record += "a2 = " + str((self.frame_expected + SW_size) % (SW_size + 1)) + '\n'
                        f.writelines(record)
                        self.send_cnt += 1

                    send_data(frame_index, self.frame_expected, self.buffer[frame_index][0], self.buffer[frame_index][1], self.host_id)
                    frame_index = inc(frame_index)
                self.next_frame_to_send = frame_index

        self.send_lock.get()

    def create_send_data(self):
        if (self.buffer_cnt < SW_size):
            buffer_index = self.next_frame_to_send
            if self.send_file_handle != None:
                if not self.is_send_start:
                    self.is_send_start = True
                    self.buffer[buffer_index] = (0, b'')
                    self.msg.put(("send_data", buffer_index))
                else:
                    data = self.send_file_handle.read(data_size)
                    if data:
                        self.buffer[buffer_index] = (1, data)
                        self.msg.put(("send_data", buffer_index))
                    else:
                        self.send_file_handle.close()
                        self.send_file_handle = None
                        self.send_end_frame = buffer_index

                        self.buffer[buffer_index] = (2, b'')
                        self.msg.put(("send_data", buffer_index))

            else:
                self.buffer[buffer_index] = (1, b'')
                self.msg.put(("send_data", buffer_index))

            self.next_frame_to_send = inc(self.next_frame_to_send)
            self.buffer_cnt += 1

    def __del__(self):
        if self.send_file_handle != None:
            self.send_file_handle.close()
        for x in self.frame_timer.values():
            x.cancel()

    def run(self):
        while True:
            self.wait_for_event()
            self.create_send_data()
            if (not self.is_recving and not self.is_sending) or self.time_out_cnt == 10:
                break
        print("thread end!")
        del_thread.put(self.host_id)


while True:
    try:
        thread_id = del_thread.get()
        temp = thread.pop(thread_id)
        del temp
    except socket.timeout:
        print("Time out")
