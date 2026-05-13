"""author: Leehu Shacht"""
import random
import traceback

import socket
import threading
from AsyncMessages import AsyncMessages
from UDP_AsincMessages import UDPAsyncMessages
from try_DATa import HoldPlayersData
from USER_DATA_BASE import UserManager

from msg_by_size_snake import TransportData
# import os
import time
# import json
import base64
import msgpack
import secrets

# --- AES --- #
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes
# --- AES --- #

# -------- RSA
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding


def generate_keys():
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, )
    # 2. Serialize (save) the Private Key
    # We use a password to encrypt the private key file itself for safety
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(b'mypassword')
    )
    with open('private_key_leehu.pem', 'wb') as f:
        f.write(pem_private)
    # 3. Generate and Serialize the Public Key
    public_key = private_key.public_key()
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    with open('public_key_leehu.pem', 'wb') as f:
        f.write(pem_public)
    print("Keys generated and saved.")
    return private_key, public_key


def load_keys():
    # Load Private Key (You need the password used during generation)
    with open("private_key_leehu.pem", "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=b'mypassword',
            backend=default_backend()
        )
    # Load Public Key
    with open("public_key_leehu.pem", "rb") as key_file:
        public_key = serialization.load_pem_public_key(
            key_file.read(),
            backend=default_backend()
        )
    return private_key, public_key


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


