import socket
import threading

from queue import Queue
from random import choice


class Room:
    def __init__(self, number):
        self.number: int = number

        self.players: list[socket.socket] = []
        self.last_cities: list[str] = []
        self.game_status: int = -1
        self.turn: socket.socket | None = None
        self.queue: Queue = Queue()

    def run(self):
        self.game_status = 0
        self.turn = choice(self.players)

        for player in self.players:
            player.send("Game is starting!".encode())

        timer = self.change_turn()
        while True:
            if self.game_status == 1:
                timer.cancel()
                self.clear()
                self.run()
                break
            elif self.game_status in [2, 3]:
                timer.cancel()
                self.clear()
                break

            if not self.queue.empty():
                conn, msg = self.queue.get()
                another_conn = self.players[0] if self.players[0] != self.turn else self.players[1]
                if conn == self.turn:
                    if self.valid_city(msg):
                        timer.cancel()
                        another_conn.send(f"Your opponent named the city: {msg}.\n"
                                          f"You should name the city on letter '{msg[-1]}'.\n"
                                          f"Last cities: {self.last_cities}".encode())
                        timer = self.change_turn()
                else:
                    conn.send("Wait for your turn!".encode())

    def loose_game(self, conn: socket.socket, another_conn: socket.socket):
        self.game_status = 1
        conn.send("Time is up, you lose!".encode())
        another_conn.send("Time of your opponent is up, you win!".encode())
        print("game over! | loose")

    def change_turn(self):
        another_conn = self.turn
        self.turn = self.players[0] if self.players[0] != self.turn else self.players[1]
        self.turn.send("Now your turn!".encode())
        timer = threading.Timer(interval=15, function=self.loose_game, args=(self.turn, another_conn))
        timer.start()
        return timer

    def valid_city(self, city: str) -> bool:
        flag = True
        if not self.last_cities:
            self.last_cities.append(city)
        elif city[0] == self.last_cities[-1][-1] and city not in self.last_cities:
            self.last_cities.append(city)
        else:
            self.turn.send('This city starts with wrong letter or named before'.encode())
            flag = False

        return flag

    def add_player(self, conn):
        self.players.append(conn)
        print(f'{conn} added to room {self.number}')

    def remove_player(self, conn):
        self.players.remove(conn)
        print(f'{conn} removed from room {self.number}')

    def is_full(self) -> bool:
        if len(self.players) == 2:
            return True

        return False

    def clear(self):
        self.last_cities: list[str] = []
        self.game_status: int = -1
        self.turn: socket.socket | None = None
        self.queue: Queue = Queue()

    def __len__(self):
        return len(self.players)

    def __repr__(self):
        return f'Room: {self.number} | Players: {len(self.players)}/2'


class Server(threading.Thread):
    ADDRESS = ('localhost', 9001)
    BUFFER_SIZE = 1024

    def __init__(self, rooms_count: int):
        super().__init__()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print('socket created')

        self.sock.bind(Server.ADDRESS)
        print('socket bound')

        self.sock.listen()
        print('socket is listening now')

        self.clients: list[socket.socket] = []
        self.rooms: list[Room] = [Room(i) for i in range(1, rooms_count + 1)]

    def run(self):
        while True:
            conn, address = self.sock.accept()
            print(f'new connection {address}')
            self.clients.append(conn)
            threading.Thread(target=self.handling_client, args=(conn, address)).start()
            print(f"handling new client {address}")

    def handling_client(self, conn: socket.socket, address: str):
        print(f"finding room for {address}")
        room = self.find_room(conn)
        client_queue = Queue()
        print(f"{address} join in {room.number}")

        receive_th = threading.Thread(target=self.receive_messages, args=(conn, client_queue))
        process_th = threading.Thread(target=self.process_messages, args=(conn, room, client_queue))

        receive_th.start()
        process_th.start()

        if room.is_full():
            room.run()

        receive_th.join()

    @staticmethod
    def receive_messages(conn: socket.socket, client_queue: Queue):
        while True:
            try:
                data: bytes = conn.recv(Server.BUFFER_SIZE)
            except Exception:
                client_queue.put("QUIT".encode())
                break
            client_queue.put(data)
            if data.decode().upper() in ("QUIT", "CHANGE"):
                break

    def process_messages(self, conn: socket.socket, room: Room, client_queue: Queue):
        while True:
            if not client_queue.empty():
                data: bytes = client_queue.get()
                msg: str = data.decode().upper()

                if msg == "QUIT":
                    self.exit_game(conn, room)
                    break
                elif msg == "CHANGE":
                    self.change_room(conn, room)
                    break

                if room.game_status == 0:
                    room.queue.put((conn, msg))
                else:
                    conn.send("Wait for your opponent..".encode())

    def find_room(self, conn):
        while True:
            conn.send(f"Choose room to play.\nAvailable rooms: {self.rooms}".encode())
            data: bytes = conn.recv(Server.BUFFER_SIZE)

            room_number = data.decode()
            if room_number.isdigit():
                room_number = int(room_number)
                if 1 <= room_number <= len(self.rooms):
                    if not self.rooms[room_number - 1].is_full():
                        room = self.rooms[room_number - 1]
                        room.add_player(conn)
                        conn.send(f"You joined in {room.number}!".encode())
                        break
                    else:
                        conn.send("That room is full!".encode())
                else:
                    conn.send("That room does not exist!".encode())
            else:
                conn.send("Wrong room number!".encode())

        return room

    @staticmethod
    def change_room(conn: socket.socket, room: Room):
        room.game_status = 2
        if room.is_full():
            conn.send("You lose!".encode())
            another_conn = room.players[1 - room.players.index(conn)]
            another_conn.send("Your opponent left, you win!".encode())
            print("game over!", end=" | ")

        conn.send("You left the room!".encode())
        room.remove_player(conn)
        server.handling_client(conn, "address")
        print(f"{conn} changed room")

    @staticmethod
    def exit_game(conn: socket.socket, room: Room):
        room.game_status = 3
        if room.is_full():
            try:
                conn.send("You lose!".encode())
                another_conn = room.players[1 - room.players.index(conn)]
                another_conn.send("Your opponent left, you win!".encode())
            except Exception:
                pass
            print("game over!", end=" | ")

        try:
            conn.send("You left!".encode())
        except Exception:
            pass
        room.remove_player(conn)
        conn.close()
        print(f"{conn} left")


server = Server(rooms_count=10)
server.start()
