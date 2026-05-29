__author__ = "Leehu Shacht"
import uuid
import platform
import hashlib
import pygame
import threading
import socket
from msg_by_size_snake import TransportData
import json
import os
import time
import math
import msgpack
import base64
import random

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes


def encrypt_aes_key(message, public_key):
    # 3. Encrypt the symmetric key with the RSA Public Key
    encrypted_message = public_key.encrypt(
        message, padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return encrypted_message


pygame.init()


def get_device_fingerprint():
    # mac address
    mac = hex(uuid.getnode())
    # system data
    node_name = platform.node()  # computer name
    processor = platform.processor()  # processor type

    raw_id = f"{mac}-{node_name}-{processor}"
    fingerprint = hashlib.sha256(raw_id.encode()).hexdigest()
    return fingerprint


def xor_data(data, key):
    """מערבל את הבתים בעזרת מפתח (טביעת האצבע)"""
    key_bytes = key.encode()
    return bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data)])


def save_settings_binary(username, token):
    try:
        data = {
            "u": username,
            "t": token
        }
        packed_data = msgpack.packb(data)
        fingerprint = get_device_fingerprint()
        encrypted_data = xor_data(packed_data, fingerprint)
        with open("settings.bin", "wb") as f:
            f.write(encrypted_data)
        print("Settings saved in binary format.")
    except Exception as e:
        print(f"Error saving binary: {e}")


def load_settings_binary():
    if not os.path.exists("settings.bin"):
        return None, None
    try:
        with open("settings.bin", "rb") as f:
            byte_data = f.read()
        byte_data = xor_data(byte_data, get_device_fingerprint())
        data = msgpack.unpackb(byte_data, raw=False)
        return data.get("u"), data.get("t")
    except Exception as e:
        print(f"Error  : {e}")
    return None, None


#print("finger print --> ", get_device_fingerprint())

SNAKE_BODY = 1
SNAKE_HEAD = 2
APPLE = 3
COIN = 6

BLOCK_SIZE = 15
UDP_RECV_SIZE = 65535
EWOULDBLOCK = 10035
COLOR_PACK = [(255, 255, 255)]

ERROR_DICT = {
    "003": "Login failed",
    "004": "Signup failed",
    "005": "Illegal state: action not allowed right now",
    "006": "Purchase has failed",
    "007": "Auto login failed",
    "008": "Passwords don't match!",
    "009": "key not recognized"
}

# -------- LOGIN SCREEN -------- #
COLOR_BG = (30, 30, 30)
COLOR_INACTIVE = (51, 51, 51)
COLOR_ACTIVE = (33, 150, 243)
COLOR_TEXT = (255, 255, 255)

STATE_LOGIN = "LOGIN"
STATE_SIGNUP = "SIGNUP"

STATE_HANDSHAKE = 0  # Key replacement
STATE_AUTH = 1       # sign in screen
STATE_LOBBY = 2      # lobby time
STATE_GAME = 3       # in game


class LoadingSpinner:
    def __init__(self):
        # create surf
        self.surf = pygame.Surface((100, 100), pygame.SRCALPHA)
        pygame.draw.circle(self.surf, (50, 50, 60), (50, 50), 35, 6)
        pygame.draw.arc(self.surf, (0, 210, 80), pygame.Rect(15, 15, 70, 70), 0, math.radians(120), 6)
        self.angle = 0
        self.font = pygame.font.SysFont(None, 40)

    def draw(self, screen, text_message):
        # background draw
        screen.fill((20, 20, 25))

        # text draw
        wait_text = self.font.render(text_message, True, (220, 220, 220))
        screen.blit(wait_text, wait_text.get_rect(center=(300, 220)))

        # spin and draw
        self.angle = (self.angle - 8) % 360
        rotated_spinner = pygame.transform.rotate(self.surf, self.angle)
        spinner_rect = rotated_spinner.get_rect(center=(300, 300))
        screen.blit(rotated_spinner, spinner_rect)


class BgSnake:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.x = random.randint(0, w)
        self.y = random.randint(0, h)
        self.angle = random.uniform(0, 2 * math.pi)
        self.speed = 2.5
        self.length = random.randint(20, 50)
        self.history = []

        # Dark Mode
        base_color = random.choice([(35, 75, 45), (35, 45, 75), (60, 35, 75), (50, 50, 50)])
        self.color = base_color
        self.radius = random.randint(6, 12)
        self.turn_speed = random.uniform(-0.03, 0.03)

    def update(self):
        self.angle += self.turn_speed + math.sin(time.time() * 2) * 0.015

        self.x += math.cos(self.angle) * self.speed
        self.y += math.sin(self.angle) * self.speed

        if self.x < -30: self.x = self.w + 30
        if self.x > self.w + 30: self.x = -30
        if self.y < -30: self.y = self.h + 30
        if self.y > self.h + 30: self.y = -30

        self.history.insert(0, (self.x, self.y))
        if len(self.history) > self.length:
            self.history.pop()

    def draw(self, screen):
        for i, (hx, hy) in enumerate(self.history):
            r = max(1, self.radius - (i * (self.radius / self.length)))
            pygame.draw.circle(screen, self.color, (int(hx), int(hy)), int(r))


class CheckBox:
    def __init__(self, x, y, label="Remember Me"):
        self.rect = pygame.Rect(x, y, 22, 22)
        self.checked = False
        self.label = label
        self.font = pygame.font.SysFont("Segoe UI", 18)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos):
            self.checked = not self.checked

    def draw(self, screen):
        pygame.draw.rect(screen, (200, 200, 200), self.rect, 2, border_radius=4)
        if self.checked:
            pygame.draw.rect(screen, COLOR_ACTIVE, self.rect.inflate(-8, -8), border_radius=2)
        txt = self.font.render(self.label, True, (255, 255, 255))
        screen.blit(txt, (self.rect.right + 10, self.rect.y))


class InputBox:
    def __init__(self, x, y, w, h, placeholder='', is_password=False):
        self.rect = pygame.Rect(x, y, w, h)
        self.color = COLOR_INACTIVE
        self.text = ''
        self.placeholder = placeholder
        self.active = False
        self.is_password = is_password
        self.font = pygame.font.SysFont("Segoe UI", 24)

        # Cursor
        self.cursor_visible = True
        self.cursor_timer = pygame.time.get_ticks()
        self.cursor_interval = 500  # milliseconds

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            # שינוי פוקוס
            self.active = self.rect.collidepoint(event.pos)
            self.color = COLOR_ACTIVE if self.active else COLOR_INACTIVE
        if event.type == pygame.KEYDOWN and self.active:
            # reset cursor blink on typing
            self.cursor_visible = True
            self.cursor_timer = pygame.time.get_ticks()
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            else:
                if len(self.text) < 30:
                    if event.unicode.isalnum():
                        self.text += event.unicode

    def update_cursor(self):
        now = pygame.time.get_ticks()
        if now - self.cursor_timer > self.cursor_interval:
            self.cursor_visible = not self.cursor_visible
            self.cursor_timer = now

    def draw(self, screen):
        # ציור התיבה
        pygame.draw.rect(screen, COLOR_INACTIVE, self.rect, border_radius=5)
        if self.active:
            pygame.draw.rect(screen, COLOR_ACTIVE, self.rect, 2, border_radius=5)

        # הצגת טקסט או Placeholder
        display_text = self.text
        if self.is_password and self.text:
            display_text = '*' * len(self.text)
        elif not self.text:
            display_text = self.placeholder

        txt_surf = self.font.render(display_text, True, COLOR_TEXT if self.text else (100, 100, 100))
        screen.blit(txt_surf, (self.rect.x + 10, self.rect.y + 5))
        # update cursor
        self.update_cursor()

        # cursor draw
        if self.active and self.cursor_visible and self.text:
            ascent = self.font.get_ascent()
            descent = self.font.get_descent()
            text_height = ascent + descent

            cursor_x = self.rect.x + 10 + self.font.size(display_text)[0]
            cursor_y = self.rect.y + (self.rect.height - text_height) // 2

            cursor_height = text_height

            pygame.draw.line(
                screen,
                COLOR_TEXT,
                (cursor_x, cursor_y),
                (cursor_x, cursor_y + cursor_height),
                2
            )
# -------- LOGIN SCREEN -------- #


class ClientThreadUDP(threading.Thread):
    def __init__(self, cli_obj):
        super().__init__()
        self.cli_obj = cli_obj
        self.running = True
        self.cmd_dict = {"BOARD": self.board_f}

    def run(self):
        while not self.cli_obj.got_init and self.running:
            msg = self.build_message("INIT", tid=self.cli_obj.tid)
            self.cli_obj.send_to_server_UDP(msg, encrypt=False)
            time.sleep(0.5)
        self.cli_obj.UDP_sock.settimeout(0.05)
        while self.running:  # and self.cli_obj.alive:
            try:
                data, addr = self.cli_obj.UDP_sock.recvfrom(UDP_RECV_SIZE)
                if not data:
                    continue
                data = self.cli_obj.decrypt_data_with_AES(data)
                if not data:
                    continue
                data_dict = msgpack.unpackb(data, raw=False)
                command = data_dict.get("cmd")
                payload = data_dict.get("payload", {})
                if command in self.cmd_dict:
                    self.cmd_dict[command](payload)
            except socket.error as err:
                if err.errno == EWOULDBLOCK or str(err) == "timed out":
                    continue
                print("UDP Recv Error:", err)
            except Exception as e:
                print("UDP Error:", e)

    def build_message(self, cmd, **payload):
        return {
            "cmd": cmd,
            "payload": payload
        }

    def board_f(self, payload):
        if self.cli_obj.state != STATE_GAME:
            return
        self.cli_obj.board_f(payload)


