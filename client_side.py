"""author: Leehu Shacht"""
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
    # 1. שליפת כתובת ה-MAC של כרטיס הרשת (ייחודי ללוח אם/כרטיס)
    mac = hex(uuid.getnode())
    # 2. שליפת פרטי מערכת נוספים
    node_name = platform.node()  # שם המחשב
    processor = platform.processor()  # סוג המעבד
    # 3. חיבור הנתונים למחרוזת אחת
    raw_id = f"{mac}-{node_name}-{processor}"
    # 4. יצירת Hash (טביעת אצבע) סופית - ככה הנתונים המקוריים לא נחשפים
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


print("finger print --> ", get_device_fingerprint())

SNAKE_BODY = 1
SNAKE_HEAD = 2
APPLE = 3
COIN = 6

BLOCK_SIZE = 15
UDP_RECV_SIZE = 65535
EWOULDBLOCK = 10035
COLOR_PACK = [(255, 255, 255)]

ERROR_DICT = {
    "003": "login failed",
    "004": "signup failed",
    "005": "Illegal state: action not allowed right now",
    "006": "purchase has failed",
    "007": "auto login failed"
}

# -------- LOGIN SCREEN -------- #
# הגדרות עיצוב (מבוסס על ה-Theme שלך)
COLOR_BG = (30, 30, 30)
COLOR_INACTIVE = (51, 51, 51)
COLOR_ACTIVE = (33, 150, 243)  # כחול אקצנט
COLOR_TEXT = (255, 255, 255)

STATE_LOGIN = "LOGIN"
STATE_SIGNUP = "SIGNUP"
STATE_FORGOT = "FORGOT"

# --- הגדרות מצבים (סנכרון מול השרת) ---
STATE_HANDSHAKE = 0  # מחליפים מפתחות הצפנה
STATE_AUTH = 1       # מסך לוגין/הרשמה
STATE_LOBBY = 2      # בחירת צבע / חנות
STATE_GAME = 3       # בתוך המשחק


class BgSnake:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.x = random.randint(0, w)
        self.y = random.randint(0, h)
        self.angle = random.uniform(0, 2 * math.pi)
        self.speed = random.uniform(1.0, 2.5)  # מהירות איטית ומרגיעה
        self.length = random.randint(20, 50)
        self.history = []

        # צבעים עמוקים ואלגנטיים שמשתלבים ב-Dark Mode
        base_color = random.choice([(35, 75, 45), (35, 45, 75), (60, 35, 75), (50, 50, 50)])
        self.color = base_color
        self.radius = random.randint(6, 12)
        self.turn_speed = random.uniform(-0.03, 0.03)

    def update(self):
        # תנועה סינוסואידלית חלקה (כמו נחש אמיתי)
        self.angle += self.turn_speed + math.sin(time.time() * 2) * 0.015

        self.x += math.cos(self.angle) * self.speed
        self.y += math.sin(self.angle) * self.speed

        # ברגע שהנחש יוצא מהמסך - הוא חוזר מהצד השני
        if self.x < -30: self.x = self.w + 30
        if self.x > self.w + 30: self.x = -30
        if self.y < -30: self.y = self.h + 30
        if self.y > self.h + 30: self.y = -30

        self.history.insert(0, (self.x, self.y))
        if len(self.history) > self.length:
            self.history.pop()

    def draw(self, screen):
        for i, (hx, hy) in enumerate(self.history):
            # אפקט זנב: ככל שהחוליה רחוקה מהראש, היא קטנה יותר
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

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            # שינוי פוקוס
            self.active = self.rect.collidepoint(event.pos)
            self.color = COLOR_ACTIVE if self.active else COLOR_INACTIVE
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            else:
                if len(self.text) < 30:  # הגבלת אורך
                    self.text += event.unicode

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
# -------- LOGIN SCREEN -------- #


class ClientThreadUDP(threading.Thread):
    def __init__(self, cli_obj):
        super().__init__()
        self.cli_obj = cli_obj
        self.running = True
        self.cmd_dict = {"BOARD": self.board_f}

    def run(self):
        self.cli_obj.UDP_sock.settimeout(0.05)
        while self.running:  # and self.cli_obj.alive:
            try:
                data, addr = self.cli_obj.UDP_sock.recvfrom(UDP_RECV_SIZE)
                if not data:
                    continue
               # print(f"[DEBUG UDP] Raw data from {addr}: {data[:20]}")
                data = self.cli_obj.deycrept_data_with_AES(data)
                if not data:
                    continue
                data_dict = msgpack.unpackb(data, raw=False)
                # data_dict = json.loads(data.decode('utf-8'))
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

        self.UDP_port = None
        self.UDP_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.UDP_obj = None
        self.last_board_id = -1

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
        self.board_height = -1
        self.board_width = -1
        self.walls = []
        self.water = []
        self.tid_to_color = {}
        self.tid_to_username = {}

        self.camera_x = -1
        self.camera_y = -1

        self.visual_camera_x = -1.0
        self.visual_camera_y = -1.0
        self.visual_snakes = {}  # מילון חדש: {p_id: [(x,y), (x,y), ...]}

        self.head_history = {}  # tid to head history
        self.snake_lengths = {}
        # ---------------------------------
        self.target_snakes = {}  # רק הנחשים, כבר ממוינים!
        # -------------------------

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
            self.sock.connect((self.ip, self.port))
            while self.running:
                data_rec = self.recv_from_server()
                if not data_rec:
                    break
                data_recv = msgpack.unpackb(data_rec, raw=False)
                # data_recv = json.loads(data_rec)
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

    def send_to_server(self, data_dict):  # need to build with self.build_message() and then call this proc
        try:
            with self.lock:
                data_bytes = msgpack.packb(data_dict)
                # json_data = json.dumps(data_dict)  # dict --> JSON string
                self.transport_data.send_with_size(data_bytes)  # string --> bytes
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
                print("sent UDP", data_bytes)
        except socket.error as e:
            print(e)
        except Exception as e:
            print(e)

    def deycrept_data_with_AES(self, data):
        # אם עוד אין מפתח (תחילת משחק), מחזירים את המידע כפי שהוא
        if self.transport_data.key == "KEY":
            return data
        try:
            iv = data[:16]
            ciphertext = data[16:]
            cipher = AES.new(self.transport_data.key, AES.MODE_CBC, iv)
            # unpad מחזיר את הבייטים המקוריים
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
            # מושכים את רשימת המתים ישירות מה-payload
            died = payload.get("died", [])
            for p_id_str in died:
                if p_id_str in self.head_history:
                    del self.head_history[p_id_str]
                if p_id_str in self.visual_snakes:
                    del self.visual_snakes[p_id_str]

    def board_f(self, payload):
        with self.lock:
            tick_id = payload.get("ID", -1)
            #print(f"DEBUG: Got board with ID {tick_id}. My last_board_id is {self.last_board_id}")  # <--- הוסף את זה!
            delta = payload.get("delta")
            is_full_sync = "full_grid" in delta
            if not is_full_sync:
                if tick_id != -1 and tick_id <= self.last_board_id:
                    return
            else:
                print("tcp packet")
                # פאקטה של TCP (סנכרון): נקבל גם אם היא שווה לזמן הנוכחי (כי היא משלימה את ה-UDP)
                # נזרוק רק אם היא ממש ישנה (איחרה בטיק שלם לפחות)
                if tick_id != -1 and tick_id < self.last_board_id:
                    return
            if tick_id != -1:
                self.last_board_id = tick_id
            if is_full_sync:
                print("update with tcp")
                self.grid = {}
                for point in delta["full_grid"]:
                    self.grid[(point[0], point[1], point[4])] = (point[2], point[3])
                if "usernames" in delta:
                    self.tid_to_username = delta.get("usernames")
                    # --- התיקון כאן! ---
                    # אם המדינה היא LOBBY ואנחנו רואים את עצמנו בלוח - עוברים למשחק
                    #if self.state == STATE_LOBBY and str(self.tid) in self.tid_to_username:
                    #   print("Found myself in TCP board! Moving to STATE_GAME")
                    #  self.state = STATE_GAME
            else:
                self.change_graphics(delta.get("remove", []), delta.get("add", []))
            died = delta.get("died", [])
            for p_id_str in died:
                if p_id_str in self.head_history:
                    del self.head_history[p_id_str]
                if p_id_str in self.visual_snakes:
                    del self.visual_snakes[p_id_str]
            if "length" in delta:
                self.snake_lengths = delta.get("length")
            if str(self.tid) in died:
                self.alive = False
            if "players_color" in delta:
                self.tid_to_color = delta.get("players_color")
            self.leaders = delta.get("leaders")
            # הקסם שמתקן הכל
            self.rebuild_optimized_data()

    def pub_key_get_f(self, payload):
        public_key = payload.get("key")
        print("in pub_key_get_f")
        self.state = STATE_AUTH
        server_pub_key_obj = serialization.load_pem_public_key(base64.b64decode(public_key))
        encrypted_aes_key = encrypt_aes_key(self.key, server_pub_key_obj)
        encrypted_key_b64 = base64.b64encode(encrypted_aes_key).decode('utf-8')
        msg = self.build_message("KEY", key=encrypted_key_b64)  # ##
        print("send back")
        self.send_to_server(msg)
        self.transport_data.key = self.key

    def change_graphics(self, to_remove, to_add):
        for point in to_remove:
            x, y, kind, p_id, ticket = point

            # אם השרת שלח טיקט ספציפי (בנחשים או בתפוחים ששלחו ערך)
            if ticket is not None:
                self.grid.pop((x, y, ticket), None)
            else:
                # הגנה: אם השרת שלח None בטיקט (קורה בתפוחים לפעמים)
                # אנחנו מוחקים את כל מה שיש במשבצת הזו
                keys_to_remove = [k for k in self.grid.keys() if k[0] == x and k[1] == y]
                for k in keys_to_remove:
                    self.grid.pop(k, None)

        for point in to_add:
            # point[0]=x, point[1]=y, point[2]=kind, point[3]=p_id, point[4]=ticket
            # המפתח הוא (x, y, ticket)
            self.grid[(point[0], point[1], point[4])] = (point[2], str(point[3]))

    def rebuild_optimized_data(self):
        temp_snakes = {}
        # שינוי כאן: המפתח הוא טאפל של 3 איברים
        for (x, y, ticket), definition in self.grid.items():
            kind = definition[0]
            if kind in (SNAKE_HEAD, SNAKE_BODY):
                p_id_str = definition[1]
                if p_id_str not in temp_snakes:
                    temp_snakes[p_id_str] = []
                # אנחנו שומרים את ה-ticket כדי למיין את הנחש מהראש לזנב
                temp_snakes[p_id_str].append((float(x), float(y), ticket))

        self.target_snakes = {}  # (x,y,ticket)
        for p_id_str in temp_snakes:
            # מיון מהראש לזנב
            temp_snakes[p_id_str].sort(key=lambda item: item[2], reverse=True)  # by ticket
            self.target_snakes[p_id_str] = [(item[0], item[1]) for item in temp_snakes[p_id_str]]

        # עדכון יעד המצלמה
        my_tid_str = str(self.tid)
        if my_tid_str in self.target_snakes and len(self.target_snakes[my_tid_str]) > 0:
            self.camera_x, self.camera_y = self.target_snakes[my_tid_str][0]

            if self.visual_camera_x == -1.0:
                self.visual_camera_x = float(self.camera_x)
                self.visual_camera_y = float(self.camera_y)

    def new_board_f(self, payload):
        with self.lock:
            self.grid = {}
            #self.UDP_port = payload.get("UDPport")
            sync = payload.get("sync")
            self.board_width, self.board_height = sync.get("board_size")
            self.tid_to_color = sync.get("players_color")
            if "walls" in sync:  # also water
                self.walls = sync.get("walls", [])
                self.water = sync.get("water", [])
                # create Surface

            for point in sync.get("full_grid"):
                self.grid[(point[0], point[1], point[4])] = (point[2], point[3])

            self.leaders = sync.get("leaders")
            if "length" in sync:
                self.snake_lengths = sync.get("length")
            in_game = False
            if "usernames" in sync:
                self.tid_to_username = sync.get("usernames")
                if str(self.tid) in self.tid_to_username:
                    in_game = True
            # מעדכן את כל הנחשים ומוצא את המצלמה
            self.rebuild_optimized_data()
            # סנכרון מיידי של המצלמה הויזואלית בהתחלה (שלא תחליק ממינוס 1)
            if self.camera_x != -1 and self.visual_camera_x == -1:
                self.visual_camera_x = float(self.camera_x)
                self.visual_camera_y = float(self.camera_y)
            if in_game:
                self.state = STATE_GAME

    def id_f(self, payload):
        self.tid = payload.get("tid")

    def coins_f(self, payload):
        coins_amount = payload.get("amount")
        if coins_amount:
            self.my_amount_of_coins = coins_amount

    def ack_f(self, payload):
        subject = payload.get("subject")
        if subject == "login" or subject == "signup" or subject == "auto_login":
            self.state = STATE_LOBBY
            if "UDPport" in payload:
                self.UDP_port = payload.get("UDPport")

            self.my_amount_of_coins = payload.get("total_coins", 0)
            print(self.my_amount_of_coins)
            self.game_shop = payload.get("shop")
            self.items_i_own = payload.get("own")
            if "token" in payload and "user" in payload:
                save_settings_binary(payload.get("user"), payload.get("token"))
            if not self.UDP_obj:
                self.UDP_obj = ClientThreadUDP(self)
                self.UDP_obj.start()
                print("sent_INIT !!!")
                self.send_to_server_UDP(self.build_message("INIT", tid=self.tid), encrypt=False)
        if subject == "buy":
            # coins=new_coins, own=new_owned
            coins = payload.get("coins")
            own = payload.get("own")
            self.my_amount_of_coins = coins
            self.items_i_own = own
            print(f"Buy successful! Coins left: {self.my_amount_of_coins}")

    def error_f(self, payload):
        num = payload.get("num")
        info = payload.get("info")
        print(num, info)

        self.error_num = num
        self.error_time = time.time()

        if num == "005":
            self.prepare_for_new_game()

    def prepare_for_new_game(self):
        self.state = STATE_LOBBY
        # self.last_board_id = -1
        self.boosting = False
        self.last_direction = None
        self.color = None
        self.board_height = -1
        self.board_width = -1
        self.walls = []
        self.water = []
        self.tid_to_color = {}
        self.camera_x = -1
        self.camera_y = -1
        self.visual_camera_x = -1.0
        self.visual_camera_y = -1.0
        self.visual_snakes = {}
        self.head_history = {}
        self.snake_lengths = {}
        self.target_snakes = {}
        self.grid = {}
        self.alive = True
        self.leaders = None

    def close(self):
        self.running = False
        if self.UDP_obj:
            self.UDP_obj.running = False
        try:
            self.sock.close()
            self.UDP_sock.close()
        except Exception as e:
            print(e)


