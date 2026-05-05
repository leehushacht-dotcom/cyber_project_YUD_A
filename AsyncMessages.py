"""author: Leehu Shacht"""

import threading
from datetime import datetime
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
        self.sum_cards_number_by_tid = defaultdict(int)
        self.lock_async_msgs = threading.Lock()
        self.async_msgs = defaultdict(list)
        self.ready_for_game = {}
        self.sock_by_user = {}
        self.lock_sum = threading.Lock()
        self.way_to_win = defaultdict(list)
        self.email_to_tid = {}

    def add_new_socket(self, new_client_sock, tid):
        """
            call to this method right after socket accept with client socket
        """
        with self.lock_async_msgs:
            self.async_msgs[new_client_sock] = []
            self.sock_by_user[tid] = new_client_sock
            self.ready_for_game[tid] = False

        with self.lock_sum:
            self.sum_cards_number_by_tid[tid] = 0
            self.way_to_win[tid] = []

    def add_new_email_to_tid(self, email, tid):
        with self.lock_async_msgs:
            self.email_to_tid[email] = tid

    def delete_socket(self, sock):
        """
            cwhen dissconnect
        """
        with self.lock_async_msgs:
            del self.async_msgs [sock]

    def check_is_exist(self, tid):
        with self.lock_async_msgs:
            for key in self.async_msgs.keys():
                if self.sock_by_user.get(tid) == key:
                    return True
            return False

    def check_is_email_exist(self, email):
        with self.lock_async_msgs:
            return email in self.email_to_tid.keys()

    def set_email_offline(self, email):
        with self.lock_async_msgs:
            if email in self.email_to_tid.keys():
                self.email_to_tid[email] = None  # become offline, not full remove
                return True
            return False


    def delete_email(self, email):
        with self.lock_async_msgs:
            if email in self.email_to_tid:
                del self.email_to_tid[email]
                return True
            return False

    def put_msg_in_async_msgs(self, data, other_sock):
        with self.lock_async_msgs:
            self.async_msgs[other_sock].append(data)

    """
    def update_socket_to_email(self, old_tid, email):
        with self.lock_async_msgs:
            if old_tid in self.sock_by_user:
                sock = self.sock_by_user.pop(old_tid)  # מוציא את הישן
                self.sock_by_user[email] = sock  # מכניס עם המפתח החדש

                # מעדכן גם את התור של ההודעות
                msgs = self.async_msgs.pop(sock, [])
                self.async_msgs[sock] = msgs
    """

    def get_online_users(self):
        with self.lock_async_msgs:
            return [email for email, tid in self.email_to_tid.items() if tid is not None]

    def put_msg_by_email(self, data, email):
        try:
            with self.lock_async_msgs:
                tid = self.email_to_tid.get(email)

                # בדיקה כפולה: האם המשתמש קיים והאם הוא מחובר (TID אינו None)
                if tid is not None:
                    sock = self.sock_by_user[tid]
                    self.async_msgs[sock].append(data)
                    return 'success'
                else:
                    return "OFFLINE"  # המשתמש קיים במערכת אבל לא מחובר כרגע
        except KeyError:
            return "NOT_FOUND"  # האימייל בכלל לא מופיע במילון

    def put_msg_by_user(self, data, user):
        try:
            with self.lock_async_msgs:
                self.async_msgs[self.sock_by_user[user]].append(data)
            return 'success'
        except KeyError:
            return "EROR|"+"004|"+"client not exist"
        except Exception:
            return "EROR|"+"001|"+"General error"

#    def put_msg_to_all(self, data):
#        self.lock_async_msgs.acquire()
#        for s in self.async_msgs.keys():
#            #if self.ready_for_game[s]:
#            self.async_msgs[s].append(data)
#        self.lock_async_msgs.release()

    def put_msg_to_all(self, data):
        """send to only "ready" players"""
        with self.lock_async_msgs:
            # אנחנו עוברים על רשימת המשתמשים (tid)
            for tid, is_ready in self.ready_for_game.items():
                if is_ready:  # רק אם השחקן מוכן!
                    try:
                        # מוצאים את ה-Socket של השחקן
                        sock = self.sock_by_user[tid]
                        # מוסיפים את ההודעה לתור שלו
                        self.async_msgs[sock].append(data)
                    except KeyError:
                        print("rare moment")
                        pass  # למקרה נדיר שה-Socket נמחק בדיוק באותו רגע

    def player_ready_for_game(self, tid):
        with self.lock_async_msgs:
            if tid in self.ready_for_game:
                self.ready_for_game[tid] = True

    def not_ready(self, tid):
        with self.lock_async_msgs:
            if tid in self.ready_for_game:
                self.ready_for_game[tid] = False
    """
        def get_async_messages_to_send(self, my_sock):
            msgs = []
            if self.async_msgs [my_sock] != []:
                self.lock_async_msgs .acquire()
                msgs =  self.async_msgs[my_sock]
                self.async_msgs[my_sock] = []
                self.lock_async_msgs .release()
            return msgs
    """

    def get_async_messages_to_send(self, my_sock):
        msgs = []
        with self.lock_async_msgs:  # המנעול למעלה!
            if self.async_msgs.get(my_sock):  # בטוח יותר מ- != [] וימנע שגיאת KeyError
                msgs = self.async_msgs[my_sock]
                self.async_msgs[my_sock] = []
        return msgs

#  ignore! related to somthing else
    def add_to_sum_by_tid(self, tid, sum_value):
        try:
            with self.lock_sum:
                self.sum_cards_number_by_tid[tid] += sum_value
                if tid not in self.way_to_win:
                    self.way_to_win[tid] = []
                self.way_to_win[tid].append(sum_value)
            return self.is_this_win(self.sum_cards_number_by_tid[tid])
        except Exception as e:
            print(str(e))


    def get_history_by_tid(self, tid):
        return list(self.way_to_win.get(tid, []))


    def is_this_win(self,number):
        number_str = str(number)
        if len(number_str) >=3:
            return len(set(number_str))==1
        return False


    def get_sum_by_tid(self,tid):
        return self.sum_cards_number_by_tid[tid]


    def get_max_sum(self):
        max_key,max_value = max(self.sum_cards_number_by_tid.items(), key = lambda item:item[1])
        now = datetime.now()
        only_time = now.strftime("%H:%M:%S")
        return max_key,max_value,only_time,len(self.sum_cards_number_by_tid)


    def get_max_sum_2(self):
        now = datetime.now()
        only_time = now.strftime("%H:%M:%S")
        return only_time, len(self.sum_cards_number_by_tid)
