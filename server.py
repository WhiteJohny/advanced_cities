import socket
import threading
import pickle

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
            player.send(pickle.dumps("Game is starting!"))

        timer = self.change_turn()
        while True:
            if self.game_status == 1:
                timer.cancel()
                self.clear()
                self.run()
                break
            elif self.game_status in [2, 3, 4]:
                timer.cancel()
                self.clear()
                break

            if not self.queue.empty():
                conn, msg = self.queue.get()
                another_conn = self.players[0] if self.players[0] != self.turn else self.players[1]
                if conn == self.turn:
                    if self.valid_city(msg):
                        timer.cancel()
                        another_conn.send(pickle.dumps(f"Your opponent named the city: {msg}.\n"
                                                       f"You should name the city on letter '{msg[-1]}'.\n"
                                                       f"Last cities: {self.last_cities}"))
                        timer = self.change_turn()
                else:
                    conn.send(pickle.dumps("Wait for your turn!"))

    def loose_game(self, conn: socket.socket, another_conn: socket.socket):
        self.game_status = 1
        conn.send(pickle.dumps("Time is up, you lose!"))
        another_conn.send(pickle.dumps("Time of your opponent is up, you win!"))
        print("game over! | loose")

    def change_turn(self):
        another_conn = self.turn
        self.turn = self.players[0] if self.players[0] != self.turn else self.players[1]
        self.turn.send(pickle.dumps("Now your turn!"))
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
            self.turn.send(pickle.dumps('This city starts with wrong letter or named before'))
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
        self.admins: list[socket.socket] = []
        self.ban_list: list[socket.socket] = []
        self.rooms: list[Room] = [Room(i) for i in range(1, rooms_count + 1)]

    def run(self):
        while True:
            conn, address = self.sock.accept()
            print(f'new connection {address}')

            if address in self.ban_list:
                conn.send("You have banned!")
                conn.close()
            else:
                if len(self.clients) == 0:
                    self.admins.append(conn)

                self.clients.append(conn)
                threading.Thread(target=self.handling_client, args=(conn, address)).start()
                print(f"handling new client {address}")

    def handling_client(self, conn: socket.socket, address: str):
        print(f"finding room for {address}")
        room = self.find_room(conn)
        if not room:
            return

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
                try:
                    data: str = pickle.loads(conn.recv(Server.BUFFER_SIZE))
                except EOFError:
                    data: None = None
            except Exception:
                client_queue.put(pickle.dumps("QUIT"))
                break

            if data:
                client_queue.put(pickle.dumps(data))
                if data.upper() in ("QUIT", "CHANGE"):
                    break

    def process_messages(self, conn: socket.socket, room: Room, client_queue: Queue):
        while True:
            if not client_queue.empty():
                data: str = pickle.loads(client_queue.get()).upper()
                print(data, "process")
                if data == "QUIT":
                    self.exit_game(conn, room)
                    break
                elif data == "CHANGE":
                    self.change_room(conn, room)
                    break
                elif data == "BAN":
                    if room.is_full():
                        room.game_status = 4
                        another_conn = room.players[0] if conn != room.players[0] else room.players[1]
                        self.ban_player(conn, another_conn)
                    else:
                        conn.send(pickle.dumps("No opponent in your room!"))

                if room.game_status == 0:
                    room.queue.put((conn, data))
                else:
                    conn.send(pickle.dumps("Wait for your opponent.."))

    def find_room(self, conn: socket.socket) -> Room:
        while True:
            conn.send(pickle.dumps(f"Choose room to play.\nAvailable rooms: {self.rooms}"))
            try:
                data: bytes = pickle.loads(conn.recv(Server.BUFFER_SIZE))
                room_number = data
            except Exception:
                room = None
                conn.close()
                print(f"{conn} lost connection!")
                break

            if room_number.upper() == "QUIT":
                room = None
                conn.send(pickle.dumps("You left!"))
                conn.close()
                print(f"{conn} left!")
                break

            if room_number.isdigit():
                room_number = int(room_number)
                if 1 <= room_number <= len(self.rooms):
                    if not self.rooms[room_number - 1].is_full():
                        room = self.rooms[room_number - 1]
                        room.add_player(conn)
                        conn.send(pickle.dumps(f"You joined in {room.number}!"))
                        break
                    else:
                        conn.send(pickle.dumps("That room is full!"))
                else:
                    conn.send(pickle.dumps("That room does not exist!"))
            else:
                conn.send(pickle.dumps("Wrong room number!"))

        return room

    @staticmethod
    def change_room(conn: socket.socket, room: Room):
        room.game_status = 2
        if room.is_full():
            conn.send(pickle.dumps("You lose!"))
            another_conn = room.players[1 - room.players.index(conn)]
            another_conn.send("Your opponent left, you win!".encode())
            print("game over!", end=" | ")

        conn.send(pickle.dumps("You left the room!"))
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
                another_conn.send(pickle.dumps("Your opponent left, you win!"))
            except Exception:
                pass
            print("game over!", end=" | ")

        try:
            conn.send(pickle.dumps("You left!"))
        except Exception:
            pass
        room.remove_player(conn)
        conn.close()
        print(f"{conn} left")

    def ban_player(self, conn: socket.socket, another_conn: socket.socket):
        if conn in self.admins:
            self.ban_list.append(conn)
            another_conn.send(pickle.dumps("You have banned!"))
            another_conn.close()
            print(f"{conn} banned {another_conn}")
        else:
            conn.send(pickle.dumps("You do not have permission to use this command!"))


server = Server(rooms_count=10)
server.start()