class ClientThread(threading.Thread):
    def __init__(self, ip="127.0.0.1", port=46767):
        super().__init__()
        self.lock = threading.RLock()
        self.ip = ip
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.state = STATE_HANDSHAKE
        self.my_amount_of_coins = 0
        self.last_coins = 0

        self.got_init = False
        self.UDP_port = None
        self.UDP_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.UDP_obj = None
        self.last_board_id = -1
        self.asking_server_for_sync = False
        self.pending_udp_updates = []

        self.key = get_random_bytes(32)

        self.boosting = False
        self.last_direction = None

        self.running = True
        self.color = None
        self.transport_data = TransportData(self.sock, "KEY")
        self.cmd_dict = {"BOARD": self.board_f, "ID": self.id_f,
                         "NEW_BOARD": self.new_board_f, "PUB_KEY": self.pub_key_get_f,
                         "DIED": self.died_f, "ACK": self.ack_f, "ERROR": self.error_f,
                         "COINS": self.coins_f}
        self.tid = None

        # board area
        self.board_height = -1
        self.board_width = -1
        self.walls = []
        self.water = []
        self.flowers = []

        self.tid_to_color = {}

        self.tid_to_username = {}
        self.known_usernames = {}

        self.camera_x = -1
        self.camera_y = -1
        self.visual_camera_x = -1.0
        self.visual_camera_y = -1.0

        self.visual_snakes = {}
        self.snake_lengths = {}
        self.target_snakes = {}
        self.recent_deaths = []

        self.grid = {}

        self.alive = True
        self.leaders = None

        self.error_num = ""
        self.error_time = 0

        self.game_shop = None
        self.items_i_own = None

        self.should_remember = False

    def run(self):
        try:
            time.sleep(0.6)  # for animation

            self.sock.connect((self.ip, self.port))
            while self.running:
                data_rec = self.recv_from_server()
                if not data_rec:
                    break
                data_recv = msgpack.unpackb(data_rec, raw=False)
                print("-------------------\nrecved:", data_recv, "\n----------------------")
                cmd = data_recv.get("cmd")
                payload = data_recv.get("payload", {})
                if cmd in self.cmd_dict:
                    self.cmd_dict[cmd](payload)
        except Exception as e:
            print(e)
        self.close()

    def build_message(self, cmd, **payload):
        return {
            "cmd": cmd,
            "payload": payload
        }

    def recv_from_server(self):
        return self.transport_data.recv_by_size()

    def send_to_server(self, data_dict):
        try:
            with self.lock:
                print("--------------------\nRaw : ", data_dict)
                data_bytes = msgpack.packb(data_dict)
                print("Sent TCP: ", data_bytes, "\n-------------------")
                self.transport_data.send_with_size(data_bytes)
        except Exception as e:
            print("Send failed:", e)

    def send_to_server_UDP(self, data_dict, encrypt=True):
        try:
            if self.UDP_port:
                data_bytes = msgpack.packb(data_dict)
                if encrypt:
                    data_bytes = self.encrypt_data_with_AES(data_bytes)
                server_address = (self.ip, self.UDP_port)
                self.UDP_sock.sendto(data_bytes, server_address)
                print("--------------------\nsent UDP", data_bytes)
                print("RAW: ", data_dict, "\n----------------------")
        except socket.error as e:
            print(e)
        except Exception as e:
            print(e)

    def decrypt_data_with_AES(self, data):
        # no key --> no decrypt
        if self.transport_data.key == "KEY":
            return data
        try:
            iv = data[:16]
            ciphertext = data[16:]
            cipher = AES.new(self.transport_data.key, AES.MODE_CBC, iv)
            return unpad(cipher.decrypt(ciphertext), AES.block_size)
        except Exception as e:
            print(f"UDP Decryption failed: {e}")
            return None

    def encrypt_data_with_AES(self, data_bytes):
        if self.transport_data.key == "KEY":
            return data_bytes
        try:
            iv = get_random_bytes(16)
            cipher = AES.new(self.transport_data.key, AES.MODE_CBC, iv)
            ciphertext = cipher.encrypt(pad(data_bytes, AES.block_size))
            return iv + ciphertext
        except Exception as e:
            print(f"UDP Encryption failed: {e}")
            return None

    def died_f(self, payload):
        with self.lock:
            print("died in TCP")
            died = payload.get("died", [])
            for p_id_str in died:

                # for animation
                user_name = self.known_usernames.get(str(p_id_str), f"Player {p_id_str}")
                if user_name not in self.recent_deaths:
                    self.recent_deaths.append(user_name)
                # -------------
                if p_id_str in self.visual_snakes:
                    del self.visual_snakes[p_id_str]

            if str(self.tid) in died:
                self.alive = False

    def board_f(self, payload):
        with self.lock:
            tick_id = payload.get("ID", -1)
            delta = payload.get("delta")
            is_full_sync = "full_grid" in delta

            # for loss, we add history to the udp msg (older udp msgs)
            history = payload.get("history", {})

            # when asked for sync but didn't get it yet, we keep the udp msgs to use them after we will get the tcp sync
            if self.asking_server_for_sync and not is_full_sync:
                self.pending_udp_updates.append(payload)
                return

            # normal udp msg
            if not is_full_sync:

                # old msg
                if tick_id != -1 and tick_id <= self.last_board_id:
                    return

                # recv udp msg newer than what we need ->
                # we check if the history that came with it is good enough to recover
                if tick_id > self.last_board_id + 1:
                    missing_ticks = tick_id - self.last_board_id - 1
                    print("packet missing: ", missing_ticks)
                    # we need to check if we can recover from the loss with the history added to the msg itself
                    can_recover = True
                    for missing_id in range(self.last_board_id + 1, tick_id):
                        if str(missing_id) not in history and missing_id not in history:
                            can_recover = False
                            break
                    if can_recover:
                        print("good! we can recover!!")
                        # fast-forward (only data update no graphic at all!)-> we add the changes of the missing msgs
                        # one after the other, catch the gap that we miss, so we can use new msgs!
                        for missing_id in range(self.last_board_id + 1, tick_id):
                            missing_delta = history.get(missing_id) or history.get(str(missing_id))
                            self.update_grid(missing_delta.get("remove", []), missing_delta.get("add", []))
                            self.last_board_id = missing_id

                    else:
                        # can't recover, the gap is too big, so we need full sync from server!
                        print(f"Packet loss! Expected {self.last_board_id + 1}, got {tick_id}. Requesting SYNC.")
                        self.asking_server_for_sync = True
                        self.send_to_server(self.build_message("SYNC_ME"))
                        return

            # ----------------------------
            # all good! now handle the msg

            if tick_id != -1:
                self.last_board_id = tick_id

            # tcp msg
            if is_full_sync:
                print("update with tcp")
                self.asking_server_for_sync = False
                # update, so we reset grid
                self.grid = {}
                for point in delta["full_grid"]:
                    self.grid[(point[0], point[1], point[4])] = (point[2], point[3])
                # if there are waiting msg
                if self.pending_udp_updates:
                    # sort them by ID
                    self.pending_udp_updates.sort(key=lambda x: x.get("ID", -1))
                    print(f"Applying {len(self.pending_udp_updates)} pending updates...")
                    # now, if the msg is newer then the tcp we got, we use it --> tcp takes longer so udp msgs might
                    # arrive before the tcp, so we keep them in this list to use them when the tcp arrived
                    for next_update in self.pending_udp_updates:
                        p_id = next_update.get("ID", -1)
                        # only newer than the tcp msg
                        if p_id > self.last_board_id:
                            # we need to check again for missing udp msgs
                            if p_id > self.last_board_id + 1:
                                history = next_update.get("history", {})
                                can_recover = True
                                for missing_id in range(self.last_board_id + 1, p_id):
                                    if str(missing_id) not in history and missing_id not in history:
                                        can_recover = False
                                        break
                                if can_recover:
                                    print("Recovered missing packet during fast-forward!")
                                    for missing_id in range(self.last_board_id + 1, p_id):
                                        missing_delta = history.get(missing_id) or history.get(str(missing_id))
                                        self.update_grid(missing_delta.get("remove", []),
                                                             missing_delta.get("add", []))
                                        self.last_board_id = missing_id
                                else:
                                    # can't recover -> ask for sync!
                                    print(f"Packet loss during Fast-Forward! Expected {self.last_board_id + 1},"
                                          f" got {p_id}. Requesting SYNC again.")
                                    self.asking_server_for_sync = True
                                    self.pending_udp_updates.clear()
                                    self.send_to_server(self.build_message("SYNC_ME"))
                                    return
                                    # ----------------------------------------------

                            p_delta = next_update.get("delta", {})
                            self.update_grid(p_delta.get("remove", []), p_delta.get("add", []))
                            self.last_board_id = p_id
            # udp msg arrived
            else:
                self.update_grid(delta.get("remove", []), delta.get("add", []))
            # normal updates for udp and tcp (both give them)
            if "usernames" in delta:
                self.tid_to_username = delta.get("usernames")
                self.known_usernames.update(self.tid_to_username)
                print("udp,", self.tid_to_username)
            if "length" in delta:
                self.snake_lengths = delta.get("length")
            if "players_color" in delta:
                self.tid_to_color = delta.get("players_color")
            self.leaders = delta.get("leaders")
            self.build_snakes_game_data()

    def pub_key_get_f(self, payload):
        public_key = payload.get("key")
        print("in pub_key_get_f")
        self.state = STATE_AUTH
        server_pub_key_obj = serialization.load_pem_public_key(base64.b64decode(public_key))
        encrypted_aes_key = encrypt_aes_key(self.key, server_pub_key_obj)
        encrypted_key_b64 = base64.b64encode(encrypted_aes_key).decode('utf-8')
        msg = self.build_message("KEY", key=encrypted_key_b64)
        print("send back pub key!")
        self.send_to_server(msg)
        self.transport_data.key = self.key

    def update_grid(self, to_remove, to_add):
        for point in to_remove:
            x, y, kind, p_id, ticket = point
            if ticket is not None:
                self.grid.pop((x, y, ticket), None)
            else:
                # this is unusual moment --> can't happen but still for the case it is
                print("TICKET = NONE")
                keys_to_remove = [k for k in self.grid.keys() if k[0] == x and k[1] == y]
                for k in keys_to_remove:
                    self.grid.pop(k, None)
        for point in to_add:
            self.grid[(point[0], point[1], point[4])] = (point[2], str(point[3]))

    def build_snakes_game_data(self):  # relay only on grid
        temp_snakes = {}
        for (x, y, ticket), definition in self.grid.items():
            kind = definition[0]
            if kind in (SNAKE_HEAD, SNAKE_BODY):
                p_id_str = definition[1]
                if p_id_str not in temp_snakes:
                    temp_snakes[p_id_str] = []
                # keep the ticket --> we need to sort the snake from head to tail
                # every part of his body is different ticket, head is 1 ....
                temp_snakes[p_id_str].append((float(x), float(y), ticket))

        self.target_snakes = {}  # (x,y)
        for p_id_str in temp_snakes:
            # sort the snake parts here
            temp_snakes[p_id_str].sort(key=lambda item: item[2], reverse=True)  # by ticket
            self.target_snakes[p_id_str] = [(item[0], item[1]) for item in temp_snakes[p_id_str]]

        # update camera position (my head)
        my_tid_str = str(self.tid)
        if my_tid_str in self.target_snakes and len(self.target_snakes[my_tid_str]) > 0:
            self.camera_x, self.camera_y = self.target_snakes[my_tid_str][0]
            if self.visual_camera_x == -1.0:
                self.visual_camera_x = float(self.camera_x)
                self.visual_camera_y = float(self.camera_y)

    def new_board_f(self, payload):
        with self.lock:
            self.grid = {}
            sync = payload.get("sync")
            # first ID here
            if "ID" in payload:
                self.last_board_id = payload.get("ID")
            elif "ID" in sync:
                self.last_board_id = sync.get("ID")
            # ----------------------------
            self.board_width, self.board_height = sync.get("board_size")
            self.tid_to_color = sync.get("players_color")
            # create surface
            if "walls" in sync:
                self.walls = sync.get("walls", [])
                self.water = sync.get("water", [])
                self.flowers = sync.get("flowers", [])

            for point in sync.get("full_grid"):
                self.grid[(point[0], point[1], point[4])] = (point[2], point[3])

            self.leaders = sync.get("leaders")
            if "length" in sync:
                self.snake_lengths = sync.get("length")
            in_game = False
            if "usernames" in sync:
                self.tid_to_username = sync.get("usernames")
                self.known_usernames.update(self.tid_to_username)
                if str(self.tid) in self.tid_to_username:
                    in_game = True

            self.build_snakes_game_data()
            if in_game:
                # should be, only to make sure
                self.state = STATE_GAME

    def id_f(self, payload):
        self.tid = payload.get("tid")

    def coins_f(self, payload):
        coins_amount = payload.get("amount")
        if coins_amount:
            self.last_coins = coins_amount - self.my_amount_of_coins
            self.my_amount_of_coins = coins_amount

    def ack_f(self, payload):
        subject = payload.get("subject")
        if subject == "login" or subject == "signup" or subject == "auto_login":
            self.state = STATE_LOBBY
            if "UDPport" in payload:
                self.UDP_port = payload.get("UDPport")
            self.my_amount_of_coins = payload.get("total_coins", 0)
            self.game_shop = payload.get("shop")
            self.items_i_own = payload.get("own")

            if "token" in payload and "user" in payload:
                # for auto login, if client want to be remembered he will get token and user, else, we remove the file
                got_token = payload.get("token")
                got_user = payload.get("user")
                if got_token:
                    save_settings_binary(got_user, got_token)
                else:
                    if os.path.exists("settings.bin"):
                        os.remove("settings.bin")

            if not self.UDP_obj:
                self.UDP_obj = ClientThreadUDP(self)
                self.UDP_obj.start()

        if subject == "buy":
            # buy approved!, my new data update (items and coins)
            coins = payload.get("coins")
            own = payload.get("own")
            self.my_amount_of_coins = coins
            self.items_i_own = own
            print(f"Buy successful! Coins left: {self.my_amount_of_coins}")

        if subject == "init":
            print("init arrived!")
            self.got_init = True

    def error_f(self, payload):
        num = payload.get("num")
        info = payload.get("info")
        print(num, ": ", info)
        self.error_num = num
        self.error_time = time.time()

    def prepare_for_new_game(self):
        self.state = STATE_LOBBY
        self.last_board_id = -1
        self.boosting = False
        self.last_direction = None
        self.color = None
        self.board_height = -1
        self.board_width = -1
        self.walls = []
        self.water = []
        self.tid_to_color = {}
        self.known_usernames = {}
        self.recent_deaths = []
        self.camera_x = -1
        self.camera_y = -1
        self.visual_camera_x = -1.0
        self.visual_camera_y = -1.0
        self.visual_snakes = {}
        self.snake_lengths = {}
        self.target_snakes = {}
        self.grid = {}
        self.alive = True
        self.leaders = None
        self.asking_server_for_sync = False
        self.pending_udp_updates.clear()

    def close(self):
        self.running = False
        if self.UDP_obj:
            self.UDP_obj.running = False
        # --- ---
        try:
            if self.state in [STATE_LOBBY, STATE_GAME]:
                self.send_to_server(self.build_message("LOGOUT", remember=True))
                print("LOGOUT SUCCESS!")
        except Exception:
            pass
        # ------------------------------------------
        try:
            self.sock.close()
            self.UDP_sock.close()
        except Exception as e:
            print(e)


