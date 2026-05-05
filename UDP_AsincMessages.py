"""author: Leehu Shacht"""

import threading
from collections import defaultdict


class UDPAsyncMessages:
    def __init__(self):
        self.lock_async_msgs = threading.Lock()
        self.ready_for_game = {}       # tid -> bool
        self.addr_to_tid = {}          # (ip, port)*addr -> tid
        self.tid_to_msg = defaultdict(list)  # tid -> list of messages

    def add_new_player(self, tid, addr):
        """Register a new player"""
        with self.lock_async_msgs:
            self.tid_to_msg[tid] = []
            self.addr_to_tid[addr] = tid
            self.ready_for_game[tid] = True

    def delete_tid(self, tid):
        with self.lock_async_msgs:
            self.tid_to_msg.pop(tid, None)
            self.ready_for_game.pop(tid, None)
            # also remove addr mapping
            for a, t in list(self.addr_to_tid.items()):
                if t == tid:
                    del self.addr_to_tid[a]
                    break

    def check_is_exist(self, addr):
        with self.lock_async_msgs:
            tid = self.addr_to_tid.get(addr)
            return tid in self.tid_to_msg if tid is not None else False

    def put_msg_in_async_msgs(self, data, tid):
        """Append a message to a specific player's queue"""
        with self.lock_async_msgs:
            self.tid_to_msg[tid].append(data)

    def put_msg_by_user(self, data, addr):
        """Append a message using the UDP addr"""
        with self.lock_async_msgs:
            tid = self.addr_to_tid.get(addr)
            if tid is None:
                return "ERROR|004|client not exist"
            self.tid_to_msg[tid].append(data)
            return "success"

    def put_msg_to_all(self, data):
        """Send to all ready players"""
        with self.lock_async_msgs:
            for tid, ready in self.ready_for_game.items():
                if ready:
                    self.tid_to_msg[tid].append(data)

    def player_ready_for_game(self, tid):
        """Mark player ready"""
        with self.lock_async_msgs:
            if tid in self.ready_for_game:
                self.ready_for_game[tid] = True

    def not_ready(self, tid):
        """Mark player not ready"""
        with self.lock_async_msgs:
            if tid in self.ready_for_game:
                self.ready_for_game[tid] = False

    def get_async_messages(self, tid):
        """Return all messages for a player and clear the queue"""
        with self.lock_async_msgs:
            msgs = list(self.tid_to_msg.get(tid, []))
            self.tid_to_msg[tid] = []
            return msgs