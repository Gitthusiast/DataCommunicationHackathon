import socket
import struct
import time
import multiprocessing
import getch
from scapy.arch import get_if_addr

TIMEOUT = 15
BUFFER_SIZE = 2048
UDP_PACKET_SIZE = 7


class Client:

    def __init__(self, name):

        self.name = name
        self.client_ip = get_if_addr('eth1')
        self.udp_port = 13117
        self.server_port = None
        self.server_ip = None

        self.beginTimer = None
        self.endTimer = None

    def start_client(self):
        """
        Main function for client. Responsible for all the flow.
        """

        print("Client started, listening for offer requests...")

        while True:
            # look for server over udp
            found_server = self.looking_for_server()

            if found_server:
                # connect via TCP connection
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
                    connected = self.connecting_to_server(tcp_socket)

                    if connected:  # successfully connected to server
                        self.game_mode(tcp_socket)

    def looking_for_server(self):
        """
        Listen for available servers over UDP
        :return: If successfully contacted a server
        :rtype: bool
        """

        try:

            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.bind((self.client_ip, self.udp_port))

            # receive UDP broadcast from server
            # listen for offer invitations
            msglen = UDP_PACKET_SIZE  # UDP_PACKET_SIZE bytes of data according to agreed format
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

                # wait for TIMEOUT seconds from connection to server to receive "game welcome" message
                self.beginTimer = time.time()
                return True
            else:
                return False

        except struct.error:
            print("Failed to unpack message. Wrong header format given")
            return False

    def connecting_to_server(self, tcp_socket):
        """
        Connecting to found server over TCP according to IP received from socket and port received from packet over UDP.
        :param tcp_socket: TCP socket for connecting to server
        :type tcp_socket: socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        :return: If managed to connect to server and sent team name
        :rtype: bool
        """

        timeout = TIMEOUT - (time.time() - self.beginTimer)
        if timeout > 0:
            tcp_socket.settimeout(timeout)  # the program would wait TIMEOUT seconds max for client to connect to server

            try:
                tcp_socket.connect((self.server_ip, self.server_port))
                tcp_socket.sendall((self.name + "\n").encode())  # send team name
                return True

            except socket.error:
                return False
        else:  # timeout passed
            return False

    def game_mode(self, tcp_socket):
        """
        Entering game mode after successfully connecting to server over TCP. Receive game start and finish messages and
        send caught key-presses.
        :param tcp_socket: connected server TCP socket
        :type tcp_socket: socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        :return: If successfully finished game
        :rtype: bool
        """

        timeout = TIMEOUT - (time.time() - self.beginTimer)
        if timeout > 0:
            # listen for game start message
            gamestart_message = self.recvall_tcp(tcp_socket, TIMEOUT)
            if gamestart_message:
                print(gamestart_message)

                # restart timer - begin game
                self.beginTimer = time.time()

                # game welcoming message received, start listening for keypress
                keypress_process = multiprocessing.Process(target=self.get_and_send_keypress, args=(tcp_socket,))
                keypress_process.start()

                # listen for endgame message
                endgame_message = ['']
                endgame_process = multiprocessing.Process(target=self.recv_endgame, args=(tcp_socket,TIMEOUT, endgame_message))
                endgame_process.start()

                # keep playing until timeout passed - game over
                while timeout > 0:
                    timeout = TIMEOUT - (time.time() - self.beginTimer)
                keypress_process.terminate()
                endgame_process.terminate()

                # print endgame message
                if endgame_message[0]:
                    print(endgame_message[0])
                    print("Server disconnected, listening for offer requests...")
                    return True

                # # listen for endgame message
                # self.beginTimer = time.time()
                # endgame_message = self.recvall_tcp(tcp_socket, TIMEOUT)
                # if endgame_message:
                #     print(endgame_message)
                #     print("Server disconnected, listening for offer requests...")
                #     return True
                else:  # game end message not received correctly
                    return False

            else:  # game welcoming message not received correctly
                return False
        else:  # timeout passed
            return False

    def get_and_send_keypress(self, sock):
        """
        Using TCP socket to send key-presses caught from keyboard.
        :param sock: connected server TCP socket
        :type sock: socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        """

        # set timeout
        timeout = TIMEOUT - (time.time() - self.beginTimer)
        while True:

            if timeout > 0:
                keypress = getch.getch()
                try:
                    sock.sendall(keypress)
                except socket.error:
                    print("server closed. Client stop sending keys")
                    break
            else:  # timeout passed
                break

    def recvall_udp(self, sock, length):
        """
        Implementing a recvall function over UDP based on predefined messaged length.
        :param sock: connected server TCP socket
        :type sock: socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        :param length: Length of expected message
        :type length: int
        :return: Tuple of message and sender address
        """

        message = bytearray()
        server_ip = None
        while len(message) < length:

            # recvfrom returns a bytes object and the address of the client socket as a tuple (ip, port)
            packet, address = sock.recvfrom(BUFFER_SIZE)  # read remaining data

            if not server_ip:
                server_ip = address[0]

            if not packet:  # EOF - something went wrong
                return None
            message.extend(packet)

        return message, server_ip

    def recvall_tcp(self, sock, timelimit):
        """
        Receives message from TCP server according to given timeout
        :param timelimit: Maximal timeout for receiving
        :param sock: the tcp socket of the connected server
        :return: return the message received from the server in game mode
        """
        message = ""
        total_data = []

        # set timeout
        timeout = timelimit - (time.time() - self.beginTimer)
        if timeout > 0:
            sock.settimeout(timeout)

            # receive welcome message
            try:
                data = sock.recv(BUFFER_SIZE)
                if data:
                    total_data.append(data.decode())
            except socket.error:
                return None

            # join all parts to make final string
            message = ''.join(total_data)  # receive game welcoming message from server
            return message
        else:  # timeout passed
            return None

    def recv_endgame(self, sock, timelimit, end_message):
        """
        Receiving end game message and stores it in a single variable mutable list
        :param sock: the tcp socket of the connected server
        :param timelimit: Maximal timeout for receiving
        :param end_message: single variable mutable list for storing message
        :return: return the message received from the server in game mode
        """

        end_message[0] = self.recvall_tcp(sock, timelimit)
