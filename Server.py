import socket
import time
import struct
import threading
from scapy.arch import get_if_addr

TIMEOUT = 10
BUFFER_SIZE = 2048


class Server:

    def __init__(self, name):

        self.name = name
        self.port_number = 2049
        self.server_ip = get_if_addr('eth1')
        self.udp_port = 13117
        self.server_socket = None
        self.group1 = []  # contains list of - group_name, connection_socket, client_address, key_counter
        self.group2 = []
        self.min_score = 0
        self.max_score = 0
        self.best_team_ever = []

        # variable used to count total time passed since the beginning of the game
        self.begin = None

    def start_server(self):
        """
            this function's responsibility is to change the modes of the server,
            waiting for client - that sends udp broadcast messages and connect to client via tcp
            game mode - this mode's responsibility is to receive the keys from the client calculate and
                        print the winner message
        """
        print("Server started, listening on {IP} address".format(IP=self.server_ip))
        while True:
            self.waiting_for_clients()
            if self.server_socket:
                print("Entering game mode")
                self.game_mode(self.server_socket)
            print("Game over, sending out offer requests...")

    def waiting_for_clients(self):
        """
            this function simultaneously sends udp broadcasts offers and accept tcp messages
        """

        # broadcasting with UDP
        udp_thread = threading.Thread(target=self.broadcast_offer, args=())
        udp_thread.start()

        # receiving tcp connection
        tcp_thread = threading.Thread(target=self.accept_tcp, args=())
        tcp_thread.start()

        udp_thread.join()
        tcp_thread.join()

    def broadcast_offer(self):
        """
            broadcast udp offers every second for 10 seconds
        """

        self.begin = time.time()
        broadcast_ip = '<broadcast>'
        try:
            sock = socket.socket(socket.AF_INET,  # Internet
                                 socket.SOCK_DGRAM)  # UDP
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except socket.error:
            return

        if sock:
            magic_cookie = 0xfeedbeef
            message_type = 0x2

            message = struct.pack("Ibh", magic_cookie, message_type, self.port_number)

            i = 0
            while i < TIMEOUT:
                sock.sendto(message, (broadcast_ip, self.udp_port))
                time.sleep(1)  # putting the current thread to sleep
                i += 1

            sock.close()

    def accept_tcp(self):
        """
            accept tcp offers and open a separate thread for every client to start playing the game
            then send welcoming message to each group
        """
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except socket.error:
            return
        self.server_socket.bind((self.server_ip, self.port_number))
        self.server_socket.listen(5)

        group_number = 0
        elapsed = 0
        threads = []
        while elapsed < TIMEOUT:  # while elapsed time is under 10 seconds keep assigning to groups

            self.server_socket.settimeout(TIMEOUT)
            try:
                connection_socket, address = self.server_socket.accept()
            except socket.error:
                elapsed = time.time() - self.begin
                continue

            connection_thread = threading.Thread(target=self.connect_to_client,
                                                 args=(connection_socket, address, group_number,))
            connection_thread.start()
            threads.insert(0, connection_thread)
            group_number = (group_number + 1) % 2

            elapsed = time.time() - self.begin

        for t in threads:
            t.join()

        welcoming_message = "Welcome to Keyboard Spamming Battle Royale.\nGroup 1:\n==\n"
        for i in range(len(self.group1)):
            welcoming_message += self.group1[i][0] + "\n"  # add the name of each group
        welcoming_message += "\nGroup 2:\n==\n"
        for i in range(len(self.group2)):
            welcoming_message += self.group2[i][0] + "\n"  # add the name of each group
        welcoming_message += "\nStart pressing keys on your keyboard as fast as you can!!\n"

        for player in self.group1:
            conn = player[1]
            conn.sendall(welcoming_message.encode())

        for player in self.group2:
            conn = player[1]
            conn.sendall(welcoming_message.encode())

    def connect_to_client(self, connection_socket, client_address, group_number):
        """
            this function receives the socket of the tcp connection and waits for the group to send it's name
            assign every client to a group
        :param connection_socket: the tcp socket between sever and each client
        :param client_address: (client ip, port)
        :param group_number: the number of the group client is assigned to
        """

        # receive the name of the team
        total_data = []
        while True:
            timeout = TIMEOUT - (time.time() - self.begin)
            if timeout < 0:
                break
            connection_socket.settimeout(timeout)
            try:
                data = connection_socket.recv(BUFFER_SIZE)
                if data:
                    total_data.append(data.decode())
            except socket.error:
                break

        # join all parts to make final string
        group_name = ''.join(total_data)  # receive the name of the group from tcp client

        if group_number == 0 and len(group_name) > 0 and group_name[-1:] == '\n':
            self.group1.insert(0, [group_name[:-1], connection_socket, client_address, 0])

        elif group_number == 1 and len(group_name) > 0 and group_name[-1:] == '\n':
            self.group2.insert(0, [group_name[:-1], connection_socket, client_address, 0])

        else:
            # the name received isn't correct
            print("the group name received isn't correct" + group_name)
            connection_socket.close()

    def game_mode(self, server_socket):
        """
            this function creates threads for players in both groups to collect keys from
            then calculate the winner and print and send appropriate end of the game messages to each client
        :return:
        :rtype:
        """

        if len(self.group1) == 0 and len(self.group2) == 0:
            print("no players connected")
            self.server_socket.close()
            return
        self.begin = time.time()
        threads = []
        elapsed = 0
        while elapsed < TIMEOUT:

            for player in self.group1:
                connection_thread = threading.Thread(target=self.receive_keys, args=(player,))
                connection_thread.start()
                threads.insert(0, connection_thread)

            for player in self.group2:
                connection_thread = threading.Thread(target=self.receive_keys, args=(player,))
                connection_thread.start()
                threads.insert(0, connection_thread)

            elapsed = time.time() - self.begin

        sum_group1 = 0
        sum_group2 = 0
        # after the while we should close the connection of each player
        for player in self.group1:
            sum_group1 += player[3]
        for player in self.group2:
            sum_group2 += player[3]
        for t in threads:
            t.join()

        if sum_group1 > sum_group2:
            message = "\nGame over!\nGroup 1 typed in {sum1} characters. Group 2 typed in {sum2} " \
                      "characters.\nGroup 1 wins!\n\nCongratulations to the winners:\n==".format(sum1=sum_group1,
                                                                                                 sum2=sum_group2)
            for player in self.group1:
                message += "\n" + player[0]
            if self.max_score < sum_group1:
                self.max_score = sum_group1
                self.best_team_ever = self.group1
            if self.min_score > sum_group2:
                self.max_score = sum_group2
        elif sum_group2 > sum_group1:
            message = "\nGame over!\nGroup 1 typed in {sum1} characters. Group 2 typed in {sum2} " \
                      "characters.\nGroup 2 wins!\n\nCongratulations to the winners:\n==".format(sum1=sum_group1,
                                                                                                 sum2=sum_group2)
            for player in self.group2:
                message += "\n" + player[0]
            if self.max_score < sum_group2:
                self.max_score = sum_group2
                self.best_team_ever = self.group2
            if self.min_score > sum_group1:
                self.min_score = sum_group1
        else:
            message = "\nGame over!\nGroup 1 and Group 2 typed in {} characters. It's a draw! ".format(sum_group1)
            if self.max_score < sum_group1:
                self.max_score = sum_group1
                self.best_team_ever = self.group1
            if self.min_score > sum_group1:
                self.min_score = sum_group1
        message += "\nThe maximum score ever was: {max}\nThe minimum score ever was: {min}\n".format(max=self.max_score,
                                                                                                 min=self.min_score)
        message += "\nThe best teams to play the game are:\n=="
        for player in self.best_team_ever:
            message += "\n" + player[0]
        print(message)

        for player in self.group1:
            try:
                player[1].sendall(message.encode())
                player[1].close()
            except:
                pass
        for player in self.group2:
            try:
                player[1].sendall(message.encode())
                player[1].close()
            except:
                pass

        server_socket.close()

    def receive_keys(self, player):
        """
            this function receives the keys sent by each client and counts them
            :param player - tuple of group_name, connection_socket, client_address, key_counter
        """
        connection_socket = player[1]
        key_counter = player[3]

        while True:
            timeout = TIMEOUT - (time.time() - self.begin)
            if timeout <= 0:
                break
            # receive keys
            try:
                connection_socket.settimeout(timeout)
                data = connection_socket.recv(BUFFER_SIZE)
                if data:
                    key_counter += len(data)  # len of bytes returns how many bytes are in the

            except socket.error:
                return

        player[3] += key_counter
