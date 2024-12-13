import threading
import socket
import pickle


class Client:
    BUFFER_SIZE = 1024
    SERVER_ADDRESS = ('localhost', 9001)

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def run(self):
        print('Connecting to {}:{}'.format(*Client.SERVER_ADDRESS))
        self.sock.connect(Client.SERVER_ADDRESS)
        print('Connected to server')

        th1 = threading.Thread(target=self.receive_messages, args=())
        th2 = threading.Thread(target=self.send_messages, args=())

        th2.start()
        th1.start()

        th1.join()

    def receive_messages(self):
        while True:
            try:
                try:
                    data: str = pickle.loads(self.sock.recv(Client.BUFFER_SIZE))
                except (EOFError, pickle.UnpicklingError):
                    data: None = None
            except Exception:
                self.sock.close()
                break

            if data:
                print(data)

    def send_messages(self):
        while True:
            msg: str = input()
            data: bytes = pickle.dumps(msg)
            self.sock.send(data)
            print("Sent")

            if msg.lower() == "quit":
                print(pickle.loads(self.sock.recv(Client.BUFFER_SIZE)))
                self.sock.close()
                break


client = Client()

try:
    client.run()
except Exception:
    pass