def display_new_board(grid, screen, cli_obj, offset_x, offset_y):
    if cli_obj.camera_x != -1:
        # draw end of board lines
        world_rect = pygame.Rect(offset_x, offset_y, cli_obj.board_width * BLOCK_SIZE, cli_obj.board_height * BLOCK_SIZE)
        pygame.draw.rect(screen, (255, 0, 0), world_rect, 3)

        # draw only fruits and coins
        for (x, y, ticket), (kind, p_id_str) in grid.items():
            if kind == APPLE:
                # ticket --> apple value
                apple_x = offset_x + x * BLOCK_SIZE
                apple_y = offset_y + y * BLOCK_SIZE
                if -BLOCK_SIZE < apple_x < screen.get_width() + BLOCK_SIZE and -BLOCK_SIZE < apple_y < screen.get_height() + BLOCK_SIZE:
                    draw_fruit((kind, p_id_str, ticket), screen, apple_x, apple_y)
            if kind == COIN:
                coin_x = offset_x + x * BLOCK_SIZE
                coin_y = offset_y + y * BLOCK_SIZE
                if -BLOCK_SIZE < coin_x < screen.get_width() + BLOCK_SIZE and -BLOCK_SIZE < coin_y < screen.get_height() + BLOCK_SIZE:
                    screen.blit(COIN_SURFACE, (coin_x - 2, coin_y - 2))


def draw_fruit(definition, screen, o_x, o_y):
    value = definition[2]
    # kinds of apples by value
    if value == 1:
        screen.blit(APPLE_SURFACE, (o_x, o_y))
    elif value == 2:
        screen.blit(BLUE_APPLE, (o_x, o_y))
    elif value == 3:
        screen.blit(GREEN_APPLE, (o_x, o_y))
    elif value < 0:
        screen.blit(POISON_APPLE, (o_x, o_y))


