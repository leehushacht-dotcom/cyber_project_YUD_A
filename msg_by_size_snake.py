"""author: Leehu Shacht"""

import socket

SIZE_HEADER_FORMAT = "000000000|" # n digits for data size + one delimiter
size_header_size = len(SIZE_HEADER_FORMAT)
TCP_DEBUG = False

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes

# structure of aes encrypt data
# 0-16 bytes iv
# rest msg


class TransportData:
    def __init__(self, sock, key):
        self.sock = sock
        self.key = key
        self.wait = False

    def send_with_size(self, data):
        if type(data) != bytes:
            data = data.encode()
        if self.key != "KEY" and not self.wait:
            try:
                iv = get_random_bytes(16)
                plaintext = data
                cipher = AES.new(self.key, AES.MODE_CBC, iv)
                ciphertext = cipher.encrypt(pad(plaintext, AES.block_size))
                data = iv + ciphertext
            except Exception as e:
                print(f"encryption failed: {e}")
                return
        len_data = len(data)
        len_data = str(len(data)).zfill(size_header_size - 1) + "|"
        len_data = len_data.encode()
        data = len_data + data

        self.sock.sendall(data)
        if TCP_DEBUG and len(len_data) > 0 and self.key != "KEY" and not self.wait:  # later better debug, just for now
            data = data[:100]
            if type(data) == bytes:
                try:
                    data = data.decode()
                except (UnicodeDecodeError, AttributeError):
                    pass
            print(f"\nSent({len_data})>>>{data}")
        elif TCP_DEBUG:
            print("sent no encrypt")
        self.wait=False

    def recv_by_size(self, return_type="bytes"):
        str_size = b""
        data_len = 0
        while len(str_size) < size_header_size:
            _d = self.sock.recv(size_header_size - len(str_size))
            if len(_d) == 0:
                str_size = b""
                break
            str_size += _d
        data = b""
        str_size = str_size.decode()
        if str_size != "":
            data_len = int(str_size[:size_header_size - 1])
            while len(data) < data_len:
                _d = self.sock.recv(data_len - len(data))
                if len(_d) == 0:
                    data = b""
                    break
                data += _d
        if data_len != len(data):
            data = b""  # Partial data is like no data !
            return data
        if self.key != "KEY":
            #print(len(data))
            try:
                iv = data[:16]
                ciphertext = data[16:]
                cipher = AES.new(self.key, AES.MODE_CBC, iv)
                decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
                data = decrypted

            except Exception as e:
                print(f"Decryption failed: {e}")
                return b""

        if TCP_DEBUG and len(str_size) > 0 and self.key != "KEY":
            data_to_print = data[:100]
            if type(data_to_print) == bytes:
                try:
                    data_to_print = data_to_print.decode()
                except (UnicodeDecodeError, AttributeError):
                    pass
            print(f"\nReceive({str_size})>>>{data_to_print}")
        if return_type == "string":
            return data.decode()
        return data
