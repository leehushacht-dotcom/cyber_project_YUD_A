import threading
import pickle
import secrets
import hashlib


class UserManager:
    def __init__(self):
        self.pickle_file = "my_users.pkl"
        self.lock = threading.Lock()
        self.users = self._load_users()
        # --- Color Shop ---
        self.color_catalog = {
            # start colors
            "c_white": {"name": "White", "price": 0, "rgb": (255, 255, 255), "rarity": "Common"},
            "c_red": {"name": "Red", "price": 0, "rgb": (255, 50, 50), "rarity": "Common"},
            "c_green": {"name": "Green", "price": 0, "rgb": (50, 255, 50), "rarity": "Common"},
            "c_blue": {"name": "Blue", "price": 0, "rgb": (50, 50, 255), "rarity": "Common"},

            # colors need to buy
            # --- (Uncommon) ---
            "c_yellow": {"name": "Yellow", "price": 50, "rgb": (255, 255, 50), "rarity": "Uncommon"},
            "c_orange": {"name": "Orange", "price": 50, "rgb": (255, 140, 0), "rarity": "Uncommon"},
            "c_cyan":   {"name": "Cyan", "price": 75, "rgb": (0, 255, 255), "rarity": "Uncommon"},

            # --- (Rare) ---
            "c_purple": {"name": "Purple", "price": 100, "rgb": (150, 50, 255), "rarity": "Rare"},
            "c_lime":   {"name": "Toxic Lime", "price": 120, "rgb": (180, 255, 50), "rarity": "Rare"},
            "c_blood":  {"name": "Blood Red", "price": 150, "rgb": (138, 3, 3), "rarity": "Rare"},

            # --- (Epic) ---
            "c_silver": {"name": "Silver", "price": 200, "rgb": (192, 192, 192), "rarity": "Epic"},
            "c_bronze": {"name": "Bronze", "price": 200, "rgb": (205, 127, 50), "rarity": "Epic"},
            "c_gold":   {"name": "Pure Gold", "price": 300, "rgb": (255, 215, 0), "rarity": "Epic"},
            "c_rose":   {"name": "Rose Gold", "price": 300, "rgb": (183, 110, 121), "rarity": "Epic"},

            # --- (Legendary) ---
            "c_void":   {"name": "Void Black", "price": 500, "rgb": (15, 15, 20), "rarity": "Legendary"},
            "c_neon":   {"name": "Neon Pink", "price": 500, "rgb": (255, 0, 255), "rarity": "Legendary"},
            "c_ice":    {"name": "Glacier Ice", "price": 600, "rgb": (175, 238, 238), "rarity": "Legendary"},

            # --- (Mythic)  ---
            "c_diamond": {"name": "Plasma Teal", "price": 1000, "rgb": (0, 255, 170), "rarity": "Mythic"},
            "c_phoenix": {"name": "Neon Flare", "price": 1000, "rgb": (255, 20, 90), "rarity": "Mythic"},
            "c_hacker": {"name": "Matrix Green", "price": 1200, "rgb": (0, 255, 65), "rarity": "Mythic"}
        }

    def _load_users(self):
        try:
            with open(self.pickle_file, "rb") as f:
                return pickle.load(f)
        except:
            return {}

    def _save_users_private(self):
        """פונקציה פנימית ששומרת לדיסק בלי לנעול שוב"""
        with open(self.pickle_file, "wb") as f:
            pickle.dump(self.users, f)

    def save_users(self):
        """הפונקציה הציבורית למי שקורא מבחוץ"""
        with self.lock:
            self._save_users_private()

    def _is_user_exists(self, username):
        return username in self.users

    def register_user(self, username, password, pepper, device_id=None):
        """ רושם משתמש חדש עם סיסמה מוצפנת """
        with self.lock:
            if self._is_user_exists(username):
                return False
            salt = secrets.token_hex(16)
            # יצירת ה-Hash (סיסמה + מלח)
            hashed_pass = hashlib.sha256((password + pepper + salt).encode()).hexdigest()

            self.users[username] = {
                "hash": hashed_pass,
                "salt": salt,
                "best_score": 0,
                "coins": 0,
                "color_collection": ["c_white", "c_red", "c_green", "c_blue"],  # color name
                "device_id": device_id,
                "token": None
            }
            self._save_users_private()
            return True

    def update_user_token(self, username, new_token, device_id):
        with self.lock:
            if username in self.users:
                print("update all token thing")
                self.users[username]["token"] = new_token
                self.users[username]["device_id"] = device_id
                self._save_users_private()

    def check_auto_login(self, username, token, device_id):
        with self.lock:
            user_data = self.users.get(username)
            if not user_data:
                return False
            s_token = user_data.get("token")
            s_device_id = user_data.get("device_id")
            print(token, device_id)
            print(s_token, s_device_id)
            if s_token and s_device_id:
                token_match = secrets.compare_digest(token, s_token)
                device_match = secrets.compare_digest(device_id, s_device_id)
                return token_match and device_match
            return False

    def logout_user(self, username):
        """ מוחק את הטוקן של המשתמש כדי לבטל את ה-Auto-Login """
        with self.lock:
            if username in self.users:
                self.users[username]["token"] = None
                # אנחנו משאירים את ה-device_id, אבל בלי טוקן אי אפשר להיכנס
                self._save_users_private()
                return True
            return False

    def check_login(self, username, password, pepper):
        """ בודק האם השם והסיסמה נכונים """
        with self.lock:
            user_data = self.users.get(username)
            if not user_data:
                return False

            stored_hash = user_data["hash"]
            salt = user_data["salt"]
            # חישוב ה-Hash של מה שהמשתמש הקליד עכשיו
            check_hash = hashlib.sha256((password + pepper + salt).encode()).hexdigest()

            return check_hash == stored_hash

    def add_coins(self, username, coins):
        with self.lock:
            if username in self.users:
                self.users[username]["coins"] += coins

    def remove_coins(self, username, coins):
        with self.lock:
            if username in self.users:
                self.users[username]["coins"] -= coins
                self._save_users_private()

    def get_coins(self, user):
        with self.lock:
            user_data = self.users.get(user)
            return user_data["coins"] if user_data else 0

    def add_color_to_collection(self, username, color):
        with self.lock:
            if username in self.users:
                self.users[username]["color_collection"].append(color)
                self._save_users_private()

    def update_best_score(self, username, best_score):
        with self.lock:
            if username in self.users:
                self.users[username]["best_score"] = best_score

    def get_color_shop(self):
        with self.lock:
            return self.color_catalog

    def get_user_color_collection(self, username):
        with self.lock:
            if username in self.users:
                if "color_collection" not in self.users[username]:
                    self.users[username]["color_collection"] = ["c_white", "c_red", "c_green", "c_blue"]
                if not self.users[username]["color_collection"]:
                    self.users[username]["color_collection"] = ["c_white", "c_red", "c_green", "c_blue"]
                # self._save_users_private()
                return self.users[username]["color_collection"]
            return []

    def refresh_all_tokens(self):
        """
        מבצע איפוס גלובלי לכל הטוקנים במערכת.
        פעולה זו מחייבת את כל המשתמשים (גם אלו שסימנו Remember Me)
        לבצע התחברות מלאה עם שם משתמש וסיסמה בפעם הבאה.
        """
        count = 0
        with self.lock:
            for user_email in self.users:
                print(user_email)
                # בודקים אם למשתמש בכלל יש טוקן פעיל לפני שמנקים
                if self.users[user_email].get('token') is not None:
                    self.users[user_email]['token'] = None
                    self.users[user_email]['device_id'] = None
                    count += 1

            # שמירה פיזית של הקובץ לאחר השינוי
            self._save_users_private()

        print(f"[Security] Global refresh completed. {count} users were forced to logout.")
        return count

    def get_item_from_shop(self, item):
        return self.color_catalog.get(item)