def create_shop_icon_surface(size=35):
    """ מצייר אייקון של חנות קטנה עם גגון פסים """
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(surf, (160, 100, 60), (4, 15, size - 8, size - 15), border_radius=2)
    pygame.draw.rect(surf, (100, 50, 20), (size // 2 - 4, 20, 8, size - 20))
    pygame.draw.polygon(surf, (220, 50, 50), [(2, 15), (size - 2, 15), (size - 6, 5), (6, 5)])
    pygame.draw.polygon(surf, (240, 240, 240), [(10, 15), (16, 15), (18, 5), (14, 5)])
    pygame.draw.polygon(surf, (240, 240, 240), [(size - 16, 15), (size - 10, 15), (size - 14, 5), (size - 18, 5)])
    pygame.draw.rect(surf, (255, 215, 0), (size // 2 - 8, 2, 16, 6), border_radius=2)
    return surf


SHOP_ICON = create_shop_icon_surface(35)


def prepare_apple_surface():
    surf = pygame.Surface((BLOCK_SIZE, BLOCK_SIZE), pygame.SRCALPHA)
    center_x = BLOCK_SIZE // 2
    center_y = BLOCK_SIZE // 2
    radius = BLOCK_SIZE // 2 - 1
    pygame.draw.circle(surf, (255, 0, 0), (center_x, center_y), radius)
    pygame.draw.line(surf, (34, 139, 34), (center_x, 2), (center_x, 6), 2)
    pygame.draw.circle(surf, (255, 255, 255), (center_x - 3, center_y - 3), 2)
    return surf


def prepare_green_apple_surface():
    surf = pygame.Surface((BLOCK_SIZE, BLOCK_SIZE), pygame.SRCALPHA)
    center_x = BLOCK_SIZE // 2
    center_y = BLOCK_SIZE // 2
    radius = BLOCK_SIZE // 2 - 1
    pygame.draw.circle(surf, (0, 255, 0), (center_x, center_y), radius)
    pygame.draw.line(surf, (34, 139, 34), (center_x, 2), (center_x, 6), 2)
    pygame.draw.circle(surf, (255, 255, 255), (center_x - 3, center_y - 3), 2)
    return surf


def prepare_blue_apple_surface():
    surf = pygame.Surface((BLOCK_SIZE, BLOCK_SIZE), pygame.SRCALPHA)
    center_x = BLOCK_SIZE // 2
    center_y = BLOCK_SIZE // 2
    radius = BLOCK_SIZE // 2 - 1
    pygame.draw.circle(surf, (0, 0, 255), (center_x, center_y), radius)
    pygame.draw.line(surf, (34, 139, 34), (center_x, 2), (center_x, 6), 2)
    pygame.draw.circle(surf, (255, 255, 255), (center_x - 3, center_y - 3), 2)
    return surf


def prepare_poison_apple_surface():
    surf = pygame.Surface((BLOCK_SIZE, BLOCK_SIZE), pygame.SRCALPHA)
    center_x = BLOCK_SIZE // 2
    center_y = BLOCK_SIZE // 2
    radius = BLOCK_SIZE // 2 - 1
    pygame.draw.circle(surf, (138, 43, 226), (center_x, center_y), radius)
    pygame.draw.line(surf, (100, 100, 100), (center_x, 2), (center_x, 6), 2)
    pygame.draw.circle(surf, (0, 255, 0), (center_x, center_y + 1), 2)
    return surf


def create_coin_surface(block_size):
    surf_size = block_size + 4
    coin_surface = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
    center = surf_size // 2
    radius = block_size // 2
    base_gold = (210, 160, 30)  # צבע רקע הזהב
    light_gold = (255, 220, 100)  # אור למסגרת
    dark_gold = (140, 90, 10)  # צל למסגרת ולחריטה
    inner_gold = (190, 140, 20)  # צבע השטח הפנימי השקוע
    pygame.draw.circle(coin_surface, dark_gold, (center, center), radius)
    pygame.draw.circle(coin_surface, light_gold, (center - 1, center - 1), radius)
    pygame.draw.circle(coin_surface, base_gold, (center, center), radius - 1)
    pygame.draw.circle(coin_surface, light_gold, (center, center), radius - 3)
    pygame.draw.circle(coin_surface, dark_gold, (center - 1, center - 1), radius - 3)
    pygame.draw.circle(coin_surface, inner_gold, (center, center), radius - 4)
    font = pygame.font.SysFont("Arial", radius * 2 - 2, bold=True)
    dollar_light = font.render("$", True, light_gold)
    coin_surface.blit(dollar_light,
                      (center - dollar_light.get_width() // 2, center - dollar_light.get_height() // 2 + 1))
    dollar_dark = font.render("$", True, dark_gold)
    coin_surface.blit(dollar_dark, (center - dollar_dark.get_width() // 2, center - dollar_dark.get_height() // 2))
    return coin_surface


def draw_leaderboard(screen, leaders, tid_to_color, my_tid, snake_lengths, tid_to_username):
    if not leaders:
        return
    start_x = screen.get_width() - 170
    start_y = 10
    screen.blit(LEADERBOARD_OVERLAY, (start_x, start_y))
    title = GLOBAL_FONT.render("LEADERBOARD", True, (255, 255, 255))
    screen.blit(title, (start_x + 10, start_y + 10))
    for i, entry in enumerate(leaders):
        p_id = str(entry[0])
        score = entry[1]
        colors = tid_to_color.get(p_id, [(200, 200, 200)])
        color = colors[0] if colors else (200, 200, 200)
        prefix = "-> " if p_id == str(my_tid) else ""
        player_name = tid_to_username.get(p_id, f"Player {p_id}")
        txt = GLOBAL_FONT.render(f"{i + 1}. {prefix}{player_name}: {score}", True, color)
        screen.blit(txt, (start_x + 10, start_y + 35 + (i * 20)))
    # my score in tne left down corner
    my_id_str = str(my_tid)
    if my_id_str in snake_lengths:
        my_score = snake_lengths[my_id_str]
        my_colors = tid_to_color.get(my_id_str, [(255, 255, 255)])
        my_color = my_colors[0] if my_colors else (255, 255, 255)
        txt = GLOBAL_FONT.render(f"score: {my_score}", True, my_color)
        screen.blit(txt, (10, screen.get_height() - 30))


def draw_minimap(screen, cli_obj, local_target_snakes):  # הוספנו פרמטר
    MAP_SIZE = 100
    map_x = screen.get_width() - MAP_SIZE - BLOCK_SIZE
    map_y = screen.get_height() - MAP_SIZE - BLOCK_SIZE
    overlay = pygame.Surface((MAP_SIZE, MAP_SIZE), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 120))
    screen.blit(overlay, (map_x, map_y))

    border_color = (255, 255, 255)
    border_thickness = 1
    world_rect_on_screen = pygame.Rect(map_x, map_y, MAP_SIZE, MAP_SIZE)
    pygame.draw.rect(screen, border_color, world_rect_on_screen, border_thickness)

    for p_id_str, segments in local_target_snakes.items():
        if len(segments) > 0:
            w_x, w_y = segments[0]  # 0 is head
            rel_x = (w_x / cli_obj.board_width) * MAP_SIZE
            rel_y = (w_y / cli_obj.board_height) * MAP_SIZE
            color = cli_obj.tid_to_color.get(p_id_str, (255, 255, 255))[0]
            pygame.draw.circle(screen, color, (int(map_x + rel_x), int(map_y + rel_y)), 2)


def prepare_flower_surface():
    surf = pygame.Surface((15, 15))
    colors = {
        '1': (15, 55, 45),  # צל עמוק עם נגיעה כחלחלה (תחושה של אדמה לחה)
        '2': (30, 100, 60),  # בסיס הדשא - ירוק אמרלד עשיר וקריר
        '3': (55, 160, 80),  # עלי דשא רעננים
        '4': (95, 210, 110)  # הברקות אור רכות (ירוק-מנטה במקום צהוב)
    }
    pixel_map = [
        "222122222122222",
        "233221233221222",
        "134322234322332",
        "223221223221343",
        "212233222212232",
        "222134322223221",
        "222223221234322",
        "123322233223221",
        "213432134322222",
        "222322223221332",
        "332221222212343",
        "343222332222232",
        "232211343212221",
        "222222232223322",
        "212222222113432"
    ]
    for y, row in enumerate(pixel_map):
        for x, char in enumerate(row):
            pygame.draw.rect(surf, colors[char], (x, y, 1, 1))
    return surf


def prepare_rock_wall_surface():
    surf = pygame.Surface((BLOCK_SIZE, BLOCK_SIZE))
    surf.fill((25, 25, 25))
    rock1 = (105, 105, 110)
    rock2 = (85, 85, 90)
    rock3 = (120, 120, 125)
    rock4 = (95, 95, 95)
    pygame.draw.rect(surf, rock1, (1, 1, 8, 7), border_radius=3)
    pygame.draw.rect(surf, rock2, (10, 1, 4, 8), border_radius=2)
    pygame.draw.rect(surf, rock3, (1, 9, 6, 5), border_radius=2)
    pygame.draw.rect(surf, rock4, (8, 10, 6, 4), border_radius=2)
    pygame.draw.circle(surf, (34, 100, 34), (8, 9), 1)
    return surf


def prepare_deep_ice_surface():
    surf = pygame.Surface((BLOCK_SIZE, BLOCK_SIZE))
    surf.fill((45, 115, 180))
    pygame.draw.rect(surf, (55, 130, 195), (2, 2, BLOCK_SIZE - 4, BLOCK_SIZE - 4))
    pygame.draw.line(surf, (90, 165, 220), (0, 0), (BLOCK_SIZE, 0), 1)
    pygame.draw.line(surf, (90, 165, 220), (0, 0), (0, BLOCK_SIZE), 1)
    pygame.draw.line(surf, (25, 75, 125), (0, BLOCK_SIZE - 1), (BLOCK_SIZE, BLOCK_SIZE - 1), 1)
    pygame.draw.line(surf, (25, 75, 125), (BLOCK_SIZE - 1, 0), (BLOCK_SIZE - 1, BLOCK_SIZE), 1)
    pygame.draw.lines(surf, (110, 180, 230), False, [(1, 3), (5, 7), (9, 13)], 1)
    pygame.draw.line(surf, (70, 140, 200), (5, 7), (11, 4), 1)
    pygame.draw.rect(surf, (160, 210, 240), (10, 10, 2, 1))
    return surf


def prepare_dirt_surface():
    surf = pygame.Surface((BLOCK_SIZE, BLOCK_SIZE))
    surf.fill((45, 35, 25))
    pygame.draw.rect(surf, (60, 50, 40), (2, 3, 3, 2))  # אבן בהירה
    pygame.draw.rect(surf, (35, 25, 15), (10, 8, 2, 2))  # גוש כהה
    pygame.draw.rect(surf, (55, 45, 35), (5, 12, 4, 2))  # אבן שטוחה
    return surf


BACKGROUND_TILE = prepare_dirt_surface()
WATER_SURFACE = prepare_deep_ice_surface()
WALL_SURFACE = prepare_rock_wall_surface()
FLOWER_SURFACE = prepare_flower_surface()

APPLE_SURFACE = prepare_apple_surface()
BLUE_APPLE = prepare_blue_apple_surface()
GREEN_APPLE = prepare_green_apple_surface()
POISON_APPLE = prepare_poison_apple_surface()
COIN_SURFACE = create_coin_surface(BLOCK_SIZE)
COIN_SURFACE_FOR_SHOW = create_coin_surface(25)


pygame.font.init()
GLOBAL_FONT = pygame.font.SysFont(None, 24, bold=False)

LEADERBOARD_OVERLAY = pygame.Surface((160, 140), pygame.SRCALPHA)
LEADERBOARD_OVERLAY.fill((0, 0, 0, 160))

MINIMAP_OVERLAY = pygame.Surface((100, 100), pygame.SRCALPHA)
MINIMAP_OVERLAY.fill((0, 0, 0, 120))


def update_and_draw_world1(cli_obj, screen, bg_surface, lerp_factor):
    """update all snake positions, bring them closer to their target position (x,y)"""
    """draw the world"""
    with cli_obj.lock:
        if cli_obj.camera_x != -1:
            cli_obj.visual_camera_x += (cli_obj.camera_x - cli_obj.visual_camera_x) * lerp_factor
            cli_obj.visual_camera_y += (cli_obj.camera_y - cli_obj.visual_camera_y) * lerp_factor

        # we need to copy all the self items inside the lock to use them out of it, keep it fast
        local_cam_x = cli_obj.visual_camera_x
        local_cam_y = cli_obj.visual_camera_y

        # target_snakes = dict |key = tid|, |val = [(x,y),... -> sort from head to tail| , this is the target x,y
        # visual_snakes = current data on screen --> x,y...
        local_target_snakes = dict(cli_obj.target_snakes)
        local_grid = dict(cli_obj.grid)
        local_tid_to_color = dict(cli_obj.tid_to_color)
        local_tid_to_username = dict(cli_obj.tid_to_username)
        local_snake_lengths = dict(cli_obj.snake_lengths)
        local_leaders = list(cli_obj.leaders) if cli_obj.leaders else None
        local_tid = cli_obj.tid

        # update, keep only the snakes that we have data on them
        active_tids = list(local_target_snakes.keys())
        cli_obj.visual_snakes = {k: v for k, v in cli_obj.visual_snakes.items() if k in active_tids}  # k = tid

        # now we need to add new ones, so we check if we have new ones
        for p_id_str, target_list in local_target_snakes.items():
            if p_id_str not in cli_obj.visual_snakes and target_list:
                cli_obj.visual_snakes[p_id_str] = [list(p) for p in target_list]  # need list to change values
        local_visual_snakes = dict(cli_obj.visual_snakes)

    for p_id_str, target_list in local_target_snakes.items():
        if not target_list:
            continue
        # get snake body on screen
        v_snake = local_visual_snakes.get(p_id_str)
        if not v_snake:
            continue

        # if snake length has grown we add in the tail place another part till we reach the right length
        while len(v_snake) < len(target_list):
            v_snake.append(list(v_snake[-1]))
        # if snake became smaller we remove tail till it reach the right length
        if len(v_snake) > len(target_list):
            del v_snake[len(target_list):]

        # now we have the right data of the snake, so we now move it!
        # we bring it closer to the target location x,y
        for i in range(len(v_snake)):
            t_x, t_y = target_list[i]
            v_snake[i][0] += (t_x - v_snake[i][0]) * lerp_factor  # x
            v_snake[i][1] += (t_y - v_snake[i][1]) * lerp_factor  # y

    # we moved all so now we draw
    offset_x = screen.get_width() // 2 - (local_cam_x * BLOCK_SIZE)
    offset_y = screen.get_height() // 2 - (local_cam_y * BLOCK_SIZE)

    screen.blit(bg_surface, (offset_x, offset_y))  # background
    display_new_board(local_grid, screen, cli_obj, offset_x, offset_y)  # fruits, coins

    # draw snakes
    for p_id_str, segments in local_visual_snakes.items():
        color_list = local_tid_to_color.get(p_id_str)
        if not color_list:
            continue
        head_color = tuple(color_list[0])
        for i in range(len(segments) - 1, -1, -1):  # tail to head
            v_x, v_y = segments[i]
            screen_x = screen.get_width() // 2 - (local_cam_x * BLOCK_SIZE) + (v_x * BLOCK_SIZE)
            screen_y = screen.get_height() // 2 - (local_cam_y * BLOCK_SIZE) + (v_y * BLOCK_SIZE)

            if -BLOCK_SIZE * 2 < screen_x < screen.get_width() + BLOCK_SIZE * 2 and -BLOCK_SIZE * 2 < screen_y < screen.get_height() + BLOCK_SIZE * 2:
                center = (int(screen_x + BLOCK_SIZE / 2), int(screen_y + BLOCK_SIZE / 2))
                base_radius = int(BLOCK_SIZE / 1.4)

                if i == 0:
                    player_name = local_tid_to_username.get(p_id_str, f"Player {p_id_str}")
                    name_surf = GLOBAL_FONT.render(player_name, True, (255, 255, 255))
                    name_x = center[0] - name_surf.get_width() // 2
                    name_y = center[1] - base_radius - 20
                    screen.blit(name_surf, (name_x, name_y))

                    pygame.draw.circle(screen, (30, 30, 30), center, base_radius + 2)
                    pygame.draw.circle(screen, head_color, center, base_radius + 1)

                    dx, dy = 1, 0
                    if len(segments) > 1:
                        nx, ny = segments[1]
                        dx, dy = v_x - nx, v_y - ny
                        length = (dx ** 2 + dy ** 2) ** 0.5
                        if length != 0:
                            dx, dy = dx / length, dy / length

                    eye1_pos = (center[0] + int(dx * 4 - dy * 5), center[1] + int(dy * 4 + dx * 5))
                    eye2_pos = (center[0] + int(dx * 4 + dy * 5), center[1] + int(dy * 4 - dx * 5))
                    pupil1_pos = (center[0] + int(dx * 6 - dy * 5), center[1] + int(dy * 6 + dx * 5))
                    pupil2_pos = (center[0] + int(dx * 6 + dy * 5), center[1] + int(dy * 6 - dx * 5))

                    pygame.draw.circle(screen, (255, 255, 255), eye1_pos, 4)
                    pygame.draw.circle(screen, (255, 255, 255), eye2_pos, 4)
                    pygame.draw.circle(screen, (0, 0, 0), pupil1_pos, 2)
                    pygame.draw.circle(screen, (0, 0, 0), pupil2_pos, 2)
                else:
                    body_color = color_list[i % len(color_list)]
                    darker_color = (max(0, body_color[0] - 60), max(0, body_color[1] - 60), max(0, body_color[2] - 60))
                    pygame.draw.circle(screen, darker_color, center, base_radius)
                    pygame.draw.circle(screen, body_color, center, base_radius - 2)

    # leaders and map
    draw_leaderboard(screen, local_leaders, local_tid_to_color, local_tid, local_snake_lengths, local_tid_to_username)
    draw_minimap(screen, cli_obj, local_target_snakes)


def draw_dead(cli_obj, screen, font_death, death_notifications):
    # death animation
    # only if snake die
    if cli_obj.recent_deaths:
        for dead_name in cli_obj.recent_deaths:
            text_surf = font_death.render(f"{dead_name} died!", True, (255, 255, 255)).convert_alpha()
            death_notifications.append([text_surf, 9, 500, 255.0])
        cli_obj.recent_deaths.clear()

    for note in death_notifications[:]:
        note[2] -= 1.0  # move it up
        note[3] -= 3.0  # alpha

        if note[3] <= 0:
            death_notifications.remove(note)  # if we can't see, remove it
        else:
            note[0].set_alpha(int(note[3]))
            screen.blit(note[0], (note[1], int(note[2])))


def cli_game_loop(cli_obj):
    width = cli_obj.board_width * BLOCK_SIZE
    height = cli_obj.board_height * BLOCK_SIZE
    screen = pygame.display.set_mode((600, 600))
    clock = pygame.time.Clock()
    # background surface
    bg_surface = pygame.Surface((width, height))

    # ----- create surface ------ #
    for x in range(cli_obj.board_width + 1):
        for y in range(cli_obj.board_height + 1):
            bg_surface.blit(BACKGROUND_TILE, (x * BLOCK_SIZE, y * BLOCK_SIZE))
    for wx, wy in cli_obj.walls:
        bg_surface.blit(WALL_SURFACE, (wx * BLOCK_SIZE, wy * BLOCK_SIZE))
    for wx, wy in cli_obj.water:
        bg_surface.blit(WATER_SURFACE, (wx * BLOCK_SIZE, wy * BLOCK_SIZE))
    for wx, wy in cli_obj.flowers:
        bg_surface.blit(FLOWER_SURFACE, (wx * BLOCK_SIZE, wy * BLOCK_SIZE))
    # ----- create surface ------ #

    msg_id = 1
    lerp_factor = 0.2

    current_msg = None
    tick_id = 0
    INTERVAL = 4
    times_sent = 0

    # for death animation
    font_death = GLOBAL_FONT
    death_notifications = []
    # -------------------

    while cli_obj.alive:
        screen.fill((0, 0, 0))
        # maybe draw here the dead snakes
        update_and_draw_world1(cli_obj, screen, bg_surface, lerp_factor)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                cli_obj.close()
                cli_obj.join()
                pygame.quit()
                raise SystemExit
            if event.type == pygame.KEYDOWN:
                direction = None
                if event.key == pygame.K_UP:
                    direction = "U"
                elif event.key == pygame.K_DOWN:
                    direction = "D"
                elif event.key == pygame.K_LEFT:
                    direction = "L"
                elif event.key == pygame.K_RIGHT:
                    direction = "R"
                if direction:
                    cli_obj.last_direction = direction
                    msg_id += 1
                    times_sent = 0
                    current_msg = cli_obj.build_message("DIR", direction=direction, ID=msg_id,
                                                        tid=cli_obj.tid, boost=cli_obj.boosting)
                    cli_obj.send_to_server_UDP(current_msg)
                elif event.key == pygame.K_SPACE and cli_obj.last_direction:  # maybe only space without direction?
                    msg_id += 1
                    times_sent = 0
                    cli_obj.boosting = True
                    current_msg = cli_obj.build_message("DIR", direction=cli_obj.last_direction, ID=msg_id,
                                                        tid=cli_obj.tid, boost=cli_obj.boosting)
                    cli_obj.send_to_server_UDP(current_msg)
            if event.type == pygame.KEYUP and cli_obj.last_direction:
                if event.key == pygame.K_SPACE:
                    msg_id += 1
                    times_sent = 0
                    cli_obj.boosting = False
                    current_msg = cli_obj.build_message("DIR", direction=cli_obj.last_direction, ID=msg_id,
                                                        tid=cli_obj.tid, boost=cli_obj.boosting)
                    cli_obj.send_to_server_UDP(current_msg)

        draw_dead(cli_obj, screen, font_death, death_notifications)
        if current_msg and tick_id % INTERVAL == 0 and times_sent < 3:
            times_sent += 1
            cli_obj.send_to_server_UDP(current_msg)
        tick_id += 1
        pygame.display.flip()
        clock.tick(60)

    # fade out animation
    fade_surface = pygame.Surface((600, 600))
    fade_surface.fill((0, 0, 0))
    for i in range(60):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                cli_obj.close()
                cli_obj.join()
                pygame.quit()
                raise SystemExit
        screen.fill((0, 0, 0))
        update_and_draw_world1(cli_obj, screen, bg_surface, lerp_factor)
        # dark draw
        fade_surface.set_alpha(i * 4)
        screen.blit(fade_surface, (0, 0))
        pygame.display.flip()
        clock.tick(60)
    cli_obj.send_to_server(cli_obj.build_message("LEAVE_GAME"))


def draw_calm_button(screen, text_surface, rect, base_color, mouse_pos):
    """ מצייר כפתור מינימליסטי, שטוח (Flat), ללא תלת-מימד וללא שינוי צבע """
    is_hover = rect.collidepoint(mouse_pos)
    border_color = (255, 255, 255) if is_hover else (100, 100, 100)
    pygame.draw.rect(screen, base_color, rect, border_radius=10)
    pygame.draw.rect(screen, border_color, rect, width=2, border_radius=10)
    text_rect = text_surface.get_rect(center=rect.center)
    screen.blit(text_surface, text_rect)


def draw_premium_button(screen, text_surface, rect, base_color, hover_color, mouse_pos):
    """draw buttons, 3d and glow """
    is_hover = rect.collidepoint(mouse_pos)
    color = hover_color if is_hover else base_color
    y_offset = -4 if is_hover else 0
    shadow_rect = pygame.Rect(rect.x, rect.y + 6, rect.width, rect.height)
    pygame.draw.rect(screen, (15, 15, 20), shadow_rect, border_radius=15)
    btn_rect = pygame.Rect(rect.x, rect.y + y_offset, rect.width, rect.height)
    pygame.draw.rect(screen, color, btn_rect, border_radius=15)
    light_color = (min(255, color[0] + 60), min(255, color[1] + 60), min(255, color[2] + 60))
    pygame.draw.rect(screen, light_color, btn_rect, width=3, border_radius=15)
    text_rect = text_surface.get_rect(center=btn_rect.center)
    screen.blit(text_surface, text_rect)


def home_screen(screen, client):
    global COLOR_PACK
    pygame.display.set_caption("SNAKE ONLINE")

    font_logo = pygame.font.SysFont("Segoe UI", 65, bold=True)
    font_play = pygame.font.SysFont("Arial Black", 45)
    font_button = pygame.font.SysFont(None, 40)
    font_small = pygame.font.SysFont(None, 24)

    text_logo = font_logo.render("SNAKE ONLINE", True, (255, 255, 255))
    text_logo_rect = text_logo.get_rect(center=(300, 150))

    logout_btn_rect = pygame.Rect(10, 60, 100, 35)
    logout_text = font_small.render("LOGOUT", True, (255, 255, 255))

    play_button_rect = pygame.Rect(200, 480, 200, 70)
    play_text = font_play.render("PLAY", True, (255, 255, 255))

    color_btn_rect = pygame.Rect(150, 380, 300, 60)
    color_btn_text = font_button.render("Create Skin", True, (255, 255, 255))

    if COLOR_PACK:
        pattern = list(COLOR_PACK)
    else:
        pattern = [(255, 255, 255)]

    # ---- shop
    show_color_picker = False
    show_shop = False
    shop_page = 0
    shop_item_rects = {}
    prev_page_rect = pygame.Rect(0, 0, 0, 0)
    next_page_rect = pygame.Rect(0, 0, 0, 0)
    total_shop_pages = 1
    selected_shop_item = None
    can_afford = False
    # ---- shop

    # shop button place
    shop_btn_rect = pygame.Rect(540, 15, 40, 40)

    popup_rect = pygame.Rect(100, 80, 400, 440)
    done_btn_rect = pygame.Rect(230, 450, 140, 50)
    done_text = font_button.render("DONE", True, (255, 255, 255))
    done_text_rect = done_text.get_rect(center=done_btn_rect.center)

    clock = pygame.time.Clock()
    waiting_for_user = True
    bg_snakes = [BgSnake(600, 600) for _ in range(15)]
    # coins animation prep
    flying_coins = []
    TARGET_X, TARGET_Y = 20.0, 30.0
    # coins animation prep
    while waiting_for_user:
        screen.fill(COLOR_BG)
        # screen animation
        for s in bg_snakes:
            s.update()
            s.draw(screen)

        mx, my = pygame.mouse.get_pos()

        # coins
        screen.blit(text_logo, text_logo_rect)
        screen.blit(COIN_SURFACE_FOR_SHOW, (10, 20))
        coin_text = font_button.render(f" {client.my_amount_of_coins}", True, (255, 215, 0))
        screen.blit(coin_text, (40, 20))

        # ========================================== coins animation
        if client.last_coins > 0:
            num_coins_to_show = min(client.last_coins, 15)
            for i in range(num_coins_to_show):
                start_x = 300 + random.randint(-100, 100)
                start_y = 300 + random.randint(-100, 100)
                delay = i * 3
                flying_coins.append([float(start_x), float(start_y), delay])
            client.last_coins = 0
        for f_coin in flying_coins[:]:
            if f_coin[2] > 0:  # check turns (delay passed?)
                f_coin[2] -= 1
                screen.blit(COIN_SURFACE_FOR_SHOW, (int(f_coin[0]), int(f_coin[1])))
            else:
                speed = 0.15
                f_coin[0] += (TARGET_X - f_coin[0]) * speed
                f_coin[1] += (TARGET_Y - f_coin[1]) * speed
                screen.blit(COIN_SURFACE_FOR_SHOW, (int(f_coin[0]), int(f_coin[1])))
                dist = math.hypot(TARGET_X - f_coin[0], TARGET_Y - f_coin[1])
                if dist < 10:  # arrived
                    flying_coins.remove(f_coin)
        # ========================================== coins animation

        if not show_color_picker and not show_shop:
            # main screen



            # drawing:
            # logout button
            draw_premium_button(screen, logout_text, logout_btn_rect, (150, 50, 50), (200, 70, 70), (mx, my))
            # play button
            draw_premium_button(screen, play_text, play_button_rect, (0, 160, 60), (0, 210, 80), (mx, my))
            # create skin button
            draw_premium_button(screen, color_btn_text, color_btn_rect, (55, 60, 75), (80, 90, 115), (mx, my))
            # shop button
            draw_premium_button(screen, SHOP_ICON, shop_btn_rect, (50, 50, 60), (70, 70, 85), (mx, my))

            # snake body drawing
            start_x, center_y, spacing = 196, 310, 16
            for i in range(13, -1, -1):  # tail to head
                hx = start_x + (i * spacing)
                radius = 12 if i == 0 else 10  # for head
                # body part
                pygame.draw.circle(screen, pattern[i % len(pattern)], (hx, center_y), radius)
                pygame.draw.circle(screen, (0, 0, 0), (hx, center_y), radius, 1)
                # eyes
                if i == 0:
                    for dy in [-5, 5]:
                        pygame.draw.circle(screen, (255, 255, 255), (hx - 4, center_y + dy), 3)
                        pygame.draw.circle(screen, (0, 0, 0), (hx - 5, center_y + dy), 1)

        elif show_color_picker:
            # create skin screen

            # dark see through background
            dim_surface = pygame.Surface((600, 600), pygame.SRCALPHA)
            dim_surface.fill((0, 0, 0, 200))
            screen.blit(dim_surface, (0, 0))

            pygame.draw.rect(screen, (50, 50, 50), popup_rect, border_radius=15)
            pygame.draw.rect(screen, (200, 200, 200), popup_rect, width=3, border_radius=15)

            # title
            title = font_button.render("Your Snake:", True, (255, 255, 255))
            screen.blit(title, (120, 100))

            hint = font_small.render("(Click a block to remove)", True, (150, 150, 150))
            screen.blit(hint, (120, 130))

            preview_rects = []
            start_x, start_y = 180, 175
            spacing = 18
            # for mouse, we need rects
            for i in range(len(pattern)):
                cx = start_x + (i * spacing)
                cy = start_y
                r = pygame.Rect(cx - 12, cy - 12, 24, 24)
                preview_rects.append(r)
            # tail to head
            for i in range(len(pattern) - 1, -1, -1):
                c = pattern[i]
                cx = start_x + (i * spacing)
                cy = start_y
                radius = 13 if i == 0 else 11  # for head
                # part draw
                pygame.draw.circle(screen, c, (cx, cy), radius)
                pygame.draw.circle(screen, (0, 0, 0) if i == 0 else (0, 0, 0), (cx, cy), radius, 1)
                # eyes
                if i == 0:
                    pygame.draw.circle(screen, (255, 255, 255), (cx - 5, cy - 5), 3)
                    pygame.draw.circle(screen, (255, 255, 255), (cx - 5, cy + 5), 3)
                    pygame.draw.circle(screen, (0, 0, 0), (cx - 6, cy - 5), 1)
                    pygame.draw.circle(screen, (0, 0, 0), (cx - 6, cy + 5), 1)

            # color palette --> only what I own
            my_palette = []
            if client.game_shop and client.items_i_own:
                for item_id in client.items_i_own:
                    if item_id in client.game_shop:
                        my_palette.append(client.game_shop[item_id]["rgb"])
            else:
                my_palette = [(255, 255, 255)]
            # page style --> more colors --> smaller circles
            num_colors = len(my_palette)
            if num_colors <= 12:
                cols = 4
                spacing = 70
                circle_radius = 30
            else:
                cols = 5
                spacing = 54
                circle_radius = 23

            grid_width = cols * spacing
            start_x = popup_rect.x + (popup_rect.width - grid_width) // 2
            start_y = 220

            grid_rects = []
            for i in range(num_colors):
                row, col = i // cols, i % cols
                grid_rects.append(pygame.Rect(start_x + col * spacing, start_y + row * spacing, spacing, spacing))

            # palette draw
            for i, color in enumerate(my_palette):
                cx, cy = grid_rects[i].center
                pygame.draw.circle(screen, color, (cx, cy), circle_radius)
                pygame.draw.circle(screen, (0, 0, 0), (cx, cy), circle_radius, 2)
            # done button
            draw_premium_button(screen, done_text, done_btn_rect, (0, 150, 0), (0, 200, 0), (mx, my))

        elif show_shop:
            # shop screen
            shop_item_rects, prev_page_rect, next_page_rect, total_shop_pages, close_btn_rect, buy_btn_rect, can_afford = build_shop(
                client, screen, font_button, popup_rect, font_small, shop_page, selected_shop_item, (mx, my))
        # error box draw
        if client.error_num:
            if time.time() - client.error_time < 5 and client.error_time != 0:  # 5 second
                draw_modern_error(screen, ERROR_DICT[client.error_num], client.error_time)
            else:
                client.error_num = ""
                client.error_time = 0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                client.close()
                client.join()
                pygame.quit()
                raise SystemExit

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if logout_btn_rect.collidepoint(event.pos):
                    client.send_to_server(client.build_message("LOGOUT", remember=False))
                    if os.path.exists("settings.bin"):
                        os.remove("settings.bin")
                    client.state = STATE_HANDSHAKE
                    client.alive = False
                    client.running = False
                    waiting_for_user = False
                    return None
                if client.error_num:
                    close_btn_rect = pygame.Rect(470, 30, 30, 30)
                    if close_btn_rect.collidepoint(event.pos):
                        client.error_num = ""
                        continue

                if not show_color_picker and not show_shop:
                    if play_button_rect.collidepoint(event.pos):  # on play
                        waiting_for_user = False
                    elif color_btn_rect.collidepoint(event.pos):  # on create snake
                        show_color_picker = True
                    elif shop_btn_rect.collidepoint(event.pos):  # on shop
                        show_shop = True
                elif show_color_picker:
                    # in create snake
                    clicked_something = False
                    if done_btn_rect.collidepoint(event.pos):
                        if len(pattern) == 0:
                            pattern.append((255, 255, 255))
                        COLOR_PACK = list(pattern)
                        show_color_picker = False
                        clicked_something = True

                    for i, rect in enumerate(grid_rects):
                        if rect.collidepoint(event.pos):
                            if len(pattern) < 14:  # max
                                pattern.append(my_palette[i])
                            clicked_something = True
                            break

                    for i, rect in enumerate(preview_rects):
                        if rect.collidepoint(event.pos):
                            pattern.pop(i)
                            clicked_something = True
                            break

                    if not clicked_something and not popup_rect.collidepoint(event.pos):
                        if len(pattern) == 0:
                            pattern.append((255, 255, 255))
                        show_color_picker = False
                elif show_shop:
                    # shop screen
                    if close_btn_rect.collidepoint(event.pos):
                        show_shop = False
                        shop_page = 0
                        selected_shop_item = None
                    elif prev_page_rect.collidepoint(event.pos) and shop_page > 0:
                        shop_page -= 1
                        selected_shop_item = None
                    elif next_page_rect.collidepoint(event.pos) and shop_page < total_shop_pages - 1:
                        shop_page += 1
                        selected_shop_item = None
                    # buy check
                    elif buy_btn_rect and buy_btn_rect.collidepoint(event.pos) and selected_shop_item:
                        if not (client.items_i_own and selected_shop_item in client.items_i_own):
                            if can_afford:
                                print(f"Buying: {selected_shop_item}")
                                client.send_to_server(client.build_message("BUY", item_id=selected_shop_item))
                    else:
                        clicked_on_item = False
                        for item_id, rect in shop_item_rects.items():
                            if rect.collidepoint(event.pos):
                                selected_shop_item = item_id  # item_id --> "c_red"
                                clicked_on_item = True
                                break
                        if not clicked_on_item and popup_rect.collidepoint(event.pos):
                            selected_shop_item = None

        pygame.display.flip()
        clock.tick(30)

    # play button pressed, prepare for game
    client.send_to_server(client.build_message("COLOR", color=pattern))
    # load screen surface draw
    spinner = LoadingSpinner()

    while client.state == STATE_LOBBY:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                client.close()
                client.join()
                pygame.quit()
                raise SystemExit
        screen.fill((20, 20, 25))
        # draw loading animation
        spinner.draw(screen, "Waiting for a spot...")

        pygame.display.flip()
        clock.tick(30)
    # STATE GAME --> now we play!
    client.tid_to_color[str(client.tid)] = pattern
    return client


def handle_auth_action(state, email, password, client_obj):
    if client_obj.state != STATE_AUTH:
        # maybe animation here
        # print("Waiting for secure connection...")
        return
    # get fingerprint, and send with msg
    f_print = get_device_fingerprint()
    rem = client_obj.should_remember
    if state == STATE_LOGIN:
        msg = client_obj.build_message("LOGIN", email=email, password=password, device_id=f_print, remember_me=rem)
    else:
        msg = client_obj.build_message("SIGNUP", email=email, password=password, device_id=f_print, remember_me=rem)
    client_obj.send_to_server(msg)


def sign_in_screen(screen, client_obj):
    current_state = STATE_LOGIN
    clock = pygame.time.Clock()

    email_in = InputBox(150, 220, 300, 40, "Username")
    pass_in = InputBox(150, 290, 300, 40, "Password", is_password=True)
    confirm_in = InputBox(150, 360, 300, 40, "Confirm Password", is_password=True)
    font_small = pygame.font.SysFont("Segoe UI", 18)

    bg_snakes = [BgSnake(600, 600) for _ in range(8)]
    rem_box = CheckBox(150, 340)

    while True:
        screen.fill(COLOR_BG)
        # screen animation
        for s in bg_snakes:
            s.update()
            s.draw(screen)

        # draw remember me button by state
        if current_state == STATE_LOGIN:
            rem_box.rect.y = 345
        else:
            rem_box.rect.y = 415
        rem_box.draw(screen)

        # draw by state
        if current_state == STATE_LOGIN:
            draw_text(screen, "SIGN IN", 300, 100, 50, True)
            email_in.draw(screen)
            pass_in.draw(screen)
            btn_rect = draw_button(screen, "LOGIN", 200, 380, 200, 50, (76, 175, 80))
            signup_link = draw_link(screen, "No account? Create one", 300, 450, font_small)
        elif current_state == STATE_SIGNUP:
            draw_text(screen, "CREATE ACCOUNT", 300, 100, 40, True)
            email_in.draw(screen)
            pass_in.draw(screen)
            confirm_in.draw(screen)
            btn_rect = draw_button(screen, "SIGN UP", 200, 455, 200, 50, (33, 150, 243))
            signup_link = draw_link(screen, "Back to Login", 300, 520, font_small)

        # error bow draw
        if client_obj.error_num:
            if time.time() - client_obj.error_time < 5 and client_obj.error_time != 0:  # 5 second
                draw_modern_error(screen, ERROR_DICT[client_obj.error_num], client_obj.error_time)
            else:
                client_obj.error_num = ""
                client_obj.error_time = 0

        # events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            email_in.handle_event(event)
            pass_in.handle_event(event)
            rem_box.handle_event(event)

            if current_state == STATE_SIGNUP:
                confirm_in.handle_event(event)

            if event.type == pygame.MOUSEBUTTONDOWN:
                if client_obj.error_num:
                    close_btn_rect = pygame.Rect(470, 30, 30, 30)
                    if close_btn_rect.collidepoint(event.pos):
                        client_obj.error_num = ""
                        continue

                if btn_rect.collidepoint(event.pos):
                    if current_state == STATE_SIGNUP and pass_in.text != confirm_in.text:
                        print("Passwords don't match!")
                        client_obj.error_num = "008"
                        client_obj.error_time = time.time()
                        continue

                    # connection
                    client_obj.should_remember = rem_box.checked
                    handle_auth_action(current_state, email_in.text, pass_in.text, client_obj)

                if signup_link.collidepoint(event.pos):
                    current_state = STATE_SIGNUP if current_state == STATE_LOGIN else STATE_LOGIN

        if client_obj.state == STATE_LOBBY:
            return True

        pygame.display.flip()
        clock.tick(60)


def build_shop(cli_obj, screen, font_button, popup_rect, font_small, shop_page, selected_item, x_y_pos):
    dim_surface = pygame.Surface((600, 600), pygame.SRCALPHA)
    dim_surface.fill((0, 0, 0, 210))
    screen.blit(dim_surface, (0, 0))

    pygame.draw.rect(screen, (35, 35, 40), popup_rect, border_radius=15)
    pygame.draw.rect(screen, (255, 215, 0), popup_rect, width=3, border_radius=15)

    title = font_button.render("PREMIUM SHOP", True, (255, 215, 0))
    screen.blit(title, (popup_rect.centerx - title.get_width() // 2, popup_rect.y + 15))

    rarity_colors = {
        "Uncommon": (50, 205, 50),
        "Rare": (30, 144, 255),
        "Epic": (148, 0, 211),
        "Legendary": (255, 140, 0),
        "Mythic": (255, 20, 147)
    }

    font_micro = pygame.font.SysFont(None, 18)

    # only items that in the shop
    items_to_show = [(k, v) for k, v in cli_obj.game_shop.items() if v.get("price", 0) > 0]
    items_to_show.sort(key=lambda item: item[1]["price"])

    ITEMS_PER_PAGE = 12
    total_pages = math.ceil(len(items_to_show) / ITEMS_PER_PAGE)
    if total_pages == 0:
        total_pages = 1

    start_idx = shop_page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_items = items_to_show[start_idx:end_idx]

    card_w = 80
    card_h = 85
    padding_x = 12
    padding_y = 12
    start_x = popup_rect.x + (popup_rect.width - (4 * card_w + 3 * padding_x)) // 2
    start_y = popup_rect.y + 55

    col = 0
    row = 0
    shop_item_rects = {}

    # item draw
    for item_id, item_data in page_items:
        cx = start_x + col * (card_w + padding_x)
        cy = start_y + row * (card_h + padding_y)
        card_rect = pygame.Rect(cx, cy, card_w, card_h)
        shop_item_rects[item_id] = card_rect

        # item background
        pygame.draw.rect(screen, (50, 50, 55), card_rect, border_radius=8)
        r_color = rarity_colors.get(item_data["rarity"], (100, 100, 100))
        pygame.draw.rect(screen, r_color, card_rect, width=3, border_radius=8)

        circle_y = cy + 30
        pygame.draw.circle(screen, item_data["rgb"], (cx + card_w // 2, circle_y), 16)
        pygame.draw.circle(screen, (0, 0, 0), (cx + card_w // 2, circle_y), 16, 1)
        pygame.draw.circle(screen, (255, 255, 255), (cx + card_w // 2 - 5, circle_y - 5), 3)

        name_str = item_data["name"]
        if len(name_str) > 10:
            name_str = name_str[:9] + ".."
        name_txt = font_micro.render(name_str, True, (240, 240, 240))
        screen.blit(name_txt, (cx + card_w // 2 - name_txt.get_width() // 2, cy + 50))

        if cli_obj.items_i_own and item_id in cli_obj.items_i_own:
            owned_bg = pygame.Rect(cx + 6, cy + 65, card_w - 12, 16)
            pygame.draw.rect(screen, (40, 100, 40), owned_bg, border_radius=4)
            owned_txt = font_micro.render("OWNED", True, (150, 255, 150))
            screen.blit(owned_txt, (cx + card_w // 2 - owned_txt.get_width() // 2, cy + 66))
        else:
            price_txt = font_micro.render(str(item_data["price"]), True, (255, 215, 0))
            pygame.draw.circle(screen, (255, 215, 0), (cx + card_w // 2 - 12, cy + 73), 5)
            screen.blit(price_txt, (cx + card_w // 2 - 4, cy + 67))

        # if item chose, we highlight it
        if item_id == selected_item:
            highlight = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
            highlight.fill((255, 255, 255, 45))
            screen.blit(highlight, card_rect.topleft)
            pygame.draw.rect(screen, (255, 255, 255), card_rect, width=3, border_radius=8)

        col += 1
        if col >= 4:
            col = 0
            row += 1
    # errows
    prev_rect = pygame.Rect(popup_rect.x + 20, 475, 60, 40)
    next_rect = pygame.Rect(popup_rect.right - 80, 475, 60, 40)

    if shop_page > 0:
        pygame.draw.rect(screen, (70, 70, 75), prev_rect, border_radius=10)
        pygame.draw.polygon(screen, (200, 200, 200),
                            [(prev_rect.centerx + 5, prev_rect.centery - 8), (prev_rect.centerx - 5, prev_rect.centery),
                             (prev_rect.centerx + 5, prev_rect.centery + 8)])
    if shop_page < total_pages - 1:
        pygame.draw.rect(screen, (70, 70, 75), next_rect, border_radius=10)
        pygame.draw.polygon(screen, (200, 200, 200),
                            [(next_rect.centerx - 5, next_rect.centery - 8), (next_rect.centerx + 5, next_rect.centery),
                             (next_rect.centerx - 5, next_rect.centery + 8)])
    page_txt = font_small.render(f"Page {shop_page + 1}/{total_pages}", True, (150, 150, 150))
    screen.blit(page_txt, (popup_rect.centerx - page_txt.get_width() // 2, 440))

    # close button
    mx, my = x_y_pos
    close_btn = pygame.Rect(popup_rect.right - 45, popup_rect.y + 15, 30, 30)
    x_txt = font_button.render("X", True, (255, 255, 255))
    draw_premium_button(screen, x_txt, close_btn, (180, 50, 50), (220, 70, 70), (mx, my))

    can_afford = False
    # dynamic buy button
    buy_btn = None
    if selected_item:
        btn_w, btn_h = 140, 45
        btn_x = popup_rect.centerx - (btn_w // 2)
        btn_y = 465
        buy_btn = pygame.Rect(btn_x, btn_y, btn_w, btn_h)

        # if we own --> OWNED
        if cli_obj.items_i_own and selected_item in cli_obj.items_i_own:
            own_txt = font_button.render("OWNED", True, (255, 255, 255))
            draw_premium_button(screen, own_txt, buy_btn, (40, 100, 40), (50, 120, 50), (mx, my))
        else:
            # buy button color by money, can afford --> green, no --> gray
            price = cli_obj.game_shop[selected_item]["price"]
            can_afford = cli_obj.my_amount_of_coins >= price

            base_col = (0, 150, 0) if can_afford else (100, 100, 100)
            hover_col = (0, 200, 0) if can_afford else (120, 120, 120)

            buy_txt = font_button.render("BUY", True, (255, 255, 255))
            draw_premium_button(screen, buy_txt, buy_btn, base_col, hover_col, (mx, my))
    return shop_item_rects, prev_rect, next_rect, total_pages, close_btn, buy_btn, can_afford


def draw_modern_error(screen, text, start_time):
    # time passed
    elapsed = time.time() - start_time
    alpha = 255

    # in and out animation
    if elapsed < 0.3:
        alpha = int((elapsed / 0.3) * 255)
    elif elapsed > 4.7:
        alpha = int(((5.0 - elapsed) / 0.3) * 255)
    alpha = max(0, min(255, alpha))

    # create surf
    box_w, box_h = 420, 50
    surf = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
    # background draw
    bg_color = (35, 35, 40, alpha)
    pygame.draw.rect(surf, bg_color, (0, 0, box_w, box_h), border_radius=8)

    # red line draw
    pygame.draw.rect(surf, (255, 70, 70, alpha), (0, 0, 6, box_h), border_top_left_radius=8,
                     border_bottom_left_radius=8)

    # icon blit
    pygame.draw.circle(surf, (255, 70, 70, alpha), (25, box_h // 2), 10, 2)
    font_icon = pygame.font.SysFont("Segoe UI", 16, bold=True)
    icon_txt = font_icon.render("!", True, (255, 70, 70))
    icon_txt.set_alpha(alpha)
    surf.blit(icon_txt, (25 - icon_txt.get_width() // 2, box_h // 2 - icon_txt.get_height() // 2))

    # text blit
    font = pygame.font.SysFont("Segoe UI", 20)
    text_surf = font.render(text, True, (240, 240, 240))
    text_surf.set_alpha(alpha)
    surf.blit(text_surf, (45, box_h // 2 - text_surf.get_height() // 2))

    # close button blit
    close_bg = (60, 60, 65, alpha)
    pygame.draw.rect(surf, close_bg, (380, 10, 30, 30), border_radius=6)
    font_x = pygame.font.SysFont("Segoe UI", 16, bold=True)
    x_surf = font_x.render("X", True, (180, 180, 180))
    x_surf.set_alpha(alpha)
    surf.blit(x_surf, (395 - x_surf.get_width() // 2, 25 - x_surf.get_height() // 2))

    # surf draw
    screen.blit(surf, (90, 20))


def draw_text(screen, text, x, y, size, bold=False):
    font = pygame.font.SysFont("Segoe UI", size, bold)
    surf = font.render(text, True, (255, 255, 255))
    screen.blit(surf, (x - surf.get_width() // 2, y))


def draw_button(screen, text, x, y, w, h, color):
    rect = pygame.Rect(x, y, w, h)
    pygame.draw.rect(screen, color, rect, border_radius=10)
    draw_text(screen, text, x + w // 2, y + 10, 24, True)
    return rect


def draw_link(screen, text, x, y, font):
    surf = font.render(text, True, (33, 150, 243))
    rect = surf.get_rect(center=(x, y))
    screen.blit(surf, rect)
    return rect


def pre_login_screen(screen, remembered_user, client_obj):
    clock = pygame.time.Clock()
    # buttons
    yes_btn = pygame.Rect(150, 250, 300, 60)
    no_btn = pygame.Rect(150, 330, 300, 60)

    bg_snakes = [BgSnake(600, 600) for _ in range(5)]
    while True:
        screen.fill(COLOR_BG)
        # screen animation
        for s in bg_snakes:
            s.update()
            s.draw(screen)
        mx, my = pygame.mouse.get_pos()

        draw_text(screen, "Welcome Back!", 300, 100, 50, True)
        draw_text(screen, f"Log in as {remembered_user}?", 300, 160, 24)

        draw_premium_button(screen, GLOBAL_FONT.render("YES, LOGIN", True, (255, 255, 255)),
                            yes_btn, (76, 175, 80), (100, 200, 110), (mx, my))
        draw_premium_button(screen, GLOBAL_FONT.render("USE ANOTHER ACCOUNT", True, (255, 255, 255)),
                            no_btn, (100, 100, 110), (130, 130, 140), (mx, my))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                client_obj.close()
                client_obj.join()
                pygame.quit()
                raise SystemExit
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if yes_btn.collidepoint(event.pos):
                    return True
                if no_btn.collidepoint(event.pos):
                    return False
        pygame.display.flip()
        clock.tick(60)


def main():
    global COLOR_PACK
    screen = pygame.display.set_mode((600, 600))
    pygame.display.set_caption("SNAKE ONLINE - Sign in")
    clock = pygame.time.Clock()
    # create spin for animation
    spinner = LoadingSpinner()

    while True:
        # stage 1: key change
        client_obj = ClientThread()
        client_obj.start()
        # wait till exchange end
        while client_obj.state == STATE_HANDSHAKE and client_obj.is_alive():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    client_obj.close()
                    client_obj.join()
                    pygame.quit()
                    raise SystemExit

            spinner.draw(screen, "Securing Connection...")
            pygame.display.flip()
            clock.tick(30)

        if not client_obj.is_alive():
            print("Failed to connect to the server!")
            client_obj.close()
            client_obj.join()
            pygame.quit()
            break

        # automatic login try here
        remembered_user, remembered_token = load_settings_binary()
        login_done = False
        if remembered_user and remembered_token:
            # if we are here it means that the client chose to be remembered in the last time
            # automatic login screen
            choice = pre_login_screen(screen, remembered_user, client_obj)
            if choice:
                msg = client_obj.build_message("TOKEN_LOGIN",
                                               user=remembered_user,
                                               token=remembered_token,
                                               device_id=get_device_fingerprint())
                client_obj.send_to_server(msg)
                client_obj.should_remember = True
                timeout = time.time() + 5
                while time.time() < timeout and client_obj.state == STATE_AUTH:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            client_obj.close()
                            client_obj.join()
                            pygame.quit()
                            raise SystemExit

                    if client_obj.error_num == "007":
                        break

                    spinner.draw(screen, "Logging in...")
                    pygame.display.flip()
                    clock.tick(30)
                if client_obj.state == STATE_LOBBY:
                    login_done = True

        # stage 3: sign in
        if not login_done:
            # if we here client didn't log in with auto login
            if not sign_in_screen(screen, client_obj):
                client_obj.running = False
                client_obj.close()
                client_obj.join()
                pygame.quit()
                break

        try:
            while client_obj.is_alive():
                # stage 4: lobby
                if client_obj.state == STATE_LOBBY:
                    res = home_screen(screen, client_obj)
                    if res is None:  # LOGOUT pressed
                        print(res, "sign of gone")
                        break
                # stage 5: game
                elif client_obj.state == STATE_GAME:
                    cli_game_loop(client_obj)
                    if client_obj:
                        client_obj.prepare_for_new_game()
            client_obj.running = False
            client_obj.close()
            client_obj.join()
            pygame.event.clear()
            time.sleep(0.1)
            COLOR_PACK = [(255, 255, 255)]
        except SystemExit:
            if 'client_obj' in locals() and client_obj is not None and client_obj.is_alive():
                client_obj.running = False
                client_obj.close()
                client_obj.join()
            break


if __name__ == "__main__":
    main()