def decrypt_aes_key(encrypted_message, private_key):
    try:
        message = private_key.decrypt(
            encrypted_message,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return message
    except ValueError:
        return "failed"


# -------- RSA


sign_cmd = ["COLOR", "KEY", "SIGNUP", "LOGIN", "TOKEN_LOGIN"]
RECV_SIZE = 1024
UDP_RECV_SIZE = 65535
EWOULDBLOCK = 10035
BROADCAST_TIME = 0.05

STATE_HANDSHAKE = 0
STATE_AUTH = 1
STATE_LOBBY = 2
STATE_GAME = 3

ALLOWED_COMMANDS = {
    STATE_HANDSHAKE: ["KEY"],
    STATE_AUTH: ["LOGIN", "SIGNUP", "TOKEN_LOGIN"],
    STATE_LOBBY: ["COLOR", "BUY", "LOGOUT", "LEAVE_GAME"],
    STATE_GAME: ["DIR", "LEAVE_GAME", "SYNC_ME"]
}

ALLOWED_UDP = {
    STATE_LOBBY: ["INIT"],
    STATE_GAME: ["DIR", "INIT"]
}

BOTS_NAMES = ["bob", "david", "rahel", "vladimir", "yona"]

ERROR_DICT = {
    "003": "login failed",
    "004": "signup failed",
    "005": "Illegal state: action not allowed right now",
    "006": "purchase has failed",
    "007": "auto login failed"
}


class BotClient:
    def __init__(self, bot_id):
        self.tid = bot_id
        self.username = BOTS_NAMES.pop(0)


class HandleClientUDP(threading.Thread):
    def __init__(self, server, udp_sock):
        super().__init__()
        self.server = server
        self.udp_sock = udp_sock
        self.udp_lock = threading.Lock()
        self.udp_clients = {}  # playerId -> (ip, port)
        self.addr_to_tid = {}  # for encrypted messages
        self.cmd_dict = {"DIR": self.dir_f, "INIT": self.init_f}
        self.tid_to_ID = {}

    def run(self):
        self.udp_sock.settimeout(0.05)
        while not self.server.stop_event.is_set():
            try:
                data, addr = self.udp_sock.recvfrom(UDP_RECV_SIZE)
                print(f"CLASS:udp | PROC:run | data:{data} | addr:{addr}")
                if not data:
                    continue
                # --- התיקון כאן ---
                # ננסה להבין אם זה INIT עוד לפני הפענוח
                is_init_packet = False
                try:
                    temp_data = msgpack.unpackb(data, raw=False)
                    if temp_data.get("cmd") == "INIT":
                        print(f"CLASS:udp | PROC:run | info:got INIT")
                        is_init_packet = True
                except:
                    pass

                if is_init_packet:
                    # אם זה INIT, נטפל בו ישירות בלי פענוח
                    payload = temp_data.get("payload", {})
                    self.cmd_dict["INIT"](payload, addr)
                    continue  # ממשיכים לחבילה הבאה

                # here decrypt data
                data, is_IN, cli_obj = self.deycrept_data_with_AES(data, addr)
                if data == b"":
                    continue
                try:
                    payload_dict = msgpack.unpackb(data, raw=False)
                except Exception:
                    continue  # מידע זבל שלא ניתן לפריקה

                cmd = payload_dict.get("cmd")
                payload = payload_dict.get("payload", {})
                if not cli_obj:
                    if cmd == "INIT":
                        # השרת עוד לא מכיר את הכתובת, אז נשלוף את ה-TID מההודעה עצמה
                        p_tid = str(payload.get("tid"))
                        temp_cli_obj = self.server.get_tcp_client_obj(p_tid)
                        # בודקים אם לשחקן הזה בכלל מותר לעשות INIT עכשיו (State LOBBY או GAME)
                        if temp_cli_obj:
                            print(f"CLASS:udp | PROC:run | info:CLI EXIST!")
                            allowed_for_temp = ALLOWED_UDP.get(temp_cli_obj.state, [])
                            if "INIT" in allowed_for_temp:
                                self.cmd_dict["INIT"](payload, addr)
                        else:
                            print(f"CLASS:udp | PROC:run | info:CLI NOT EXIST!")
                    # אם זה לא INIT או שאין לקוח כזה - מתעלמים
                    continue
                else:
                    allowed = ALLOWED_UDP.get(cli_obj.state, [])
                    cmd = payload_dict.get("cmd")
                    if cmd in allowed:
                        if cmd != "INIT" and not is_IN:
                            continue
                        self.cmd_dict[cmd](payload_dict.get("payload"), addr)
                self.send_messages_back()
            # except ConnectionResetError:
            # התיקון: ווינדוס זורק את זה כששחקן התנתק. פשוט מתעלמים וממשיכים להאזין!
            #   pass
            except socket.error as err:
                if err.errno == EWOULDBLOCK or str(err) == "timed out":  # if we use conn.settimeout(x)
                    self.send_messages_back()
                    continue
                if err.errno == 10054:
                    # 'Connection reset by peer'
                    print("Error %d Client is Gone.  reset by peer." % (err.errno))
                    continue
                else:
                    print("%d General Sock Error Client disconnected" % (err.errno))
                    continue
            except Exception as e:
                print(e)
        print("bye UDP!")

    def build_message(self, cmd, **payload):
        return {
            "cmd": cmd,
            "payload": payload
        }

    def deycrept_data_with_AES(self, data, addr):
        if addr in self.addr_to_tid.keys():
            tid = self.addr_to_tid.get(addr)
        else:
            return data, False, None
        tid = str(tid)
        client_obj = self.server.get_tcp_client_obj(tid)
        if client_obj and client_obj.transport_data.key != "KEY":
            try:
                iv = data[:16]
                ciphertext = data[16:]
                cipher = AES.new(client_obj.transport_data.key, AES.MODE_CBC, iv)
                decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
                return decrypted, True, client_obj
            except Exception as e:
                print(f"UDP Decryption failed: {e}")
                return b"", True, None
        return b"", True, None

    def encrypt_data_with_AES(self, data_bytes, addr):
        with self.udp_lock:
            tid = self.addr_to_tid.get(addr)
        if not tid:
            print(f"Blocking outgoing UDP: unknown address {addr}")
            return None
        client_obj = self.server.get_tcp_client_obj(tid)
        if not client_obj or client_obj.transport_data.key == "KEY":
            print(f"Blocking outgoing UDP: Encryption not ready for {tid}")
            return None
        try:
            iv = get_random_bytes(16)
            cipher = AES.new(client_obj.transport_data.key, AES.MODE_CBC, iv)
            ciphertext = cipher.encrypt(pad(data_bytes, AES.block_size))
            return iv + ciphertext
        except Exception as e:
            print(f"CRITICAL: Encryption failed for {tid}: {e}")
            return None

    def send_messages_back(self):
        with self.udp_lock:
            temp = list(self.udp_clients.keys())
        for tid in temp:
            messages = self.server.UDP_async_msg.get_async_messages(str(tid))
            if not messages:
                continue
            with self.udp_lock:
                client_address = self.udp_clients.get(str(tid))
            if client_address:
                for msg in messages:
                    if msg:
                        self.send_data(msg, client_address)
            else:
                print(f"Skipping message for disconnected client: {tid}")

    def init_f(self, payload, addr):
        print(f"CLASS:udp | PROC:init_f | info:GOT INIT")
        p_tid = int(payload.get("tid"))
        client_obj = self.server.get_tcp_client_obj(str(p_tid))
        if not client_obj:
            print(f"CRITICAL: INIT failed, TCP client {p_tid} not found!")
            return

        if client_obj.state not in [STATE_LOBBY, STATE_GAME]:
            print(f"UDP INIT blocked: Client {p_tid} is in state {client_obj.state}")
            return
        str_tid = str(p_tid)
        with self.udp_lock:
            if str_tid not in self.udp_clients:
                self.addr_to_tid[addr] = str_tid
                self.udp_clients[str_tid] = addr
                self.server.UDP_async_msg.add_new_player(str_tid, addr)
                self.tid_to_ID[str_tid] = -1
                print(f"Player {str_tid} registered UDP address: {addr}")
                self.server.forced_full_sync = True
            else:
                print("in? -- >", str_tid)

    def dir_f(self, payload, addr):
        p_tid = str(payload.get("tid"))
        msg_id = payload.get("ID", -1)
        direction = payload.get("direction")
        is_boosting = payload.get("boost")
        # רישום אוטומטי אם ה-INIT הלך לאיבוד
        # if p_tid not in self.udp_clients:
        #   self.init_f(payload, addr)
        is_new_msg = False
        with self.udp_lock:
            if p_tid not in self.udp_clients:
                self.udp_clients[p_tid] = addr
                self.server.UDP_async_msg.add_new_player(str(p_tid), addr)
                self.tid_to_ID[str(p_tid)] = -1
            if msg_id > self.tid_to_ID[str(p_tid)]:
                print("new id")
                self.tid_to_ID[str(p_tid)] = msg_id
                is_new_msg = True

            else:
                print("old id")
        if is_new_msg:
            player_obj = self.server.players_manager.get_cli_obj(str(p_tid))
            if player_obj:
                self.server.players_manager.set_boost(player_obj, is_boosting)
                self.server.players_manager.change_direction(player_obj, direction)
            else:
                print(f"CLASS:udp | PROC:dir_f | info:CLI UNKNOWN")

    def remove_client(self, tid):
        str_tid = str(tid)
        with self.udp_lock:
            # נמצא את הכתובת שקשורה ל-TID הזה כדי למחוק אותה מהמפה השנייה
            addr_to_remove = None
            for addr, t_id in self.addr_to_tid.items():
                if t_id == str_tid:
                    addr_to_remove = addr
                    break
            if addr_to_remove:
                del self.addr_to_tid[addr_to_remove]
            self.udp_clients.pop(str_tid, None)
            self.tid_to_ID.pop(str_tid, None)

        """
        str_tid = str(tid)
        with self.server.lock:
            if str_tid in self.udp_clients:
                addr = self.udp_clients[str_tid]
                if addr in self.addr_to_tid:
                    del self.addr_to_tid[addr]
                del self.udp_clients[str_tid]
            if str_tid in self.tid_to_ID:
                del self.tid_to_ID[str_tid]"""

    def send_data(self, data_dict, addr):
        try:
            # dict --> JSON string --> bytes
            data_bytes = msgpack.packb(data_dict)
            data_bytes = self.encrypt_data_with_AES(data_bytes, addr)
            if data_bytes:
                self.udp_sock.sendto(data_bytes, addr)
        except Exception as e:
            print("UDP send failed:", e)


class Client(threading.Thread):
    def __init__(self, server, sock, tid):
        super().__init__()
        self.server = server
        self.sock = sock
        self.transport_data = TransportData(self.sock, "KEY")  # key?
        self.state = STATE_HANDSHAKE
        self.tid = tid
        self.username = None
        # self.password = None
        self.sync_me = False
        self.need_new_board = False

        self.snake_color = None
        self.cmd_dict = {"COLOR": self.color_f, "KEY": self.key_f, "SIGNUP": self.signup_f,
                         "LOGIN": self.login_f, "BUY": self.buy_f, "TOKEN_LOGIN": self.token_login_f,
                         "LOGOUT": self.logout_f, "LEAVE_GAME": self.leave_game_f, "SYNC_ME": self.sync_me_f}

    def run(self):
        self.sock.settimeout(0.1)
        self.server.async_msg.not_ready(int(self.tid))
        self.server.UDP_async_msg.not_ready(int(self.tid))
        self.server.async_msg.put_msg_by_user(
            self.build_message("PUB_KEY", key=self.server.b64_public_ready), int(self.tid))

        while not self.server.stop_event.is_set():
            try:
                data = self.recv_by_size()  # dict
                if not data:
                    print(f"CLASS:client | PROC:run | info:recv 0 data")
                    break
                print(f"CLASS:client | PROC:run | data before:{data}")
                try:
                    data = msgpack.unpackb(data, raw=False)
                except Exception:
                    continue
                print(f"CLASS:client | PROC:run | data after:{data}")
                # data = json.loads(data)
                command = data.get("cmd")
                payload = data.get("payload", {})
                if command:
                    if command in ALLOWED_COMMANDS[self.state]:
                        command = data.get("cmd")
                        payload = data.get("payload", {})
                        if command in self.cmd_dict.keys():
                            self.cmd_dict[command](payload)
                        else:
                            self.send_error("002")
                    else:
                        print(f"[Security] Blocked {command} for client {self.tid} in state {self.state}")
                        self.send_error("005")  # שגיאת "מצב לא חוקי" (תגדיר ב-ERROR_DICT)
                else:
                    self.send_error("002")
            except socket.error as err:
                if err.errno == EWOULDBLOCK or str(err) == "timed out":  # if we use conn.settimeout(x)
                    msgs = self.server.async_msg.get_async_messages_to_send(self.sock)
                    for data in msgs:
                        self.send_with_sign(data)
                    continue
                if err.errno == 10054:
                    # 'Connection reset by peer'
                    print("Error %d Client is Gone.  reset by peer." % (err.errno))
                    break
                else:
                    print("%d General Sock Error Client disconnected" % (err.errno))
                    break
        self.close()

    def build_message(self, cmd, **payload):
        return {
            "cmd": cmd,
            "payload": payload
        }

    def send_error(self, error_num):
        msg = self.build_message("ERROR", num=error_num, info=ERROR_DICT[error_num])
        self.server.async_msg.put_msg_by_user(msg, int(self.tid))

    def buy_f(self, payload):
        item_id = payload.get("item_id")
        if not item_id:
            self.send_error("006")
            return
        shop_item = self.server.user_manager.get_item_from_shop(item_id)
        if not shop_item:
            print(f"[{self.username}] Tried to buy non-existent item: {item_id}")
            self.send_error("006")
            return
        price = shop_item.get("price", 0)
        current_coins = self.server.user_manager.get_coins(self.username)
        owned_items = self.server.user_manager.get_user_color_collection(self.username)
        if item_id in owned_items:
            print(f"CLASS:client | PROC:buy_f | info:player already has item")
            self.send_error("006")
            return
        if current_coins < price:
            print(f"CLASS:client | PROC:buy_f | info:not enough money to buy item")
            self.send_error("006")
            return
        self.server.user_manager.remove_coins(self.username, price)
        self.server.user_manager.add_color_to_collection(self.username, item_id)
        new_coins = self.server.user_manager.get_coins(self.username)
        new_owned = self.server.user_manager.get_user_color_collection(self.username)
        msg = self.build_message("ACK", subject="buy", coins=new_coins, own=new_owned)
        self.server.async_msg.put_msg_by_user(msg, int(self.tid))

    def logout_f(self, payload):
        remember_me = payload.get("remember", False)
        if not remember_me:
            if self.username:
                print(f"[Logout] User {self.username} is logging out.")
                self.server.user_manager.logout_user(self.username)
        else:
            print(f"[Logout] {self.username} closed the game. Token kept.")
        self.close()

    def token_login_f(self, payload):
        user_name = payload.get("user")
        token = payload.get("token")
        device_id = payload.get("device_id")
        print(f"CLASS:client | PROC:token_login_f | proc got --> {device_id}")
        is_success = self.server.user_manager.check_auto_login(user_name, token, device_id)
        if is_success:
            self.state = STATE_LOBBY
            # coins add
            self.username = user_name
            total_coins = self.server.user_manager.get_coins(user_name)
            print(f"CLASS:client | PROC:token_login_f | total coins -- > {total_coins}")

            # here send also shop and owning
            i_own = self.server.user_manager.get_user_color_collection(self.username)
            msg = self.build_message("ACK", subject="auto_login", UDPport=self.server.UDP_port1,
                                     total_coins=total_coins,
                                     shop=self.server.shop, own=i_own)
            # coins add
            self.server.async_msg.put_msg_by_user(msg, int(self.tid))
            # send ack --> success
        else:
            self.send_error("007")
            # send ack --> fail

    def login_f(self, payload):
        user_name = payload.get("email")
        password = payload.get("password")
        # ------
        device_id = payload.get("device_id")
        remember_me = payload.get("remember_me")
        # ------
        is_success = self.server.user_manager.check_login(user_name, password, self.server.pepper)
        if is_success:
            self.state = STATE_LOBBY
            # coins add
            self.username = user_name
            token_to_send = None
            if remember_me:
                token_to_send = secrets.token_hex(32)
                self.server.user_manager.update_user_token(user_name, token_to_send, device_id)
                print(f"User {user_name} asked to be remembered. Token generated.")
            else:
                # אם לא רצו להיזכר, כדאי אפילו למחוק טוקן ישן מה-DB ליתר ביטחון
                self.server.user_manager.update_user_token(user_name, None, None)
                print(f"User {user_name} logged in without persistence.")
            total_coins = self.server.user_manager.get_coins(user_name)
            print(f"CLASS:client | PROC:login_f | total coins -- > {total_coins}")
            # here send also shop and owning
            i_own = self.server.user_manager.get_user_color_collection(self.username)
            msg = self.build_message("ACK", subject="login", UDPport=self.server.UDP_port1, total_coins=total_coins,
                                     shop=self.server.shop, own=i_own, token=token_to_send, user=user_name)
            # coins add
            self.server.async_msg.put_msg_by_user(msg, int(self.tid))
            # send ack --> success
        else:
            self.send_error("003")
            # send ack --> fail

    def signup_f(self, payload):

        user_name = payload.get("email")
        password = payload.get("password")
        # ------
        device_id = payload.get("device_id")
        remember_me = payload.get("remember_me")
        # ------
        is_registered = self.server.user_manager.register_user(user_name, password, self.server.pepper)
        if is_registered:
            print(f"CLASS:client | PROC:sign_up_f | signup succeed")

            self.state = STATE_LOBBY
            # coins add
            self.username = user_name
            token_to_send = None
            if remember_me:
                token_to_send = secrets.token_hex(32)
                self.server.user_manager.update_user_token(user_name, token_to_send, device_id)
                print(f"User {user_name} asked to be remembered. Token generated.")
            else:
                # אם לא רצו להיזכר, כדאי אפילו למחוק טוקן ישן מה-DB ליתר ביטחון
                self.server.user_manager.update_user_token(user_name, None, None)
                print(f"User {user_name} logged in without persistence.")

            i_own = self.server.user_manager.get_user_color_collection(self.username)
            msg = self.build_message("ACK", subject="signup", UDPport=self.server.UDP_port1, total_coins=0,
                                     shop=self.server.shop, own=i_own, token=token_to_send, user=user_name)
            self.server.async_msg.put_msg_by_user(msg, int(self.tid))
            # send ack --> success
        else:
            self.send_error("004")
            # send ack --> fail

    def color_f(self, payload):
        print(f"CLASS:client | PROC:color | info:in color_f!")

        self.snake_color = payload.get("color")
        self.server.players_manager.set_snake_color_locked(str(self.tid), self.snake_color)
        success = self.server.players_manager.add_new_player_to_game(self)
        # success mean | True --> if server found spot for me | False --> server put me on wait
        if success:
            self.need_new_board = True
            #self.send_new_board_f()
            #self.state = STATE_GAME
            #self.server.async_msg.player_ready_for_game(int(self.tid))
            #self.server.UDP_async_msg.player_ready_for_game(int(self.tid))
        else:
            print(f"CLASS:client | PROC:color | info:waiting for place in board")

    # --------------------------------------------------------------------------------------------------------------
    def send_new_board_f(self, sync=None, values=True):
        if not sync:
            sync = self.server.players_manager.get_full_sync(new_map=True)
        self.server.async_msg.put_msg_by_user(
            self.build_message("NEW_BOARD", sync=sync, UDPport=self.server.UDP_port1), int(self.tid))
        if values:
            self.state = STATE_GAME
            self.server.async_msg.player_ready_for_game(int(self.tid))
            self.server.UDP_async_msg.player_ready_for_game(str(self.tid))
        print("CLASS: client | PROC:send_new_board_f | info: send NEW_BOARD!")
    # --------------------------------------------------------------------------------------------------------------

    def key_f(self, payload):
        key_got = base64.b64decode(payload.get("key"))
        key_got = decrypt_aes_key(key_got, self.server.private_key)
        if key_got == "failed":
            print(f"CLASS:client | PROC:key_f | info:failed")

            # self.server.async_msg.put_msg_by_user(self.build_message("ERROR", num="009", info="Key not recognized"),
            #                                   int(self.tid))
        else:
            print(f"CLASS:client | PROC:key_f | info:success")

            self.state = STATE_AUTH
            self.transport_data.key = key_got
            self.server.async_msg.put_msg_by_user(self.build_message("ID", tid=str(self.tid)), int(self.tid))

    def leave_game_f(self, payload):
        print(f"Player {self.tid} finished death animation. Moving to LOBBY.")
        self.state = STATE_LOBBY
        self.server.async_msg.not_ready(int(self.tid))
        self.server.UDP_async_msg.not_ready(str(self.tid))

    def sync_me_f(self, payload):
        if self.state == STATE_GAME:
            self.sync_me = True

    def start_board_f(self, payload):
        # new player ask for board (future use maybe)
        sync = self.server.players_manager.get_full_sync()
        self.server.async_msg.put_msg_by_user(self.build_message("NEW_BOARD", sync=sync), int(self.tid))

    def send_with_sign(self, data_dict):
        try:
            print(f"CLASS:client | PROC:send_with_sign | state:{self.state} | data:{data_dict}")
            data_bytes = msgpack.packb(data_dict)
            # json_data = json.dumps(data_dict)  # dict --> JSON string
            self.send_with_size(data_bytes)  # string --> bytes
        except Exception as e:
            print("Send failed:", e)

    def recv_by_size(self, return_type="string"):
        return self.transport_data.recv_by_size()

    def send_with_size(self, data):
        self.transport_data.send_with_size(data)

    def close(self):
        try:
            if self.username:

                try:
                    cli_money = self.server.players_manager.pop_player_coins(self)
                    if cli_money and cli_money > 0:
                        self.server.user_manager.add_coins(self.username, cli_money)
                        print(f"[SAVED] {cli_money} coins saved for {self.username} before closing.")
                except Exception:
                    pass

                self.server.user_manager.save_users()
            self.server.UDP_async_msg.not_ready(str(self.tid))
            self.server.handle_client_udp_obj.remove_client(self.tid)

            self.server.remove_tcp_cli_obj(self)

            self.server.async_msg.not_ready(int(self.tid))
            self.server.players_manager.remove_player(self)
            # -----------------------------------
            self.server.user_manager.save_users()
            self.sock.close()
        except Exception as e:
            print(e)


class Server:
    def __init__(self, TCPport, UDPport1, UDPport2, ip="0.0.0.0"):
        self.lock = threading.RLock()
        self.forced_full_sync = False
        self.ip = ip
        self.TCP_port = TCPport
        self.UDP_port1 = UDPport1
        self.UDP_port2 = UDPport2
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_obj_lst = []
        self.players_manager = HoldPlayersData()
        self.handle_client_udp_obj = None
        self.async_msg: AsyncMessages = AsyncMessages()
        self.UDP_async_msg: UDPAsyncMessages = UDPAsyncMessages()
        self.user_manager = UserManager()
        self.pepper = "leehu_the_king"
        self.stop_event = threading.Event()

        # --- RSA --- #
        self.private_key_file = "private_key_leehu.pem"
        self.public_key_file = "public_key_leehu.pem"
        try:
            self.private_key, self.public_key = load_keys()
            print("load keys from file")
        except:
            print("generate key")
            self.private_key, self.public_key = generate_keys()
        self.pem_public_ready = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self.b64_public_ready = base64.b64encode(self.pem_public_ready).decode('utf-8')

        self.shop = self.user_manager.get_color_shop()
        # --- RSA --- #

    def start(self):
        self.udp_sock.bind((self.ip, self.UDP_port1))
        self.sock.bind((self.ip, self.TCP_port))
        self.sock.listen()
        self.run()

    def run(self):
        self.handle_client_udp_obj = HandleClientUDP(self, self.udp_sock)
        self.handle_client_udp_obj.start()
        # print(self.user_manager.refresh_all_tokens())
        # input("stop")
        i = 1
        threading.Thread(target=self.game_loop, daemon=True).start()
        while not self.stop_event.is_set():
            try:
                cli_sock, addr = self.sock.accept()
                self.async_msg.add_new_socket(cli_sock, i)
                client_obj = Client(self, cli_sock, i)

                self.client_obj_lst.append(client_obj)

                client_obj.start()
                i += 1
            except socket.error:
                print("socket error - > sever shutdown")
                break
            except Exception as e:
                print(str(e))
                break
        self.close()

    def game_loop(self):
        tick_id = 1
        next_sync_tick = 100
        INTERVAL = 100
        send_tcp = False
        udp_history = {}
        HISTORY_MAX_SIZE = 5

        for i in range(5):
            bot = BotClient(-1 * (i + 1))
            self.players_manager.add_new_player_to_game(bot, bot=True)
            color = [0, 0, 0]
            color[random.randint(0, 2)] = 255
            self.players_manager.set_snake_color_locked(str(bot.tid), [tuple(color)])
        while not self.stop_event.is_set():
            try:
                #print(self.async_msg.ready_for_game, "---------------------")
                self.players_manager.move_all_players(tick_id)  # lock in the file
                delta = self.players_manager.get_world_delta()  # lock in the file
                udp_history[str(tick_id)] = delta.copy()
                if tick_id > HISTORY_MAX_SIZE:
                    udp_history.pop(str(tick_id - HISTORY_MAX_SIZE), None)

                if self.forced_full_sync or tick_id >= next_sync_tick:  # prepare for tcp send (update board for all)
                    sync = self.players_manager.get_full_sync()  # lock in the file
                    if "full_grid" in sync:
                        tcp_delta = delta.copy()
                        tcp_delta["full_grid"] = sync["full_grid"]
                        tcp_delta.pop("remove")
                        tcp_delta.pop("add")
                        tcp_board_msg = self.build_message("BOARD", delta=tcp_delta, ID=tick_id)
                        send_tcp = True
                    next_sync_tick = tick_id + INTERVAL
                    self.forced_full_sync = False
                # -------------------------------------------------
                else:
                    # players who asked for personal sync
                    need_sync_players = [c for c in self.client_obj_lst if c.sync_me]
                    need_new_board_players = [c for c in self.client_obj_lst if c.need_new_board]
                    if need_sync_players or need_new_board_players:
                        sync = self.players_manager.get_full_sync()
                        sync_new_map = self.players_manager.get_full_sync(new_map=True)
                        if need_sync_players:
                            personal_tcp_delta = delta.copy()
                            personal_tcp_delta["full_grid"] = sync["full_grid"]
                            personal_tcp_delta.pop("remove", None)
                            personal_tcp_delta.pop("add", None)
                            personal_msg = self.build_message("BOARD", delta=personal_tcp_delta, ID=tick_id)
                            for cli in need_sync_players:
                                self.async_msg.put_msg_by_user(personal_msg, int(cli.tid))
                                cli.sync_me = False
                        for cli in need_new_board_players:
                            cli.send_new_board_f(sync=sync_new_map, values=True)
                            cli.need_new_board = False
                # --------------------------------------------------
                if delta.get("died"):
                    self.send_broadcast_death(delta["died"])
                    for p_id_str in delta["died"]:
                        dead_client = self.get_tcp_client_obj(p_id_str)
                        if dead_client:
                            #  coins add
                            cli_money = self.players_manager.pop_player_coins(dead_client)
                            if cli_money > 0 and dead_client.username:
                                self.user_manager.add_coins(dead_client.username, cli_money)
                                print(f"Saved {cli_money} coins for {dead_client.username}")
                            total_money = self.user_manager.get_coins(
                                dead_client.username) if dead_client.username else 0
                            print(f"CLASS:server | PROC:game_loop | total_money:{total_money} | dead cli:{dead_client.username}")

                            self.send_update_coins(p_id_str, total_money)
                            #  coins add
                            dead_client.state = STATE_LOBBY
                            #self.async_msg.not_ready(int(p_id_str))
                            #self.UDP_async_msg.not_ready(str(p_id_str))
                            self.players_manager.remove_player(dead_client)
                            dead_client.snake_color = None
                            if p_id_str in self.handle_client_udp_obj.tid_to_ID:
                                self.handle_client_udp_obj.tid_to_ID[p_id_str] = -1
                            print(f"Server updated state for dead player {p_id_str} back to LOBBY")
                udp_board_msg = self.build_message("BOARD", delta=delta, ID=tick_id, history=udp_history)
                self.UDP_async_msg.put_msg_to_all(udp_board_msg)
                if send_tcp:
                    self.async_msg.put_msg_to_all(tcp_board_msg)
                    send_tcp = False
                tick_id += 1
            except Exception as e:
                print("Caught error in game loop:")
                traceback.print_exc()
            time.sleep(BROADCAST_TIME)
        print("game loop over")

    def send_broadcast_death(self, died_list):
        msg = self.build_message("DIED", died=died_list)
        self.async_msg.put_msg_to_all(msg)

    def send_update_coins(self, cli_tid, coins):
        msg = self.build_message("COINS", amount=coins)
        self.async_msg.put_msg_by_user(msg, int(cli_tid))

    def get_tcp_client_obj(self, tid):
        str_tid = str(tid)
        for cli in self.client_obj_lst:
            if str(cli.tid) == str_tid:
                return cli
        return None

    def remove_tcp_cli_obj(self, cli):
        with self.lock:
            if cli in self.client_obj_lst:
                self.client_obj_lst.remove(cli)

    def build_message(self, cmd, **payload):
        return {
            "cmd": cmd,
            "payload": payload
        }

    def close(self):
        try:
            self.close_all_threads()
            self.user_manager.save_users()
            self.sock.close()
        except socket.error:
            print("socket error while try to close")

    def close_all_threads(self):
        self.stop_event.set()
        for client_obj in self.client_obj_lst:
            client_obj.join()
            self.players_manager.remove_player(client_obj)
        self.client_obj_lst.clear()


def main():
    server_obj = Server(46767, 44444, 47676)
    server_obj.start()


if __name__ == "__main__":
    main()

# ##