def display_new_board(grid, my_tid, tid_to_color, screen, cli_obj, offset_x, offset_y):
    # ציור הגבול האדום
    if cli_obj.camera_x != -1:
        world_rect = pygame.Rect(offset_x, offset_y, cli_obj.board_width * BLOCK_SIZE, cli_obj.board_height * BLOCK_SIZE)
        pygame.draw.rect(screen, (255, 0, 0), world_rect, 3)

        # only fruits and coins
        for (x, y, ticket), (kind, p_id_str) in list(grid.items()):
            if kind == APPLE:
                # ה-ticket הוא ה-value שקובע אם התפוח אדום, כחול או ירוק
                apple_x = offset_x + x * BLOCK_SIZE
                apple_y = offset_y + y * BLOCK_SIZE
                if -BLOCK_SIZE < apple_x < screen.get_width() + BLOCK_SIZE and -BLOCK_SIZE < apple_y < screen.get_height() + BLOCK_SIZE:
                    # אנחנו שולחים את ה-ticket כפרמטר השלישי (ה-value)
                    draw_fruit((kind, p_id_str, ticket), screen, apple_x, apple_y)
            if kind == COIN:
                coin_x = offset_x + x * BLOCK_SIZE
                coin_y = offset_y + y * BLOCK_SIZE
                if -BLOCK_SIZE < coin_x < screen.get_width() + BLOCK_SIZE and -BLOCK_SIZE < coin_y < screen.get_height() + BLOCK_SIZE:
                    #screen.blit(COIN_SURFACE, (coin_x, coin_y))
                    screen.blit(COIN_SURFACE, (coin_x - 2, coin_y - 2))


