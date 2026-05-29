__author__ = "Leehu Shacht"

import threading
from collections import defaultdict


class AsyncMessages:
    """
        this class provide global messages area for server that handle muktyclients by threads
        it enables many threads to communicate by one dictionary (self.async_msgs)
        each thread might put data to specific other thread (the key is the other thread socket)
        each thread can get his messages by his socket
        this class is thread safe
    """

    def __init__(self):
        self.lock_async_msgs = threading.Lock()
        self.async_msgs = defaultdict(list)
        self.ready_for_game = {}
        self.sock_by_user = {}

    def add_new_socket(self, new_client_sock, tid):
        """
            call to this method right after socket accept with client socket
        """
        with self.lock_async_msgs:
            self.async_msgs[new_client_sock] = []
            self.sock_by_user[tid] = new_client_sock
            self.ready_for_game[tid] = False

    def delete_socket(self, sock):
        """
            when disconnect
        """
        with self.lock_async_msgs:
            self.async_msgs.pop(sock, None)

    def check_is_exist(self, tid):
        with self.lock_async_msgs:
            if tid in self.sock_by_user:
                return self.sock_by_user[tid] in self.async_msgs
            return False

    def put_msg_in_async_msgs(self, data, other_sock):
        with self.lock_async_msgs:
            self.async_msgs[other_sock].append(data)

    def put_msg_by_user(self, data, user):
        try:
            with self.lock_async_msgs:
                self.async_msgs[self.sock_by_user[user]].append(data)
            return 'success'
        except KeyError:
            return "client not exist"
        except Exception:
            return "General error"

    def put_msg_to_all(self, data):
        """send to only "ready" players"""
        with self.lock_async_msgs:
            for tid, is_ready in self.ready_for_game.items():
                if is_ready:
                    try:
                        sock = self.sock_by_user[tid]
                        self.async_msgs[sock].append(data)
                    except KeyError:
                        print("rare moment")
                        pass

    def player_ready_for_game(self, tid):
        with self.lock_async_msgs:
            if tid in self.ready_for_game:
                self.ready_for_game[tid] = True

    def not_ready(self, tid):
        with self.lock_async_msgs:
            if tid in self.ready_for_game:
                self.ready_for_game[tid] = False

    def get_async_messages_to_send(self, my_sock):
        msgs = []
        with self.lock_async_msgs:
            if self.async_msgs.get(my_sock):
                msgs = self.async_msgs[my_sock]
                self.async_msgs[my_sock] = []
        return msgs
