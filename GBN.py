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

# 下面的代码为将 socket 绑定到端口上
######################################################################

if len(sys.argv) > 1:  # 如果存在输入的端口号，就绑定到那个端口，如果没有输入参数，就使用默认的端口
    port = int(sys.argv[1])

server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
host_name = socket.gethostname()
host_name = socket.gethostbyname(host_name)
address = (host_name, port)
server_socket.bind(address)
server_socket.settimeout(120)  # 设置监听最长时间为 20 s
if not os.path.exists(str(address)):
    os.makedirs(str(address))

######################################################################


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


# 发送包的函数
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


# 下面为接收包的函数，通过创建一个线程监听发送到端口的包，然后将包消息发送到对应处理线程的消息队列中
###########################################################################


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

###########################################################################


# 下面函数实现的功能为接受用户的输入的发送端口和发送文件
###########################################################################
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

###########################################################################

thread = dict()  # 负责保存每一个端口交互的处理线程
del_thread = Queue()  # 负责删除处理线程

# 下面是处理线程，也是 udp 传输的核心部分，对于来自不同端口的包，用不同的处理线程处理
###########################################################################


class host(threading.Thread):
    def __init__(self, host_id):
        threading.Thread.__init__(self)
        self.host_id = host_id  # 线程处理的端口
        self.next_frame_to_send = init_seq_no  # GBN协议中的发送包序号
        self.frame_expected = init_seq_no  # GBN协议中对方接受包的序号
        self.ack_expected = init_seq_no  # GBN协议中接受对方包的序号
        self.recv_file_name = str(host_id) + '_to_' + str(address)  # 保存数据的文件名

        # 将之前运行的数据、日志文件删除
        ##################################################################
        if os.path.exists(self.recv_file_name):
            os.remove(self.recv_file_name)
        if os.path.exists(str(address) + "/" + "recvfrom_" + str(self.host_id)):
            os.remove(str(address) + "/" + "recvfrom_" + str(self.host_id))
        if os.path.exists(str(address) + "/" + "sendto_" + str(self.host_id)):
            os.remove(str(address) + "/" + "sendto_" + str(self.host_id))
        ##################################################################

        self.frame_timer = dict()  # 保存每一个帧计时器线程
        self.buffer = dict()  # 发送缓冲区
        self.buffer_cnt = 0  # 发送缓冲区计数
        self.time_out_cnt = 0  # 超时计数，如果超时次数过多，关闭线程
        self.send_file_handle = None  # 发送文件的指针

        # 对于文件发送开始和结束的标记，可以放到后面看
        ##################################################################
        self.is_sending = False
        self.is_send_start = False
        self.send_end_frame = None
        self.is_recving = False
        ##################################################################

        self.msg = Queue()  # 消息队列，用来保存发送、接收、超时消息
        self.time_lock = Queue(1) # TODO
        self.isDaemon = True  # 守护线程，为了防止主程序中途退出线程不能结束，可以不用管
        self.send_cnt = 0  # 发送序号，用于保存消息日志
        self.recv_cnt = 0  # 接受序号，用于保存消息日志
        self.lost_cnt = 0  # 丢包计数，当丢包到达 lost_rate 的时候就进行丢包处理
        self.ack = [False for _ in range(SW_size + 1)] # 判断帧是否受到了 ack ，防止计时器在收到ack后依然发送超时信号
        self.start() # 线程启动

    # 发送超时信号
    def send_time_out(self, frame_num):
        self.time_lock.put(0)
        if not self.ack[frame_num]:
            self.msg.put(("time_out", None))
        self.time_lock.get()

    # 设置计时器
    def start_timer(self, frame_num):
        self.stop_timer(frame_num)
        self.ack[frame_num] = False
        self.frame_timer[frame_num] = threading.Timer(time_out, self.send_time_out, (frame_num, ))
        self.frame_timer[frame_num].setDaemon(True)
        self.frame_timer[frame_num].start()

    # 受到 ack 包后，需要将对应的帧的计时器取消
    def stop_timer(self, frame_num):
        if frame_num not in self.frame_timer:
            return
        self.frame_timer[frame_num].cancel()

    # 处理消息队列中的消息,其实大致和书上的代码类似
    def wait_for_event(self):
        msg = self.msg.get()
        self.time_lock.put(0)

        if msg[0] == "recv_data":
            data = msg[1]
            seq_num, ack_num, file_state, info = from_physical_layer(data)

            # 下面为记录日志部分，可以先不看
            ##################################################################
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
            ##################################################################

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

            # 下面为记录日志部分，可以先不看
            ##################################################################
            with open(str(address) + "/" + "sendto_" + str(self.host_id), "a") as f:
                record = "pdu_to_send = " + str(self.send_cnt) + ' , '
                record += "staus = " + "NEW" + ' , '
                record += "ackedNo = " + str(self.ack_expected) + ' , '
                record += "a1 = " + str(next_frame_to_send) + ' , '
                record += "a2 = " + str((self.frame_expected + SW_size) % (SW_size + 1)) + '\n'
                f.writelines(record)
                self.send_cnt += 1
            ##################################################################

            # 这里发送部分和书上不一样，因为构造包的过程已经在另一个函数中处理了，所以这里只是单纯地发送包
            send_data(next_frame_to_send, self.frame_expected, self.buffer[next_frame_to_send][0], self.buffer[next_frame_to_send][1], self.host_id)

        elif msg[0] == "time_out":
            if self.time_out_cnt < 10:
                self.time_out_cnt = self.time_out_cnt + 1
                frame_index = self.ack_expected
                for _ in range(self.buffer_cnt):

                    # 下面为记录日志部分，可以先不看
                    ##################################################################
                    with open(str(address) + "/" + "sendto_" + str(self.host_id), "a") as f:
                        record = "pdu_to_cnt = " + str(self.send_cnt) + ' , '
                        record += "staus = " + "TO" + ' , '
                        record += "ackedNo = " + str(self.ack_expected) + ' , '
                        record += "a1 = " + str(frame_index) + ' , '
                        record += "a2 = " + str((self.frame_expected + SW_size) % (SW_size + 1)) + '\n'
                        f.writelines(record)
                        self.send_cnt += 1
                    ##################################################################

                    send_data(frame_index, self.frame_expected, self.buffer[frame_index][0], self.buffer[frame_index][1], self.host_id)
                    frame_index = inc(frame_index)
                self.next_frame_to_send = frame_index

        self.time_lock.get()

    # 创建发送包
    def create_send_data(self):
        if (self.buffer_cnt < SW_size):

            # 如果需要向对放端口发送文件，就进行捎带确认
            buffer_index = self.next_frame_to_send
            if self.send_file_handle != None:
                if not self.is_send_start:
                    # 如果是刚刚开始发送文件，需要发送一个特殊的包告诉对方开始传送数据
                    self.is_send_start = True
                    self.buffer[buffer_index] = (0, b'')
                    self.msg.put(("send_data", buffer_index))
                else:
                    data = self.send_file_handle.read(data_size)
                    if data:
                        # 传送数据
                        self.buffer[buffer_index] = (1, data)
                        self.msg.put(("send_data", buffer_index))
                    else:
                        # 如果读到文件末尾，需要发送一个特殊的包告诉对方传送结束
                        self.send_file_handle.close()
                        self.send_file_handle = None
                        self.send_end_frame = buffer_index

                        self.buffer[buffer_index] = (2, b'')
                        self.msg.put(("send_data", buffer_index))

            # 如果没有向对方端口发送文件的需求，就只发送 ack 确认包
            else:
                self.buffer[buffer_index] = (1, b'')
                self.msg.put(("send_data", buffer_index))

            self.next_frame_to_send = inc(self.next_frame_to_send)
            self.buffer_cnt += 1

    # 可以不用管
    def __del__(self):
        if self.send_file_handle != None:
            self.send_file_handle.close()
        for x in self.frame_timer.values():
            x.cancel()

    # 线程运行的主函数，通过消息队列阻塞，每次循环通过创建一个发送包保持端口的活性
    def run(self):
        while True:
            self.wait_for_event()
            self.create_send_data()
            if (not self.is_recving and not self.is_sending) or self.time_out_cnt == 10:
                break
        print("thread end!")
        del_thread.put(self.host_id)


###########################################################################

# 运行的主线程，通过删除队列阻塞
###########################################################################

while True:
    try:
        thread_id = del_thread.get()
        temp = thread.pop(thread_id)
        del temp
    except socket.timeout:
        print("Time out")

###########################################################################
