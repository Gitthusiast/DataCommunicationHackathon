import socket
import struct
import time
import msvcrt
import multiprocessing

TIMEOUT = 15


class Client:

    def __init__(self, name):

        self.name = name
        self.client_ip = '192.168.0.186'
        self.udp_port = 13117
        self.server_port = None
        self.server_ip = None

        self.beginTimer = None
        self.endTimer = None

    def start_client(self):

        print("Client started, listening for offer requests...")

        while True:
            found_server = self.looking_for_server()

            if found_server:
                # connect via TCP connection
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
                    connected = self.connecting_to_server(tcp_socket)

                    if connected:  # successfully connected to server
                        self.game_mode(tcp_socket)

    def looking_for_server(self):

        try:

            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.bind((self.client_ip, self.udp_port))

            # receive UDP broadcast from server
            # listen for offer invitations
            msglen = 7  # 7 bytes of data
            packet = self.recvall_udp(udp_socket, msglen)

            if packet:  # successfully received udp offer
                message, self.server_ip = packet

                magic_cookie, message_type, self.server_port = struct.unpack("IbH", message)
                if magic_cookie != 0xfeedbeef:  # magicCookie
                    print("the message is rejected not a magic cookie")

                if message_type != 0x2:  # offer message
                    print("only 0x2 offer types are supported")

                # receive offer
                print("Recieved offer from {IP}, attempting to connect...".format(IP=self.server_ip))

                # wait for 15 seconds from connection to server to receive "game welcome" message
                self.beginTimer = time.time()
                return True
            else:
                return False

        except struct.error:
            print("Failed to unpack message. Wrong header format given")
            return False

    def connecting_to_server(self, tcp_socket):

        timeout = TIMEOUT - (time.time() - self.beginTimer)
        if timeout > 0:
            tcp_socket.settimeout(timeout)  # the program would wait 15 seconds max for client to connect to server

            try:
                tcp_socket.connect((self.server_ip, self.server_port))
                tcp_socket.sendall(self.name + "\n")
                return True

            except socket.timeout:
                return False
        else:  # timeout passed
            return False

    def game_mode(self, tcp_socket):

        timeout = TIMEOUT - (time.time() - self.beginTimer)
        if timeout > 0:
            gamestart_message = self.recvall_tcp(tcp_socket, TIMEOUT)
            if gamestart_message:
                print(gamestart_message)

                # restart timer - begin game
                self.beginTimer = time.time()

                # game welcoming message received, start listening for keypress
                keypress_process = multiprocessing.Process(target=self.get_and_send_keypress, args=(tcp_socket,))
                keypress_process.start()

                # keep playing until timeout passed - game over
                while timeout > 0:
                    timeout = TIMEOUT - (time.time() - self.beginTimer)
                keypress_process.terminate()

                # listen for endgame message
                endgame_message = self.recvall_tcp(tcp_socket, 5)
                if endgame_message:
                    print(endgame_message)
                    print("Server disconnected, listening for offer requests...")
                    return True
                else:  # game end message not received correctly
                    return False

            else:  # game welcoming message not received correctly
                return False
        else:  # timeout passed
            return False

    def get_and_send_keypress(self, sock):

        # set timeout
        timeout = TIMEOUT - (time.time() - self.beginTimer)
        while True:

            if timeout > 0:
                keypress = msvcrt.getch()
                sock.sendall(keypress)
            else:  # timeout passed
                break

    def recvall_udp(self, sock, length):

        message = bytearray()
        server_ip = None
        while len(message) < length:

            # recvfrom returns a bytes object and the address of the client socket as a tuple (ip, port)
            packet, address = sock.recvfrom(length - len(message))  # read remaining data

            if not server_ip:
                server_ip = address[0]

            if not packet:  # EOF - something went wrong
                return None
            message.extend(packet)

        return message, server_ip

    def recvall_tcp(self, sock, timelimit):
        """
        this function receives message from tcp server and prints it to screen
        :param timelimit:
        :type timelimit:
        :param sock: the tcp socket to send the keyboard character
        :return: return the message received from the server and print it in game mode
        """

        total_data = []
        while True:

            # set timeout
            timeout = timelimit - (time.time() - self.beginTimer)
            if timeout > 0:
                sock.settimeout(timeout)

                # receive welcome message
                try:
                    data = sock.recv(2048)
                    if data:
                        total_data.append(data)
                except socket.error:
                    print("couldn't receive the welcoming message")
                    return None

                # join all parts to make final string
                message = ''.join(total_data)  # receive game welcoming message from server
                return message
            else:  # timeout passed
                return None