def draw_fruit(definition, screen, o_x, o_y):
    value = definition[2]
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

    # 1. המבנה עצמו (חום-לבנה)
    pygame.draw.rect(surf, (160, 100, 60), (4, 15, size - 8, size - 15), border_radius=2)

    # 2. דלת קטנה
    pygame.draw.rect(surf, (100, 50, 20), (size // 2 - 4, 20, 8, size - 20))

    # 3. גגון פסים (Awning)
    # גגון אדום
    pygame.draw.polygon(surf, (220, 50, 50), [(2, 15), (size - 2, 15), (size - 6, 5), (6, 5)])
    # פסים לבנים על הגגון
    pygame.draw.polygon(surf, (240, 240, 240), [(10, 15), (16, 15), (18, 5), (14, 5)])
    pygame.draw.polygon(surf, (240, 240, 240), [(size - 16, 15), (size - 10, 15), (size - 14, 5), (size - 18, 5)])

    # 4. שלט זהב קטן למעלה
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
    # צבע סגול רעיל!
    pygame.draw.circle(surf, (138, 43, 226), (center_x, center_y), radius)
    # גבעול
    pygame.draw.line(surf, (100, 100, 100), (center_x, 2), (center_x, 6), 2)
    # נקודת רעל ירוקה באמצע (אזהרה)
    pygame.draw.circle(surf, (0, 255, 0), (center_x, center_y + 1), 2)
    return surf


def create_coin_surface(block_size):
    """
        יוצר משטח של מטבע/אסימון ב-Pygame עם מראה חרוט ומסגרת עבה.
        משתמש בהצללות חדות (Bevel) ליצירת תחושת תלת-מימד ללא עזרים חיצוניים.
        """
    surf_size = block_size + 4
    coin_surface = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
    center = surf_size // 2
    radius = block_size // 2

    # צבעי הזהב לאסימון חרוט
    base_gold = (210, 160, 30)  # צבע רקע הזהב
    light_gold = (255, 220, 100)  # אור למסגרת
    dark_gold = (140, 90, 10)  # צל למסגרת ולחריטה
    inner_gold = (190, 140, 20)  # צבע השטח הפנימי השקוע

    # 1. המסגרת החיצונית (תלת מימד - צל ואור)
    # מציירים עיגול מלא בצבע הצל
    pygame.draw.circle(coin_surface, dark_gold, (center, center), radius)
    # מזיזים את העיגול הבהיר קצת שמאלה ולמעלה כדי ליצור תחושת אור מצד שמאל-עליון
    pygame.draw.circle(coin_surface, light_gold, (center - 1, center - 1), radius)
    # חוזרים למרכז עם צבע הבסיס כדי ליצור את המסגרת העבה
    pygame.draw.circle(coin_surface, base_gold, (center, center), radius - 1)

    # 2. האזור הפנימי השקוע (Debossed Area)
    # כדי ליצור שקע, עושים הפוך מהמסגרת: אור למטה וצל למעלה.
    pygame.draw.circle(coin_surface, light_gold, (center, center), radius - 3)
    pygame.draw.circle(coin_surface, dark_gold, (center - 1, center - 1), radius - 3)
    pygame.draw.circle(coin_surface, inner_gold, (center, center), radius - 4)

    # 3. החריטה המרכזית (כוכב או סמל פשוט)
    # נצייר סימן "$" חרוט. חריטה נוצרת על ידי ציור הסימן בצבע הבסיס/כהה,
    # והוספת קו דק בהיר מתחתיו (אור שפוגע בשפת החריטה).

    font = pygame.font.SysFont("Arial", radius * 2 - 2, bold=True)

    # הצל של החריטה (האור שפוגע בדופן הפנימית התחתונה)
    dollar_light = font.render("$", True, light_gold)
    coin_surface.blit(dollar_light,
                      (center - dollar_light.get_width() // 2, center - dollar_light.get_height() // 2 + 1))

    # הסימן עצמו (השטח העמוק)
    dollar_dark = font.render("$", True, dark_gold)
    coin_surface.blit(dollar_dark, (center - dollar_dark.get_width() // 2, center - dollar_dark.get_height() // 2))

    return coin_surface


def draw_leaderboard(screen, leaders, tid_to_color, my_tid, snake_lengths, tid_to_username):
    if not leaders:
        return
    start_x = screen.get_width() - 170
    start_y = 10
    screen.blit(LEADERBOARD_OVERLAY, (start_x, start_y))
    # 2. משתמשים בפונט הגלובלי:
    title = GLOBAL_FONT.render("LEADERBOARD", True, (255, 255, 255))
    screen.blit(title, (start_x + 10, start_y + 10))

    my_color = None
    my_score = None

    for i, entry in enumerate(leaders):
        p_id = str(entry[0])
        score = entry[1]
        colors = tid_to_color.get(p_id, [(200, 200, 200)])
        if p_id == str(my_tid):
            my_color = colors[0] if colors else None
            my_score = entry[1] if entry else None
        color = colors[0] if colors else (200, 200, 200)
        prefix = "-> " if p_id == str(my_tid) else ""
        player_name = tid_to_username.get(p_id, f"Player {p_id}")
        # 3. שוב שימוש בפונט הגלובלי:
        txt = GLOBAL_FONT.render(f"{i + 1}. {prefix}{player_name}: {score}", True, color)
        screen.blit(txt, (start_x + 10, start_y + 35 + (i * 20)))

    my_id_str = str(my_tid)
    if my_id_str in snake_lengths:
        my_score = snake_lengths[my_id_str]
        my_colors = tid_to_color.get(my_id_str, [(255, 255, 255)])
        my_color = my_colors[0] if my_colors else (255, 255, 255)

        # 4. ועוד פעם שימוש בפונט הגלובלי:
        txt = GLOBAL_FONT.render(f"score: {my_score}", True, my_color)
        screen.blit(txt, (10, screen.get_height() - 30))


def draw_minimap(screen, cli_obj):
    MAP_SIZE = 100
    MARGIN = 15
    map_x = screen.get_width() - MAP_SIZE - MARGIN
    map_y = screen.get_height() - MAP_SIZE - MARGIN
    overlay = pygame.Surface((MAP_SIZE, MAP_SIZE), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 120))
    screen.blit(overlay, (map_x, map_y))
    border_color = (255, 255, 255)
    border_thickness = 1
    world_rect_on_screen = pygame.Rect(
        map_x,
        map_y,
        MAP_SIZE,
        MAP_SIZE)
    pygame.draw.rect(screen, border_color, world_rect_on_screen, border_thickness)
    with cli_obj.lock:
        # משתמשים ברשימת הנחשים המוכנה!
        for p_id_str, segments in cli_obj.target_snakes.items():
            if len(segments) > 0:
                w_x, w_y = segments[0] # חוליה 0 היא הראש
                rel_x = (w_x / cli_obj.board_width) * MAP_SIZE
                rel_y = (w_y / cli_obj.board_height) * MAP_SIZE
                color = cli_obj.tid_to_color.get(str(cli_obj.tid), [(255, 255, 255)])[0] if p_id_str == str(cli_obj.tid) else (255, 255, 255)
                pygame.draw.circle(screen, color, (int(map_x + rel_x), int(map_y + rel_y)), 2)


def prepare_danger_tape_surface():
    surf = pygame.Surface((BLOCK_SIZE, BLOCK_SIZE))

    # צהוב אזהרה עז
    surf.fill((255, 204, 0))

    # צבע שחור לפסים
    black = (20, 20, 20)

    # ציור הפסים בעזרת פוליגונים כדי לקבל אלכסונים עבים
    # פס שמאלי-עליון
    pygame.draw.polygon(surf, black, [(0, 0), (6, 0), (0, 6)])

    # פס מרכזי
    pygame.draw.polygon(surf, black,
                        [(12, 0), (BLOCK_SIZE, 0), (BLOCK_SIZE, 3), (3, BLOCK_SIZE), (0, BLOCK_SIZE), (0, 12)])

    # פס ימני-תחתון
    pygame.draw.polygon(surf, black, [(BLOCK_SIZE, 9), (BLOCK_SIZE, BLOCK_SIZE), (9, BLOCK_SIZE)])

    # מסגרת תוחמת שחורה דקה כדי להפריד בין הקוביות
    pygame.draw.rect(surf, (0, 0, 0), (0, 0, BLOCK_SIZE, BLOCK_SIZE), 1)

    return surf
def prepare_wall_surface():
    # יצירת משטח עם תמיכה בשקיפות (כדי שהקוצים יבלטו על הרקע השחור של הלוח)
    surf = pygame.Surface((BLOCK_SIZE, BLOCK_SIZE), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))  # רקע שקוף לחלוטין

    center = BLOCK_SIZE // 2

    # 1. בסיס הקוץ (עיגול חום-אפור כהה במרכז)
    pygame.draw.circle(surf, (60, 50, 45), (center, center), center - 3)

    # 2. הקוצים עצמם - משולשים חדים בגוונים שונים
    # קוץ שחור-אפור למעלה
    pygame.draw.polygon(surf, (80, 80, 80), [(center - 3, center), (center + 3, center), (center, 0)])
    # קוץ חום כהה למטה
    pygame.draw.polygon(surf, (40, 30, 25), [(center - 3, center), (center + 3, center), (center, BLOCK_SIZE)])
    # קוץ אפור-כהה שמאלה
    pygame.draw.polygon(surf, (50, 50, 50), [(center, center - 3), (center, center + 3), (0, center)])
    # קוץ מתכתי-בהיר ימינה (נותן תחושה של תאורה)
    pygame.draw.polygon(surf, (110, 110, 110), [(center, center - 3), (center, center + 3), (BLOCK_SIZE, center)])

    # 3. תוספת קוצים אלכסוניים חדים במיוחד!
    # קוץ חום לשמאל-למעלה
    pygame.draw.polygon(surf, (70, 55, 45), [(center - 2, center + 2), (center + 2, center - 2), (0, 0)])
    # קוץ שחור לימין-למטה
    pygame.draw.polygon(surf, (20, 20, 20),
                        [(center - 2, center - 2), (center + 2, center + 2), (BLOCK_SIZE, BLOCK_SIZE)])

    # 4. נקודת חיבור מרכזית להדגשת התלת-ממד
    pygame.draw.circle(surf, (15, 15, 15), (center, center), 2)

    return surf


def prepare_water_surface():
    surf = pygame.Surface((BLOCK_SIZE, BLOCK_SIZE), pygame.SRCALPHA)
    surf.fill((0, 100, 255, 120))
    return surf


def prepare_beveled_metal_surface():
    surf = pygame.Surface((BLOCK_SIZE, BLOCK_SIZE))

    # צבע מתכת בסיסי (במרכז)
    surf.fill((140, 140, 145))

    bw = 2  # עובי המסגרת התלת-ממדית (Bevel width)
    light_grey = (220, 220, 225)  # החלק המואר
    dark_grey = (60, 60, 65)  # החלק המוצלל

    # פאה עליונה (מוארת)
    pygame.draw.polygon(surf, light_grey, [(0, 0), (BLOCK_SIZE, 0), (BLOCK_SIZE - bw, bw), (bw, bw)])
    # פאה שמאלית (מוארת)
    pygame.draw.polygon(surf, light_grey, [(0, 0), (bw, bw), (bw, BLOCK_SIZE - bw), (0, BLOCK_SIZE)])

    # פאה תחתונה (מוצלת)
    pygame.draw.polygon(surf, dark_grey, [(0, BLOCK_SIZE), (bw, BLOCK_SIZE - bw), (BLOCK_SIZE - bw, BLOCK_SIZE - bw),
                                          (BLOCK_SIZE, BLOCK_SIZE)])
    # פאה ימנית (מוצלת)
    pygame.draw.polygon(surf, dark_grey, [(BLOCK_SIZE, 0), (BLOCK_SIZE, BLOCK_SIZE), (BLOCK_SIZE - bw, BLOCK_SIZE - bw),
                                          (BLOCK_SIZE - bw, bw)])

    # מסגרת דקה מאוד מסביב להכל כדי להפריד בין הבלוקים כשהם מחוברים
    pygame.draw.rect(surf, (30, 30, 30), (0, 0, BLOCK_SIZE, BLOCK_SIZE), 1)

    return surf


def prepare_rock_wall_surface():
    surf = pygame.Surface((BLOCK_SIZE, BLOCK_SIZE))

    # צבע רקע - זה יהיה הצבע של החריצים/המלט בין הסלעים (שחור-אפור כהה)
    surf.fill((25, 25, 25))

    # פלטת גוונים של אבנים (שילוב של אפור, מעט כחול ומעט חום)
    rock1 = (105, 105, 110)
    rock2 = (85, 85, 90)
    rock3 = (120, 120, 125)
    rock4 = (95, 95, 95)

    # ציור הסלעים - משתמשים ב-border_radius כדי לעגל אותם!
    # סלע שמאלי-עליון (גדול ודומיננטי)
    pygame.draw.rect(surf, rock1, (1, 1, 8, 7), border_radius=3)

    # סלע ימני-עליון (צר וארוך)
    pygame.draw.rect(surf, rock2, (10, 1, 4, 8), border_radius=2)

    # סלע שמאלי-תחתון
    pygame.draw.rect(surf, rock3, (1, 9, 6, 5), border_radius=2)

    # סלע ימני-תחתון
    pygame.draw.rect(surf, rock4, (8, 10, 6, 4), border_radius=2)

    # טאץ' טבעי: ציור של מעט "טחב" (Moss) ירוק כהה באחד החריצים שבין הסלעים
    pygame.draw.circle(surf, (34, 100, 34), (8, 9), 1)

    return surf


def prepare_deep_ice_surface():
    surf = pygame.Surface((BLOCK_SIZE, BLOCK_SIZE))

    # 1. צבע בסיס - כחול מים עמוק וקפוא (Glacier Blue)
    surf.fill((45, 115, 180))

    # 2. הוספת "עומק" למים הקפואים - ריבוע פנימי מעט בהיר יותר
    pygame.draw.rect(surf, (55, 130, 195), (2, 2, BLOCK_SIZE - 4, BLOCK_SIZE - 4))

    # 3. מסגרת קפואה (מעודנת, פחות בוהקת מקודם)
    # למעלה ושמאל (תאורה עדינה)
    pygame.draw.line(surf, (90, 165, 220), (0, 0), (BLOCK_SIZE, 0), 1)
    pygame.draw.line(surf, (90, 165, 220), (0, 0), (0, BLOCK_SIZE), 1)
    # למטה וימין (צל כהה שנותן תחושת עומק של מים)
    pygame.draw.line(surf, (25, 75, 125), (0, BLOCK_SIZE - 1), (BLOCK_SIZE, BLOCK_SIZE - 1), 1)
    pygame.draw.line(surf, (25, 75, 125), (BLOCK_SIZE - 1, 0), (BLOCK_SIZE - 1, BLOCK_SIZE), 1)

    # 4. סדקים עמוקים בתוך הקרח (בצבע תכלת עמום, לא לבן)
    # סדק אלכסוני שבור
    pygame.draw.lines(surf, (110, 180, 230), False, [(1, 3), (5, 7), (9, 13)], 1)
    # סדק משני קטן שיורד לעומק
    pygame.draw.line(surf, (70, 140, 200), (5, 7), (11, 4), 1)

    # 5. השתקפות חלשה מאוד (נותן תחושה של קרח רטוב/חלק)
    pygame.draw.rect(surf, (160, 210, 240), (10, 10, 2, 1))

    return surf


def prepare_dirt_surface():
    surf = pygame.Surface((BLOCK_SIZE, BLOCK_SIZE))
    # צבע בסיס - חום אדמה כהה
    surf.fill((45, 35, 25))

    # "אבנים" או גושי אדמה קטנים (בגוונים טיפה שונים של חום)
    pygame.draw.rect(surf, (60, 50, 40), (2, 3, 3, 2))  # אבן בהירה
    pygame.draw.rect(surf, (35, 25, 15), (10, 8, 2, 2))  # גוש כהה
    pygame.draw.rect(surf, (55, 45, 35), (5, 12, 4, 2))  # אבן שטוחה

    return surf

BACKGROUND_TILE = prepare_dirt_surface() # או כל אחד אחר שבחרת
# אל תשכח לעדכן את המשתנה למעלה:
WATER_SURFACE = prepare_deep_ice_surface()
WALL_SURFACE = prepare_rock_wall_surface()

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
    # יצירת מילון למעקב אחרי הגדילה הויזואלית (נוצר פעם אחת עצמאית)
    if not hasattr(cli_obj, 'visual_lengths'):
        cli_obj.visual_lengths = {}

    with cli_obj.lock:
        # only players (tids) that alive (active)
        active_tids = list(cli_obj.target_snakes.keys())

        if cli_obj.camera_x != -1:
            cli_obj.visual_camera_x += (cli_obj.camera_x - cli_obj.visual_camera_x) * lerp_factor
            cli_obj.visual_camera_y += (cli_obj.camera_y - cli_obj.visual_camera_y) * lerp_factor
        # this for clean lists from dead snakes --> not active
        # --------------------------
        cli_obj.visual_snakes = {k: v for k, v in cli_obj.visual_snakes.items() if k in active_tids}
        cli_obj.head_history = {k: v for k, v in cli_obj.head_history.items() if k in active_tids}
        cli_obj.visual_lengths = {k: v for k, v in cli_obj.visual_lengths.items() if k in active_tids}
        # --------------------------

        for p_id_str, target_list in list(cli_obj.target_snakes.items()):
            if not target_list:  # (x,y)
                continue

            if p_id_str not in cli_obj.visual_snakes:
                cli_obj.visual_snakes[p_id_str] = [list(p) for p in target_list]

            v_snake = cli_obj.visual_snakes[p_id_str]  # (x,y)...

            # --- טיפול בשינויי אורך ---
            # אם השרת הוסיף חוליות (אכלנו), נוסיף אותן במיקום של הזנב הנוכחי
            while len(v_snake) < len(target_list):
                v_snake.append(list(v_snake[-1]))

            # אם השרת הוריד חוליות (בוסט/מוות), נוריד אותן מהסוף
            if len(v_snake) > len(target_list):
                v_snake = v_snake[:len(target_list)]

            # --- האנימציה האמיתית ---
            # כל חוליה רודפת אחרי המיקום שלה בשרת (target_list)
            for i in range(len(v_snake)):
                target_x, target_y = target_list[i]
                v_snake[i][0] += (target_x - v_snake[i][0]) * lerp_factor
                v_snake[i][1] += (target_y - v_snake[i][1]) * lerp_factor

            cli_obj.visual_snakes[p_id_str] = v_snake  # new places closer to target

        offset_x = screen.get_width() // 2 - (cli_obj.visual_camera_x * BLOCK_SIZE)
        offset_y = screen.get_height() // 2 - (cli_obj.visual_camera_y * BLOCK_SIZE)

    # --- שלב הציור ---
    screen.blit(bg_surface, (offset_x, offset_y))

    with cli_obj.lock:
        display_new_board(cli_obj.grid, cli_obj.tid, cli_obj.tid_to_color, screen, cli_obj, offset_x, offset_y)

        for p_id_str, segments in list(cli_obj.visual_snakes.items()):  # tid, (x,y)
            color_list = cli_obj.tid_to_color.get(p_id_str)
            if not color_list:
                continue

            head_color = (color_list[0][0], color_list[0][1], color_list[0][2])

            for i in range(len(segments) - 1, -1, -1):  # start from tail
                v_x, v_y = segments[i]  # x, y
                screen_x = screen.get_width() // 2 - (cli_obj.visual_camera_x * BLOCK_SIZE) + (v_x * BLOCK_SIZE)
                screen_y = screen.get_height() // 2 - (cli_obj.visual_camera_y * BLOCK_SIZE) + (v_y * BLOCK_SIZE)

                if -BLOCK_SIZE * 2 < screen_x < screen.get_width() + BLOCK_SIZE * 2 and -BLOCK_SIZE * 2 < screen_y < screen.get_height() + BLOCK_SIZE * 2:
                    center = (int(screen_x + BLOCK_SIZE / 2), int(screen_y + BLOCK_SIZE / 2))
                    base_radius = int(BLOCK_SIZE / 1.4)

                    if i == 0:
                        # --- ציור השם מעל הנחש ---
                        # שולפים את השם מהמילון (עם הגנה)
                        player_name = cli_obj.tid_to_username.get(p_id_str, f"Player {p_id_str}")
                        # יוצרים את הטקסט (משתמשים בפונט הגלובלי)
                        name_surf = GLOBAL_FONT.render(player_name, True, (255, 255, 255))
                        # ממקמים את הטקסט בדיוק באמצע ומעל הראש
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
                        darker_color = (
                        max(0, body_color[0] - 60), max(0, body_color[1] - 60), max(0, body_color[2] - 60))
                        pygame.draw.circle(screen, darker_color, center, base_radius)
                        pygame.draw.circle(screen, body_color, center, base_radius - 2)

    draw_leaderboard(screen, cli_obj.leaders, cli_obj.tid_to_color, cli_obj.tid, cli_obj.snake_lengths, cli_obj.tid_to_username)
    draw_minimap(screen, cli_obj)


def cli_game_loop(cli_obj):
    # cli_obj.send_to_server_UDP(cli_obj.build_message("INIT", tid=cli_obj.tid))
    width = cli_obj.board_width * BLOCK_SIZE
    height = cli_obj.board_height * BLOCK_SIZE
    screen = pygame.display.set_mode((600, 600))
    clock = pygame.time.Clock()
    # 2. יצירת ה-Surface של הרקע (מציירים פעם אחת וחוסכים ביצועים)
    # 2. יצירת ה-Surface של הרקע
    bg_surface = pygame.Surface((width, height))

    # צובעים את כל הרקע בשחור מראש
    #bg_surface.fill((0, 0, 0))
    # ----- create surface ------ #
    for x in range(cli_obj.board_width + 1):
        for y in range(cli_obj.board_height + 1):
            bg_surface.blit(BACKGROUND_TILE, (x * BLOCK_SIZE, y * BLOCK_SIZE))
    # --- ציור המפה הקבועה עם המשטחים המוכללים ---
    for wx, wy in cli_obj.walls:
        bg_surface.blit(WALL_SURFACE, (wx * BLOCK_SIZE, wy * BLOCK_SIZE))

    for wx, wy in cli_obj.water:
        bg_surface.blit(WATER_SURFACE, (wx * BLOCK_SIZE, wy * BLOCK_SIZE))
    # ----- create surface ------ #
    msg_id = 1
    lerp_factor = 0.2
    current_msg = None
    tick_id = 0
    INTERVAL = 4
    # server_got = False
    times_sent = 0
    while cli_obj.alive:
        screen.fill((0, 0, 0))
        update_and_draw_world1(cli_obj, screen, bg_surface, lerp_factor)
        for event in pygame.event.get():  # try to improve it, faster somehow
            if event.type == pygame.QUIT:
                cli_obj.close()
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
                elif event.key == pygame.K_SPACE and cli_obj.last_direction:
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
        if current_msg and tick_id % INTERVAL == 0 and times_sent < 3:
            times_sent += 1
            cli_obj.send_to_server_UDP(current_msg)
        tick_id += 1
        pygame.display.flip()
        clock.tick(60)
        # msg_id += 1 --> only if i want time or somthing like that
    # --- אנימציית "Fade Out" כשהשחקן מת ---
    # יצירת משטח שחור בגודל המסך
    fade_surface = pygame.Surface((600, 600))
    fade_surface.fill((0, 0, 0))

    for i in range(60):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                cli_obj.close()
                pygame.quit()
                raise SystemExit
        screen.fill((0, 0, 0))
        update_and_draw_world1(cli_obj, screen, bg_surface, lerp_factor)

        # --- 3. ציור ההחשכה ---
        fade_surface.set_alpha(i * 4)
        screen.blit(fade_surface, (0, 0))
        pygame.display.flip()
        clock.tick(60)


def draw_premium_button(screen, text_surface, rect, base_color, hover_color, mouse_pos):
    """ מצייר כפתור תלת-מימדי מודרני עם צל ואפקט ריחוף """
    is_hover = rect.collidepoint(mouse_pos)
    # צבע נוכחי לפי מצב העכבר (בהיר יותר בריחוף)
    color = hover_color if is_hover else base_color
    # תזוזה קלה למעלה כשהעכבר עליו (אפקט קפיצה)
    y_offset = -4 if is_hover else 0
    # 1. ציור הצל (תמיד נשאר למטה במקום קבוע)
    shadow_rect = pygame.Rect(rect.x, rect.y + 6, rect.width, rect.height)
    pygame.draw.rect(screen, (15, 15, 20), shadow_rect, border_radius=15)
    # 2. ציור הגוף המרכזי של הכפתור (זז למעלה בריחוף)
    btn_rect = pygame.Rect(rect.x, rect.y + y_offset, rect.width, rect.height)
    pygame.draw.rect(screen, color, btn_rect, border_radius=15)
    # 3. מסגרת עליונה בהירה (הברקה של תלת-מימד)
    # מחשבים צבע בהיר יותר מהצבע הנוכחי
    light_color = (min(255, color[0] + 60), min(255, color[1] + 60), min(255, color[2] + 60))
    pygame.draw.rect(screen, light_color, btn_rect, width=3, border_radius=15)
    # 4. ציור הטקסט בדיוק באמצע הכפתור שזז
    text_rect = text_surface.get_rect(center=btn_rect.center)
    screen.blit(text_surface, text_rect)


def home_screen(screen, client):
    global COLOR_PACK
    pygame.display.set_caption("SNAKE ONLINE")
    try:
        bg_image = pygame.image.load('background.png').convert()
        bg_image = pygame.transform.scale(bg_image, (600, 600))
    except Exception as e:
        bg_image = None

    font_logo = pygame.font.SysFont(None, 80, bold=True)
    font_play = pygame.font.SysFont(None, 60, bold=True)
    font_button = pygame.font.SysFont(None, 40)
    font_small = pygame.font.SysFont(None, 24)

    text_logo = font_logo.render("SNAKE ONLINE", True, (255, 255, 255))
    text_logo_rect = text_logo.get_rect(center=(300, 100))

    logout_btn_rect = pygame.Rect(10, 60, 100, 35)
    logout_text = font_small.render("LOGOUT", True, (255, 255, 255))

    play_button_rect = pygame.Rect(200, 480, 200, 70)
    play_text = font_play.render("PLAY", True, (255, 255, 255))
    play_text_rect = play_text.get_rect(center=play_button_rect.center)

    color_btn_rect = pygame.Rect(150, 380, 300, 60)
    color_btn_text = font_button.render("Create Skin", True, (255, 255, 255))
    color_btn_text_rect = color_btn_text.get_rect(center=color_btn_rect.center)

    # 12 צבעים
    palette = [
        (255, 50, 50), (50, 255, 50), (50, 50, 255), (255, 255, 50),
        (255, 150, 50), (150, 50, 255), (50, 255, 255), (255, 100, 200),
        (139, 69, 19), (100, 100, 100), (255, 255, 255), (0, 128, 128)
    ]

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

    # מיקום כפתור החנות (צד ימין למעלה)
    shop_btn_rect = pygame.Rect(540, 15, 40, 40)
    # כפתור סגירה לחנות
    close_shop_rect = pygame.Rect(230, 470, 140, 50)

    popup_rect = pygame.Rect(100, 80, 400, 440)
    done_btn_rect = pygame.Rect(230, 450, 140, 50)
    done_text = font_button.render("DONE", True, (255, 255, 255))
    done_text_rect = done_text.get_rect(center=done_btn_rect.center)

    clock = pygame.time.Clock()
    waiting_for_user = True

    # ----------------- background ----------------------------
    # --- הכנת רקע הזירה ללובי (מפת דמו ענקית) ---
    DEMO_MAP_SIZE = 900
    lobby_bg = pygame.Surface((DEMO_MAP_SIZE, DEMO_MAP_SIZE))
    for x in range(0, DEMO_MAP_SIZE, BLOCK_SIZE):
        for y in range(0, DEMO_MAP_SIZE, BLOCK_SIZE):
            lobby_bg.blit(BACKGROUND_TILE, (x, y))
            # נפזר קצת קוצים ומים אקראיים כדי שייראה כמו זירה אמיתית
            rand_val = random.random()
            if rand_val < 0.04:
                lobby_bg.blit(WALL_SURFACE, (x, y))
            elif rand_val < 0.07:
                lobby_bg.blit(WATER_SURFACE, (x, y))

    pan_x, pan_y = 0.0, 0.0  # משתנים למעקב אחרי תנועת המצלמה
    # ----------------- background ----------------------------

    while waiting_for_user:
        # ----------------- background ----------------------------
        # --- הנעת רקע הזירה באלכסון (Infinite Pan) ---
        pan_speed = 0.4  # מהירות גלילה איטית וסינמטית
        pan_x = (pan_x - pan_speed) % DEMO_MAP_SIZE
        pan_y = (pan_y - pan_speed) % DEMO_MAP_SIZE

        # כדי ליצור גלילה אינסופית בלי "חתכים", מציירים את המשטח 4 פעמים
        screen.blit(lobby_bg, (pan_x, pan_y))
        screen.blit(lobby_bg, (pan_x - DEMO_MAP_SIZE, pan_y))
        screen.blit(lobby_bg, (pan_x, pan_y - DEMO_MAP_SIZE))
        screen.blit(lobby_bg, (pan_x - DEMO_MAP_SIZE, pan_y - DEMO_MAP_SIZE))

        # --- אפקט זכוכית כהה ---
        # שמים משטח שחור שקוף ב-85% מעל המפה כדי שהטקסטים והנחש יבלטו
        dark_overlay = pygame.Surface((600, 600), pygame.SRCALPHA)
        dark_overlay.fill((15, 15, 20, 100))  # גוון מעט כחלחל-שחור להרגשה עמוקה
        screen.blit(dark_overlay, (0, 0))
        # ----------------- background ----------------------------

        screen.blit(text_logo, text_logo_rect)
        screen.blit(COIN_SURFACE_FOR_SHOW, (10, 20))
        coin_text = font_button.render(f" {client.my_amount_of_coins}", True, (255, 215, 0))
        screen.blit(coin_text, (40, 20))

        if not show_color_picker and not show_shop:
            # --- מסך ראשי ---

            # קולטים את מיקום העכבר כדי לדעת אם לעשות אפקט ריחוף
            mx, my = pygame.mouse.get_pos()
            draw_premium_button(screen, logout_text, logout_btn_rect, (150, 50, 50), (200, 70, 70), (mx, my))

            # כפתור PLAY מרכזי (ירוק בוהק וחי)
            draw_premium_button(
                screen=screen,
                text_surface=play_text,
                rect=play_button_rect,
                base_color=(0, 160, 60),  # צבע רגיל
                hover_color=(0, 210, 80),  # צבע כשמרחפים (ירוק ניאון)
                mouse_pos=(mx, my)
            )

            # כפתור Create Skin (אפור-כחול יוקרתי)
            draw_premium_button(
                screen=screen,
                text_surface=color_btn_text,
                rect=color_btn_rect,
                base_color=(55, 60, 75),  # צבע רגיל
                hover_color=(80, 90, 115),  # צבע כשמרחפים (מתבהר)
                mouse_pos=(mx, my)
            )

            # כפתור חנות (כבר נראה סבבה, אבל אפשר להוסיף לו הברקה אם תרצה)
            pygame.draw.rect(screen, (60, 60, 70), shop_btn_rect, border_radius=8)
            pygame.draw.rect(screen, (255, 215, 0), shop_btn_rect, width=2, border_radius=8)
            screen.blit(SHOP_ICON, (shop_btn_rect.x + 2, shop_btn_rect.y + 2))
            # מראה את התבנית הנוכחית מעל כפתור הצבעים
            # --- תצוגת נחש חי (Animated Skin Preview) ---
            # הנחש שוכב לרוחב, הראש בשמאל, הזנב בימין, וגלים עוברים לו בגוף!
            time_t = time.time() * 2.5  # קצב הזחילה (הגלים)
            center_x, center_y = 300, 310
            amplitude_y = 18  # גובה הגלים (למעלה ולמטה)
            spacing = 16  # המרחק האופקי בין חוליה לחוליה

            MAX_SEGMENTS = 14

            # חישוב המיקום ההתחלתי של הראש כדי שהנחש יהיה ממורכז בדיוק באמצע המסך
            start_x = center_x - ((MAX_SEGMENTS - 1) * spacing) // 2

            for i in range(MAX_SEGMENTS - 1, -1, -1):
                c = pattern[i % len(pattern)]

                # ה-X קבוע לכל חוליה (i=0 הראש הכי שמאלי, i=13 הזנב הכי ימני)
                hx = start_x + (i * spacing)

                # ה-Y מקבל גל סינוס שנוסע מהראש לזנב
                hy = center_y + math.sin(time_t - i * 0.4) * amplitude_y

                radius = 12 if i == 0 else 10  # הראש קצת יותר גדול

                # ציור החוליה
                pygame.draw.circle(screen, c, (int(hx), int(hy)), radius)
                pygame.draw.circle(screen, (0, 0, 0) if i == 0 else (0, 0, 0), (int(hx), int(hy)), radius, 1)

                # ציור עיניים לראש
                if i == 0:
                    # כדי לדעת לאן הראש פונה, נבדוק איפה נמצאת החוליה שמאחוריו (i=1)
                    hx_1 = start_x + (1 * spacing)
                    hy_1 = center_y + math.sin(time_t - 1 * 0.4) * amplitude_y

                    # וקטור הכיוון: מהגוף אל הראש
                    dx, dy = hx - hx_1, hy - hy_1
                    dist = math.hypot(dx, dy)
                    if dist != 0:
                        dx, dy = dx / dist, dy / dist
                    else:
                        dx, dy = -1, 0  # ברירת מחדל: שמאלה

                    # מיקום העיניים מתעדכן דינמית לפי השיפוע של הגל!
                    pygame.draw.circle(screen, (255, 255, 255), (int(hx + dx * 4 - dy * 5), int(hy + dy * 4 + dx * 5)),
                                       3)
                    pygame.draw.circle(screen, (255, 255, 255), (int(hx + dx * 4 + dy * 5), int(hy + dy * 4 - dx * 5)),
                                       3)
                    pygame.draw.circle(screen, (0, 0, 0), (int(hx + dx * 5 - dy * 5), int(hy + dy * 5 + dx * 5)), 1)
                    pygame.draw.circle(screen, (0, 0, 0), (int(hx + dx * 5 + dy * 5), int(hy + dy * 5 - dx * 5)), 1)

        elif show_color_picker:
            # --- פופ-אפ עריכת Skin ---
            dim_surface = pygame.Surface((600, 600), pygame.SRCALPHA)
            dim_surface.fill((0, 0, 0, 200))
            screen.blit(dim_surface, (0, 0))

            pygame.draw.rect(screen, (50, 50, 50), popup_rect, border_radius=15)
            pygame.draw.rect(screen, (200, 200, 200), popup_rect, width=3, border_radius=15)

            # כותרת פופ אפ
            title = font_button.render("Your Snake:", True, (255, 255, 255))
            screen.blit(title, (120, 100))

            hint = font_small.render("(Click a block to remove)", True, (150, 150, 150))
            screen.blit(hint, (120, 130))

            # 1. ציור התבנית שבחרנו - הנחש שלמעלה!
            preview_rects = []
            start_x, start_y = 180, 175
            spacing = 18  # המרחק בין החוליות

            # קודם יוצרים מלבנים בלתי נראים מאחורי הקלעים בשביל הלחיצות של העכבר
            for i in range(len(pattern)):
                cx = start_x + (i * spacing)
                cy = start_y
                r = pygame.Rect(cx - 12, cy - 12, 24, 24)
                preview_rects.append(r)

            # מציירים מהזנב לראש כדי שהראש יסתיר את החוליה שמאחוריו
            for i in range(len(pattern) - 1, -1, -1):
                c = pattern[i]
                cx = start_x + (i * spacing)
                cy = start_y
                radius = 13 if i == 0 else 11  # הראש טיפה יותר שמן

                # ציור חוליה עגולה
                pygame.draw.circle(screen, c, (cx, cy), radius)
                pygame.draw.circle(screen, (0, 0, 0) if i == 0 else (0, 0, 0), (cx, cy), radius, 1)

                if i == 0:
                    # ציור עיניים לראש (הנחש מסתכל שמאלה!)
                    pygame.draw.circle(screen, (255, 255, 255), (cx - 5, cy - 5), 3)
                    pygame.draw.circle(screen, (255, 255, 255), (cx - 5, cy + 5), 3)
                    pygame.draw.circle(screen, (0, 0, 0), (cx - 6, cy - 5), 1)
                    pygame.draw.circle(screen, (0, 0, 0), (cx - 6, cy + 5), 1)

            # --- בניית פלטת צבעים דינמית לפי מה שיש לי ---
            my_palette = []
            # נוודא שקבלנו את החנות ואת מה שיש לנו
            if client.game_shop and client.items_i_own:
                for item_id in client.items_i_own:
                    if item_id in client.game_shop:
                        # שומרים רק את הצבע ה-RGB מהקטלוג
                        my_palette.append(client.game_shop[item_id]["rgb"])
            else:
                my_palette = [(255, 255, 255)]

            num_colors = len(my_palette)
            if num_colors <= 12:
                cols = 4
                spacing = 70
                circle_radius = 30
            else:
                cols = 5
                spacing = 54
                circle_radius = 23  # עיגולים קצת יותר קטנים
            # מרכוז אוטומטי של הגריד באמצע הפופ-אפ (מתמטיקה פשוטה!)
            grid_width = cols * spacing
            start_x = popup_rect.x + (popup_rect.width - grid_width) // 2
            start_y = 220

            grid_rects = []
            for i in range(num_colors):
                row, col = i // cols, i % cols
                # המלבן השקוף שלוחצים עליו
                grid_rects.append(pygame.Rect(start_x + col * spacing, start_y + row * spacing, spacing, spacing))

            # 2. ציור צבעי הפלטה שיש לי (עם הגודל והמיקום החדשים!)
            for i, color in enumerate(my_palette):
                cx, cy = grid_rects[i].center
                pygame.draw.circle(screen, color, (cx, cy), circle_radius)
                pygame.draw.circle(screen, (0, 0, 0), (cx, cy), circle_radius, 2)

            # 3. כפתור DONE
            pygame.draw.rect(screen, (0, 150, 0), done_btn_rect, border_radius=10)
            pygame.draw.rect(screen, (0, 200, 0), done_btn_rect, width=3, border_radius=10)
            screen.blit(done_text, done_text_rect)

        elif show_shop:
            # --- פופ-אפ חנות חדש! ---
            shop_item_rects, prev_page_rect, next_page_rect, total_shop_pages, close_btn_rect, buy_btn_rect, can_afford = build_shop(
                client, screen, font_button, popup_rect, font_small, shop_page, selected_shop_item)
        # --------------------------------------------------------
        # --- ציור קופסת שגיאה עם כפתור סגירה ---
        if client.error_num:
            if time.time() - client.error_time < 5 and client.error_time != 0:  # 5 second
                draw_modern_error(screen, ERROR_DICT[client.error_num], client.error_time)
            else:
                client.error_num = ""
                client.error_time = 0
        # -------------------------------------------------------------------

        # --- ניהול לחיצות ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if logout_btn_rect.collidepoint(event.pos):
                    client.send_to_server(client.build_message("LOGOUT"))
                    #client.last_board_id = -1
                    if os.path.exists("settings.bin"):
                        os.remove("settings.bin")
                    client.state = STATE_HANDSHAKE
                    client.alive = False
                    client.running = False
                    waiting_for_user = False
                    return None

                # --- בדיקת לחיצה על סגירת שגיאה ---
                if client.error_num:
                    close_btn_rect = pygame.Rect(470, 30, 30, 30)

                    # אם העכבר פגע במלבן הזה:
                    if close_btn_rect.collidepoint(event.pos):
                        client.error_num = ""  # מוחק את השגיאה מיידית!
                        continue  # מדלג על שאר הלחיצות כדי לא ללחוץ בטעות על משהו מאחורי השגיאה

                if not show_color_picker and not show_shop:
                    if play_button_rect.collidepoint(event.pos):
                        waiting_for_user = False
                    elif color_btn_rect.collidepoint(event.pos):
                        show_color_picker = True
                    elif shop_btn_rect.collidepoint(event.pos):  # לחיצה על כפתור החנות!
                        show_shop = True
                elif show_color_picker:
                    clicked_something = False

                    # בדוק אם לחצו על DONE
                    if done_btn_rect.collidepoint(event.pos):
                        if len(pattern) == 0:
                            pattern.append((255, 255, 255))  # חייב לפחות צבע אחד
                        COLOR_PACK = list(pattern)
                        show_color_picker = False
                        clicked_something = True

                    # בדוק אם לחצו על צבע בפלטה (להוסיף מהפלטה הדינמית!)
                    for i, rect in enumerate(grid_rects):
                        if rect.collidepoint(event.pos):
                            if len(pattern) < 14:  # הגבלת אורך מקסימלי לתבנית
                                pattern.append(my_palette[i])
                            clicked_something = True
                            break

                    # בדוק אם לחצו על בלוק בשרשרת (למחוק)
                    for i, rect in enumerate(preview_rects):
                        if rect.collidepoint(event.pos):
                            pattern.pop(i)
                            clicked_something = True
                            break

                    # סגירת חלון אם לחצו מחוץ לו
                    if not clicked_something and not popup_rect.collidepoint(event.pos):
                        if len(pattern) == 0:
                            pattern.append((255, 255, 255))
                        show_color_picker = False
                elif show_shop:
                    # סגירת החנות
                    if close_btn_rect.collidepoint(event.pos):
                        show_shop = False
                        shop_page = 0
                        selected_shop_item = None  # מאפסים בחירה

                    # חצים (הוספנו איפוס בחירה כשמעבירים עמוד)
                    elif prev_page_rect.collidepoint(event.pos) and shop_page > 0:
                        shop_page -= 1
                        selected_shop_item = None
                    elif next_page_rect.collidepoint(event.pos) and shop_page < total_shop_pages - 1:
                        shop_page += 1
                        selected_shop_item = None

                    # כפתור הקנייה (רק אם הוא קיים ולחצנו עליו)
                    elif buy_btn_rect and buy_btn_rect.collidepoint(event.pos) and selected_shop_item:
                        # וידוא שזה לא כפתור OWNED (שאנחנו לא מנסים לקנות שוב)
                        if not (client.items_i_own and selected_shop_item in client.items_i_own):
                            if can_afford:
                                print(f"Buying: {selected_shop_item}")
                                client.send_to_server(client.build_message("BUY", item_id=selected_shop_item))
                    # בחירת פריט - מדליק את השכבה השקופה
                    else:
                        clicked_on_item = False
                        for item_id, rect in shop_item_rects.items():
                            if rect.collidepoint(event.pos):
                                selected_shop_item = item_id  # item_id --> "c_red"
                                clicked_on_item = True
                                break
                        # אם לחצו על מקום ריק בחנות - מבטלים את הבחירה
                        if not clicked_on_item and popup_rect.collidepoint(event.pos):
                            selected_shop_item = None

        pygame.display.flip()
        clock.tick(30)
    print("sending color to server...")
    # שולחים את הרשימה המלאה של הצבעים!
    client.send_to_server(client.build_message("COLOR", color=pattern))
    while client.state == STATE_LOBBY:
        print(f"Current State: {client.state}, My TID: {client.tid}, Active Users:")
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                client.close()
                pygame.quit()
                raise SystemExit

        # מציירים מסך טעינה במקום לקפוא
        screen.fill((20, 20, 20))
        wait_text = font_button.render("Server is full! Waiting for a spot...", True, (255, 200, 0))
        screen.blit(wait_text, wait_text.get_rect(center=(300, 300)))
        pygame.display.flip()
        clock.tick(30)
        #time.sleep(0.05)
    # תיקון קטן: נשמור את הצבעים שבחרנו גם אצלנו מקומית מיד
    client.tid_to_color[str(client.tid)] = pattern
    return client


def handle_auth_action(state, email, password, client_obj):
    if client_obj.state != STATE_AUTH:
        print("Waiting for secure connection...")
        return
    # שליפת טביעת האצבע והבחירה של המשתמש
    f_print = get_device_fingerprint()
    rem = client_obj.should_remember
    if state == STATE_LOGIN:
        msg = client_obj.build_message("LOGIN", email=email, password=password, device_id=f_print, remember_me=rem)
    else:  # SIGNUP
        msg = client_obj.build_message("SIGNUP", email=email, password=password, device_id=f_print, remember_me=rem)
    client_obj.send_to_server(msg)   # with encrypt TCP


def unified_auth_screen(screen, client_obj):
    current_state = STATE_LOGIN
    clock = pygame.time.Clock()
    # יצירת התיבות לכל המצבים
    email_in = InputBox(150, 220, 300, 40, "Username")
    pass_in = InputBox(150, 290, 300, 40, "Password", is_password=True)
    confirm_in = InputBox(150, 360, 300, 40, "Confirm Password", is_password=True)
    font_small = pygame.font.SysFont("Segoe UI", 18)

    bg_snakes = [BgSnake(600, 600) for _ in range(8)]
    rem_box = CheckBox(150, 340)

    while True:
        screen.fill(COLOR_BG)

        for s in bg_snakes:
            s.update()
            s.draw(screen)
        rem_box.draw(screen)  # ציור התיבה
        mx, my = pygame.mouse.get_pos()

        if current_state == STATE_LOGIN:
            rem_box.rect.y = 345  # מיקום בהתחברות (מתחת לסיסמה)
        else:
            rem_box.rect.y = 415  # מיקום בהרשמה (מתחת לאימות סיסמה)

        rem_box.draw(screen)  # מציירים את התיבה במקום המעודכן

        # --- לוגיקת ציור לפי State ---
        if current_state == STATE_LOGIN:
            draw_text(screen, "SIGN IN", 300, 100, 50, True)
            email_in.draw(screen)
            pass_in.draw(screen)
            btn_rect = draw_button(screen, "LOGIN", 200, 380, 200, 50, (76, 175, 80))

            # לינקים למעבר מסכים
            signup_link = draw_link(screen, "No account? Create one", 300, 450, font_small)
            forgot_link = draw_link(screen, "Forgot Password?", 300, 480, font_small)

        elif current_state == STATE_SIGNUP:
            draw_text(screen, "CREATE ACCOUNT", 300, 100, 40, True)
            email_in.draw(screen)
            pass_in.draw(screen)
            confirm_in.draw(screen)
            # דחפנו את הכפתור והלינקים למטה כדי לפנות מקום לתיבת ה"זכור אותי" החדשה
            btn_rect = draw_button(screen, "SIGN UP", 200, 455, 200, 50, (33, 150, 243))
            signup_link = draw_link(screen, "Back to Login", 300, 520, font_small)


        # --------------------------------------------------------
        # --- ציור קופסת שגיאה עם כפתור סגירה ---
        if client_obj.error_num:
            if time.time() - client_obj.error_time < 5 and client_obj.error_time != 0:  # 5 second
                draw_modern_error(screen, ERROR_DICT[client_obj.error_num], client_obj.error_time)
            else:
                client_obj.error_num = ""
                client_obj.error_time = 0
        # -------------------------------------------------------------------

        # --- ניהול אירועים ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None

            email_in.handle_event(event)
            pass_in.handle_event(event)
            rem_box.handle_event(event)  # טיפול בלחיצה על התיבה
            if current_state == STATE_SIGNUP: confirm_in.handle_event(event)

            if event.type == pygame.MOUSEBUTTONDOWN:
                # --- בדיקת לחיצה על סגירת שגיאה ---
                if client_obj.error_num:
                    close_btn_rect = pygame.Rect(470, 30, 30, 30)

                    # אם העכבר פגע במלבן הזה:
                    if close_btn_rect.collidepoint(event.pos):
                        client_obj.error_num = ""  # מוחק את השגיאה מיידית!
                        continue  # מדלג על שאר הלחיצות כדי לא ללחוץ בטעות על משהו מאחורי השגיאה

                if btn_rect.collidepoint(event.pos):
                    if current_state == STATE_SIGNUP and pass_in.text != confirm_in.text:
                        print("Passwords don't match!")
                        continue
                    # כאן קורה החיבור לשרת (Login/Signup)

                    client_obj.should_remember = rem_box.checked
                    handle_auth_action(current_state, email_in.text, pass_in.text, client_obj)

                if signup_link.collidepoint(event.pos):
                    current_state = STATE_SIGNUP if current_state == STATE_LOGIN else STATE_LOGIN

        if client_obj.state == STATE_LOBBY:
            return True

        pygame.display.flip()
        clock.tick(60)


def build_shop(cli_obj, screen, font_button, popup_rect, font_small, shop_page, selected_item):
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

    for item_id, item_data in page_items:
        cx = start_x + col * (card_w + padding_x)
        cy = start_y + row * (card_h + padding_y)
        card_rect = pygame.Rect(cx, cy, card_w, card_h)
        shop_item_rects[item_id] = card_rect

        # רקע ומסגרת רגילה
        pygame.draw.rect(screen, (50, 50, 55), card_rect, border_radius=8)
        r_color = rarity_colors.get(item_data["rarity"], (100, 100, 100))
        pygame.draw.rect(screen, r_color, card_rect, width=2, border_radius=8)

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

        # -------------------------------------------------------------
        # === הקסם! אם הפריט הזה נבחר - מציירים עליו שכבה שקופה! ===
        if item_id == selected_item:
            # 1. יצירת משטח שתומך בשקיפות בגודל הכרטיס
            highlight = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
            highlight.fill((255, 255, 255, 45))  # לבן עם 45/255 אחוזי אטימות
            screen.blit(highlight, card_rect.topleft)
            # 2. מסגרת לבנה עבה וזוהרת שמדגישה אותו
            pygame.draw.rect(screen, (255, 255, 255), card_rect, width=3, border_radius=8)
        # -------------------------------------------------------------

        col += 1
        if col >= 4:
            col = 0
            row += 1

    # חצים
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

    # --- כפתור CLOSE בצד שמאל למטה ---
    close_btn = pygame.Rect(popup_rect.x + 90, 465, 100, 45)
    pygame.draw.rect(screen, (180, 50, 50), close_btn, border_radius=10)
    pygame.draw.rect(screen, (255, 100, 100), close_btn, width=3, border_radius=10)
    close_txt = font_button.render("CLOSE", True, (255, 255, 255))
    screen.blit(close_txt, close_txt.get_rect(center=close_btn.center))

    can_afford = False
    # --- כפתור BUY דינמי בצד ימין למטה (מופיע רק אם בחרנו משהו) ---
    buy_btn = None
    if selected_item:
        buy_btn = pygame.Rect(popup_rect.right - 190, 465, 100, 45)

        # אם יש לנו כבר את הפריט - נראה OWNED
        if cli_obj.items_i_own and selected_item in cli_obj.items_i_own:
            pygame.draw.rect(screen, (40, 100, 40), buy_btn, border_radius=10)
            pygame.draw.rect(screen, (100, 255, 100), buy_btn, width=3, border_radius=10)
            own_txt = font_button.render("OWNED", True, (255, 255, 255))
            screen.blit(own_txt, own_txt.get_rect(center=buy_btn.center))
        else:
            # בודק אם יש לנו מספיק כסף כדי לצבוע את הכפתור בירוק או באפור!
            price = cli_obj.game_shop[selected_item]["price"]
            can_afford = cli_obj.my_amount_of_coins >= price
            bg_col = (0, 150, 0) if can_afford else (100, 100, 100)
            bord_col = (0, 255, 0) if can_afford else (150, 150, 150)

            pygame.draw.rect(screen, bg_col, buy_btn, border_radius=10)
            pygame.draw.rect(screen, bord_col, buy_btn, width=3, border_radius=10)
            buy_txt = font_button.render("BUY", True, (255, 255, 255))
            screen.blit(buy_txt, buy_txt.get_rect(center=buy_btn.center))

    return shop_item_rects, prev_rect, next_rect, total_pages, close_btn, buy_btn, can_afford


def draw_modern_error(screen, text, start_time):
    # חישוב הזמן שעבר לאנימציית Fade
    elapsed = time.time() - start_time
    alpha = 255

    # אנימציית כניסה ויציאה (0.3 שניות של הבהרה/החשכה)
    if elapsed < 0.3:
        alpha = int((elapsed / 0.3) * 255)
    elif elapsed > 4.7:
        alpha = int(((5.0 - elapsed) / 0.3) * 255)
    alpha = max(0, min(255, alpha))

    # יצירת משטח שתומך בשקיפות
    box_w, box_h = 420, 50
    surf = pygame.Surface((box_w, box_h), pygame.SRCALPHA)

    # 1. רקע הקופסה (אפור-שחור אלגנטי)
    bg_color = (35, 35, 40, alpha)
    pygame.draw.rect(surf, bg_color, (0, 0, box_w, box_h), border_radius=8)

    # 2. פס אדום דק בצד שמאל
    pygame.draw.rect(surf, (255, 70, 70, alpha), (0, 0, 6, box_h), border_top_left_radius=8,
                     border_bottom_left_radius=8)

    # 3. ציור אייקון אזהרה (עיגול עם סימן קריאה)
    pygame.draw.circle(surf, (255, 70, 70, alpha), (25, box_h // 2), 10, 2)
    font_icon = pygame.font.SysFont("Segoe UI", 16, bold=True)
    icon_txt = font_icon.render("!", True, (255, 70, 70))
    icon_txt.set_alpha(alpha)
    surf.blit(icon_txt, (25 - icon_txt.get_width() // 2, box_h // 2 - icon_txt.get_height() // 2))

    # 4. ציור טקסט השגיאה
    font = pygame.font.SysFont("Segoe UI", 20)
    text_surf = font.render(text, True, (240, 240, 240))
    text_surf.set_alpha(alpha)
    surf.blit(text_surf, (45, box_h // 2 - text_surf.get_height() // 2))

    # 5. כפתור הסגירה (X) - עדין ומשתלב
    close_bg = (60, 60, 65, alpha)
    pygame.draw.rect(surf, close_bg, (380, 10, 30, 30), border_radius=6)
    font_x = pygame.font.SysFont("Segoe UI", 16, bold=True)
    x_surf = font_x.render("X", True, (180, 180, 180))
    x_surf.set_alpha(alpha)
    surf.blit(x_surf, (395 - x_surf.get_width() // 2, 25 - x_surf.get_height() // 2))

    # הדבקת המשטח כולו על המסך הראשי (ממורכז למעלה)
    screen.blit(surf, (90, 20))


# פונקציות עזר לציור
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


def pre_login_screen(screen, remembered_user):
    clock = pygame.time.Clock()
    font_play = pygame.font.SysFont("Segoe UI", 40, bold=True)
    # הגדרת כפתורים
    yes_btn = pygame.Rect(150, 250, 300, 60)
    no_btn = pygame.Rect(150, 330, 300, 60)
    bg_snakes = [BgSnake(600, 600) for _ in range(5)]  # נחשי רקע למראה חי
    while True:
        screen.fill(COLOR_BG)
        for s in bg_snakes:
            s.update()
            s.draw(screen)
        mx, my = pygame.mouse.get_pos()
        # כותרת
        draw_text(screen, "Welcome Back!", 300, 100, 50, True)
        draw_text(screen, f"Log in as {remembered_user}?", 300, 160, 24)
        # כפתור "כן" (ירוק)
        draw_premium_button(screen, GLOBAL_FONT.render("YES, LOGIN", True, (255, 255, 255)),
                            yes_btn, (76, 175, 80), (100, 200, 110), (mx, my))
        # כפתור "לא" (אפור)
        draw_premium_button(screen, GLOBAL_FONT.render("USE ANOTHER ACCOUNT", True, (255, 255, 255)),
                            no_btn, (100, 100, 110), (130, 130, 140), (mx, my))
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
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
    screen = pygame.display.set_mode((600, 600))
    pygame.display.set_caption("SNAKE ONLINE - Secure Login")
    while True:
        # --- שלב 1: התחברות לשרת ותחילת הצפנה ---
        client_obj = ClientThread()
        client_obj.start()
        # מחכים שניה שה-Handshake של ה-RSA/AES יסתיים בשקט
        while client_obj.state == STATE_HANDSHAKE and client_obj.is_alive():
            time.sleep(0.05)

        # automatic login try here
        remembered_user, remembered_token = load_settings_binary()
        login_done = False
        if remembered_user and remembered_token:
            choice = pre_login_screen(screen, remembered_user)
            if choice:
                # המשתמש אישר - שולחים טוקן (מוצפן ב-AES שכבר מוכן)
                msg = client_obj.build_message("TOKEN_LOGIN",
                                               user=remembered_user,
                                               token=remembered_token,
                                               device_id=get_device_fingerprint())
                client_obj.send_to_server(msg)
                client_obj.should_remember = True
                timeout = time.time() + 5
                while time.time() < timeout and client_obj.state == STATE_AUTH:
                    time.sleep(0.05)
                if client_obj.state == STATE_LOBBY:
                    login_done = True

        # --- שלב 2: הצגת מסך הלוגין/הרשמה ---
        # הפונקציה הזו תרוץ בלולאה עד שהמשתמש יצליח להתחבר
        if not login_done:
            if not unified_auth_screen(screen, client_obj):
                break
        try:
            while client_obj.is_alive():

                if client_obj.state == STATE_LOBBY:
                    res = home_screen(screen, client_obj)
                    if res is None:  # סימן שנעשה Logout
                        print(res, "sign of gone")
                        break  # שובר את הלולאה הפנימית וחוזר ל-while True להתחברות חדשה

                elif client_obj.state == STATE_GAME:
                    # מריצים את המשחק עד שהשחקן מת (או יוצא)
                    cli_game_loop(client_obj)
                    if client_obj:
                        client_obj.prepare_for_new_game()
            client_obj.running = False
            client_obj.close()
            client_obj.join()
            pygame.event.clear()
            time.sleep(0.1)
        except SystemExit:
            if 'client_obj' in locals() and client_obj is not None and client_obj.is_alive():
                client_obj.join()
            break


if __name__ == "__main__":
    main()
