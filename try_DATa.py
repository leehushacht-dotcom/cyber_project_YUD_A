"""author: Leehu Shacht"""

import threading
import random
from PIL import Image

opposites = {"U": "D", "D": "U", "L": "R", "R": "L"}
BOARD_HEIGHT = 100
BOARD_WIDTH = 100
MAX_FRUITS = 700
MAX_COINS = 80

# --- world objects --- #
SNAKE_BODY = 1
SNAKE_HEAD = 2
APPLE = 3
WALL = 4
WATER = 5
COIN = 6
# --- world objects --- #


GOOD_VALUE = 10
GOOD_APPLE_VALUE = 1
BLOCK_SIZE = 10


class SpatialGrid:
    def __init__(self):
        self.grid = {}
        self.wall = set()
        self.water = set()
        self.fruits = set()
        self.coins = set()

    def get_cell(self, x, y):
        return (x//BLOCK_SIZE, y//BLOCK_SIZE)

    def add_point(self, x, y, kind, player, color_index=None):
        cell = self.get_cell(x, y)
        if cell not in self.grid:
            self.grid[cell] = set()
        self.grid[cell].add((x, y, kind, player, color_index))
        if kind == APPLE:
            self.fruits.add((x, y))
        elif kind == COIN:
            self.coins.add((x, y))

    def add_wall(self, x, y):
        self.wall.add((x, y))

    def add_water(self, x, y):
        self.water.add((x, y))

    def remove_point(self, x, y, kind, player, ticket):
        cell = self.get_cell(x, y)
        if cell in self.grid:
            self.grid[cell] = {p for p in self.grid[cell] if
                               not (p[0] == x and p[1] == y and p[2] == kind and p[3] == player and p[4] == ticket)}
            if kind == APPLE:
                self.fruits.discard((x, y))
            elif kind == COIN:
                self.coins.discard((x, y))
            if not self.grid[cell]:
                del self.grid[cell]

    def get_point_value(self, x, y, hardcore=False):
        safe_radius = 2 if hardcore else 0
        for dx in range(-safe_radius, safe_radius + 1):
            for dy in range(-safe_radius, safe_radius + 1):
                check_x, check_y = x + dx, y + dy  # point in the radius we want
                if (check_x, check_y) in self.wall or (check_x, check_y) in self.water:
                    return 0

        points = self.nearby_points_c(x, y)
        value = 10000
        for point in points:
            kind = point[2]  # שולפים את סוג האובייקט
            # אנחנו מתייחסים רק לנחשים! תפוחים לא פוסלים מיקום.
            if kind in (SNAKE_HEAD, SNAKE_BODY):
                distance = abs(x - point[0]) + abs(y - point[1])
                if distance < value:
                    value = distance
            elif kind in (APPLE, COIN):
                distance = abs(x - point[0]) + abs(y - point[1])
                if distance == 0:
                    return 0
                if hardcore and kind == APPLE:
                    if distance < 3:
                        return 0
        return value

    def nearby_points_c(self, x, y):
        cell_x, cell_y = self.get_cell(x, y)
        points = []
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                cell = (cell_x + dx, cell_y + dy)
                if cell in self.grid:
                    points.extend(list(self.grid[cell]))
        return points

    def is_cell_free(self, x, y):
        points = self.nearby_points_c(x, y)
        for px, py, kind, player, ticket in points:
            if abs(px - x) <= 1 and abs(py - y) <= 1:
                return False
        return True

    def is_exact_cell_free_from_snakes(self, x, y):
        cx, cy = self.get_cell(x, y)
        points = self.get_points_in_cell((cx, cy))
        if points:
            for px, py, kind, owner, ticket in points:
                if px == x and py == y and kind not in (APPLE, COIN):
                    return False
        return True

    def get_points_in_cell(self, cell):
        return list(self.grid[cell]) if cell in self.grid else None


class HoldPlayersData:
    def __init__(self):
        self.cur_tick = 0
        self.changed = False
        self.newest_bot = None
        self.fruit_to_tick = {}
        self.coin_to_tick = {}
        self.fruits_num = 0
        self.coins_num = 0
        self.board_is_full_A = False
        self.board_is_full_C = False
        self.live_heads_pos = {}
        self.tid_to_obj = {}
        self.player_to_color = {}  # color is list of colors of the snake
        self.player_to_coin = {}
        self.player_to_boost = {}
        self.died_snakes = []
        self.coli = []
        self.waiting_players = []
        self.waiting_fruits_count = 0
        self.waiting_coins_count = 0
        self.tid_to_usernames = {}
        self.to_add = []
        self.to_remove = []
        self.GRID = SpatialGrid()
        self.in_game_players = {}  # key = player,(dict) value = body, direction
        self.in_game_bots = []
        self.game_lock = threading.Lock()
        self.users_lock = threading.Lock()
        self.load_map_from_image()
        self.build_fruits_and_coins_board()
        self.directions_map = {
            "U": (0, -1),
            "D": (0, 1),
            "L": (-1, 0),
            "R": (1, 0)}

    def _object_add(self, x, y, kind, player_obj, ticket):
        p_id = str(player_obj.tid) if player_obj else None
        self.GRID.add_point(x, y, kind, player_obj, ticket)
        self.to_add.append((x, y, kind, p_id, ticket))

    def _object_remove(self, x, y, kind, player_obj, ticket):
        p_id = str(player_obj.tid) if player_obj else None
        self.GRID.remove_point(x, y, kind, player_obj, ticket)
        self.to_remove.append((x, y, kind, p_id, ticket))

    def _spawn_apple(self, x, y, val, force_spawn=False):
        if self.fruits_num < MAX_FRUITS or force_spawn:
            self._object_add(x, y, APPLE, None, val)
            self.fruits_num += 1
            self.fruit_to_tick[(x,y)] = int(self.cur_tick)
        else:
            self.board_is_full_A = True

    def _spawn_coin(self, x, y, force_spawn=False):
        if self.coins_num < MAX_COINS or force_spawn:
            self._object_add(x, y, COIN, None, 1)
            self.coins_num += 1
            self.coin_to_tick[(x, y)] = int(self.cur_tick)
        else:
            self.board_is_full_C = True

    def _remove_exist_apple(self, x, y, val):
        self._object_remove(x, y, APPLE, None, val)
        self.fruits_num -= 1
        self.fruit_to_tick.pop((x,y), None)

    def _remove_exist_coin(self, x, y):
        self._object_remove(x, y, COIN, None, 1)
        self.coins_num -= 1
        self.coin_to_tick.pop((x, y), None)

    def spawn_wall(self, x, y):
        with self.game_lock:
            self.GRID.add_wall(x, y)

    def spawn_water(self, x, y):
        with self.game_lock:
            self.GRID.add_water(x, y)
    """
    def build_fruits_and_coins_board(self):  # improve create logic, *also in spawn after eating(other funcs)
        turn = 1
        for i in range(100):
            x = (i % 10) * 10 + random.randint(0, 9)
            y = (i // 10) * 10 + random.randint(0, 9)
            with self.game_lock:
                if (x, y) in self.GRID.wall or (x, y) in self.GRID.water:
                    continue
                if turn % 2 == 0:
                    val = self.create_fruit_value()
                    self._spawn_apple(x, y, val)
                else:
                    self._spawn_coin(x, y)
                turn += 1
    """

    def build_fruits_and_coins_board(self, target_amount=500, ingame=False):
        max_x = BOARD_WIDTH - 1
        max_y = BOARD_HEIGHT - 1
        items_spawned = 0
        attempts = 0
        max_attempts = target_amount * 3
        with self.game_lock:
            occupied_spots = set(self.GRID.wall).union(self.GRID.water)
            if ingame:
                for points in self.GRID.grid.values():
                    for px, py, kind, player, ticket in points:
                        occupied_spots.add((px, py))
            while items_spawned < target_amount and attempts < max_attempts:
                attempts += 1
                x = random.randint(0, max_x)
                y = random.randint(0, max_y)
                if (x, y) in occupied_spots:
                    continue
                if items_spawned % 5 != 0:
                    val = self.create_fruit_value()
                    self._spawn_apple(x, y, val)
                else:
                    self._spawn_coin(x, y)
                occupied_spots.add((x, y))
                items_spawned += 1

        print(f"Board initialized with {items_spawned} items.")

    def load_map_from_image(self, image_path="base_map.png"):
        img = Image.open(image_path).convert('RGB')
        width, height = img.size
        for x in range(width):
            for y in range(height):
                r, g, b = img.getpixel((x, y))
                if r == 0 and g == 0 and b == 0:
                    self.spawn_wall(x, y)
                elif r == 255 and g == 255 and b == 255:
                    self.spawn_water(x, y)

    def _find_safe_spawn(self, min_dist=GOOD_APPLE_VALUE, max_attempts=10, direction=False):
        for _ in range(max_attempts):
            x = random.randint(5, BOARD_WIDTH - 6)
            y = random.randint(5, BOARD_HEIGHT - 6)
            in_wall_or_water = (x, y) in self.GRID.wall or (x, y) in self.GRID.water
            if not in_wall_or_water:
                dist_from_objects = self.GRID.get_point_value(x, y, direction)
            if in_wall_or_water:
                continue
            if dist_from_objects >= min_dist:
                if direction:
                    options = ["U", "D", "R", "L"]
                    return (x, y), options[random.randint(0, 3)]
                return (x, y), None

        return None, None

    def add_new_player_to_game(self, cli_obj, bot=False):
        with self.game_lock:
            pos, x_y = self._find_safe_spawn(GOOD_VALUE, 20, True)
            if pos and x_y:
                with self.users_lock:
                    self.live_heads_pos[cli_obj] = (pos[0], pos[1])
                    self.tid_to_obj[str(cli_obj.tid)] = cli_obj
                    self.in_game_players[cli_obj] = {}
                    self.in_game_players[cli_obj]["body"] = [[pos[0], pos[1], 1]]
                    self.in_game_players[cli_obj]["dir"] = x_y  # U = up, D = down, L = left, R = right
                    self.in_game_players[cli_obj]["last_dir"] = x_y
                    self.in_game_players[cli_obj]["dir_queue"] = []
                    self.in_game_players[cli_obj]["length"] = 5
                    self.in_game_players[cli_obj]["color_counter"] = len(self.in_game_players[cli_obj]["body"])
                    self.in_game_players[cli_obj]["growth"] = 4
                    # רישום הראש בלוח כדי שכולם יראו אותו בפריים הבא
                    self._object_add(pos[0], pos[1], SNAKE_HEAD, cli_obj, 1)
                    if bot:
                        print("is bot")
                        self.in_game_bots.append(cli_obj)
                        self.newest_bot = int(cli_obj.tid)
                        self.tid_to_usernames[str(cli_obj.tid)] = cli_obj.username
                        self.changed = True
                    else:
                        self.tid_to_usernames[str(cli_obj.tid)] = cli_obj.username
                        cli_obj.is_ready = True
                return True
            else:
                with self.users_lock:
                    self.waiting_players.append((cli_obj, bot))
                return False

    def remove_player(self, cli_obj, bot=False):
        with self.users_lock:
            if (cli_obj, bot) in self.waiting_players:
                self.waiting_players.remove((cli_obj, bot))
                return
        with self.game_lock:
            if cli_obj in self.in_game_players:
                self._snake_died(cli_obj)

    def change_direction(self, cli_obj, direction):
        if direction not in opposites.keys():
            return "Code not supported"
        with self.game_lock:
            if cli_obj not in self.in_game_players:
                return "not in game"
            queue = self.in_game_players[cli_obj]["dir_queue"]
            # אם יש פקודות בתור, נבדוק מול הפקודה האחרונה בתור. אם לא, נבדוק מול הכיוון הנוכחי.
            last_requested = queue[-1] if queue else self.in_game_players[cli_obj]["dir"]
            # פילטר ספאם (אם שלחו לנו את אותו כיוון ברצף, נתעלם)
            if last_requested == direction:
                return "spam ignored"

            # בודקים האם הפקודה החדשה חוקית אחרי הפקודה הקודמת שביקשנו!
            if opposites[last_requested] != direction:
                if len(queue) < 2:  # נאפשר לשמור עד 2 פניות מהירות מראש
                    queue.append(direction)
                return "success"
            else:
                return "opposite"

    def move_all_players(self, server_tick):
        self.cur_tick = server_tick
        print(self.fruits_num, "|", self.coins_num)
        if self.board_is_full_A:
            if random.random() > 0.25:
                print("cleaning!")
                self._cleanup_unseen_apples_fast()
                self.board_is_full_A = False
        if self.board_is_full_C:
            if random.random() > 0.25:
                print("cleaning!")
                self._clean_old_coins()
                self.board_is_full_C = False
        self.update_bots(server_tick)
        with self.game_lock:
            moving_this_tick = []
            with self.users_lock:
                boosts = self.player_to_boost.copy()

            for snake in list(self.in_game_players.keys()):
                is_boosting = boosts.get(snake, False)

                player_data = self.in_game_players[snake]
                head_x = player_data["body"][0][0]
                head_y = player_data["body"][0][1]
                in_water = (head_x, head_y) in self.GRID.water

                if (is_boosting or in_water) and self.in_game_players[snake]["length"] > 5:
                    moving_this_tick.append(snake)
                elif server_tick % 2 == 0:
                    moving_this_tick.append(snake)

            # שלב 1: שולפים מהתור ומעדכנים כיוונים לכל הנחשים!
            for snake in moving_this_tick:
                queue = self.in_game_players[snake]["dir_queue"]
                if queue:
                    self.in_game_players[snake]["dir"] = queue.pop(0)
            self.coli = self._check_collisions(moving_this_tick)
            for snake in moving_this_tick:
                is_boosting = boosts.get(snake, False)
                self._move_player_by_direction(snake, is_boosting)

        if self.waiting_fruits_count > 0 and random.random() > 0.25:
            with self.game_lock:
                x_y, _ = self._find_safe_spawn()
                if x_y:
                    val = self.create_fruit_value()
                    self._spawn_apple(x_y[0], x_y[1], val)
        if self.waiting_fruits_count > 0:
            self.waiting_fruits_count -= 1
        if self.waiting_coins_count > 0 and random.random() > 0.25:
            with self.game_lock:
                x_y, _ = self._find_safe_spawn()
                if x_y:
                    self._spawn_coin(x_y[0], x_y[1])
        if self.waiting_coins_count > 0:
            self.waiting_coins_count -= 1

        waiting_player_data = None
        with self.users_lock:
            if self.waiting_players:
                waiting_player_data = self.waiting_players.pop(0)

        # 2. אם שלפנו מישהו, נחפש לו מקום בנחת (ללא מנעולים!)
        if waiting_player_data:
            player, bot = waiting_player_data
            with self.game_lock:
                pos, x_y = self._find_safe_spawn(GOOD_VALUE, 20, True)
                if pos:
                    with self.users_lock:
                        self.tid_to_obj[str(player.tid)] = player
                        self.in_game_players[player] = {
                            "body": [[pos[0], pos[1], 1]],
                            "last_dir": x_y,
                            "dir_queue": [],
                            "dir": x_y,
                            "length": 5,
                            "color_counter": 1,
                            "growth": 4
                        }
                        self._object_add(pos[0], pos[1], SNAKE_HEAD, player, 1)
                        if bot:
                            print("is bot")
                            self.in_game_bots.append(player)
                            self.newest_bot = int(player.tid)
                            self.tid_to_usernames[str(player.tid)] = player.username
                            self.changed = True

                        else:
                            self.tid_to_usernames[str(player.tid)] = player.username
                            player.is_ready = True
                    if not bot:
                        print("send NEW_BOARD from file")
                        player.need_new_board = True
                        return True, player
                else:
                    print("wait!")
                    with self.users_lock:
                        self.waiting_players.append((player, bot))
        return False, None

    def _cleanup_unseen_apples_fast(self):
        count = 0
        visible_cells = set()
        for hx, hy in self.live_heads_pos.values():
            head_cell_x, head_cell_y = self.GRID.get_cell(hx, hy)
            for cx in range(head_cell_x - 3, head_cell_x + 4):
                for cy in range(head_cell_y - 3, head_cell_y + 4):
                    visible_cells.add((cx, cy))
        apples_to_check = list(self.GRID.fruits)
        for ax, ay in apples_to_check:
            apple_cell = self.GRID.get_cell(ax, ay)
            if apple_cell not in visible_cells:
                points = self.GRID.get_points_in_cell(apple_cell)  #
                if points:
                    for px, py, kind, owner, ticket in points:
                        if px == ax and py == ay and kind == APPLE:  #
                            count += 1
                            self._remove_exist_apple(ax, ay, ticket)  #
                            break
        print(count ,"apples cleaned!")

    def _cleanup_unseen_coins_fast(self):
        count = 0
        visible_cells = set()
        for hx, hy in self.live_heads_pos.values():
            head_cell_x, head_cell_y = self.GRID.get_cell(hx, hy)
            for cx in range(head_cell_x - 3, head_cell_x + 4):
                for cy in range(head_cell_y - 3, head_cell_y + 4):
                    visible_cells.add((cx, cy))
        coins_to_check = list(self.GRID.coins)
        for ax, ay in coins_to_check:
            coin_cell = self.GRID.get_cell(ax, ay)
            if coin_cell not in visible_cells:
                points = self.GRID.get_points_in_cell(coin_cell)  #
                if points:
                    for px, py, kind, owner, ticket in points:
                        if px == ax and py == ay and kind == COIN:  #
                            count += 1
                            self._remove_exist_coin(ax, ay)  #
                            break
        print(count ,"coins cleaned!")

    def _clean_old_coins(self, amount=5):
        sorted_items = sorted(self.coin_to_tick.items(), key=lambda x: x[1])
        print(sorted_items)
        last_tick = self.cur_tick
        count = amount
        for pos, tick in sorted_items:
            coin_cell = self.GRID.get_cell(pos[0], pos[1])
            if last_tick - tick > 100:
                points = self.GRID.get_points_in_cell(coin_cell)
                if points:
                    for px, py, kind, owner, ticket in points:
                        if px == pos[0] and py == pos[1] and kind == COIN:
                            self._remove_exist_coin(pos[0], pos[1])
                            count -= 1
                            break
            else:
                break
            if count <= 0:
                break


    def get_full_sync(self, new_map=False):  # for new players 1 time, next time use self.get_world_delta()
        with self.game_lock:
            with self.users_lock:
                full_grid = []
                for points in list(self.GRID.grid.values()):
                    for px, py, kind, player, ticket in list(points):
                        p_id = str(player.tid) if player else None
                        full_grid.append((px, py, kind, p_id, ticket))
#                "add": final_add,
 #               "remove": list(self.to_remove),
  #              "died": list(self.died_snakes),
   #             "leaders": self._get_leaders(),
    #            "length": {str
                msg = {
                    "full_grid": full_grid,
                    "board_size": (BOARD_WIDTH, BOARD_HEIGHT),
                    "players_color": self.player_to_color.copy(),
                    "leaders": self._get_leaders(),
                    "length": {str(snake.tid): data["length"] for snake, data in self.in_game_players.items()},
                    "usernames": self.tid_to_usernames.copy()
                }

                if new_map:
                    msg["walls"] = list(self.GRID.wall)
                    msg["water"] = list(self.GRID.water)
                return msg

    def _move_player_by_direction(self, snake, is_boosting):
        if snake not in self.in_game_players:
            print("no way")
            return
        dir_key = self.in_game_players[snake]["dir"]
        self.in_game_players[snake]["last_dir"] = dir_key
        dx, dy = self.directions_map[dir_key]
        self._move_player(snake, dx, dy, is_boosting)

    def _move_player(self, snake, dx, dy, is_boosting):
        if snake not in self.in_game_players:
            return

        player_data = self.in_game_players[snake]
        body = player_data["body"]
        old_head = body[0]
        new_head = [old_head[0] + dx, old_head[1] + dy]

        if snake in self.coli:
            self._snake_died(snake)
            return
        in_water = tuple(new_head) in self.GRID.water

        # 1. בדיקת אכילה ועדכון מחסן צמיחה
        apple_val = self._is_snake_ate(new_head)
        if apple_val > 0:
            #if snake in self.in_game_players:
             #   print("bot ate and grow")
            player_data["growth"] += apple_val
            player_data["length"] += apple_val
            self.waiting_fruits_count += 1
        elif apple_val < 0:
            shrink = abs(apple_val)
            actual_shrink = min(shrink, player_data["length"] - 5)
            if actual_shrink > 0:
                player_data["length"] -= actual_shrink
                for _ in range(actual_shrink):
                    if len(body) > 1:
                        tail = body.pop()
                        tail_x, tail_y, tail_ticket = tail[0], tail[1], tail[2]
                        self._object_remove(tail_x, tail_y, SNAKE_BODY, snake, tail_ticket)
        player_data["color_counter"] += 1
        current_ticket = player_data["color_counter"]
        body.insert(0, [new_head[0], new_head[1], current_ticket])
        self.live_heads_pos[snake] = (new_head[0], new_head[1])

        # 2. עדכון ויזואלי בגריד (ראש וגוף)

        self._object_add(new_head[0], new_head[1], SNAKE_HEAD, snake, current_ticket)
        self._object_remove(old_head[0], old_head[1], SNAKE_HEAD, snake, old_head[2])
        self._object_add(old_head[0], old_head[1], SNAKE_BODY, snake, old_head[2])

        if player_data["growth"] > 0:
            # אנחנו בתהליך צמיחה מאכילה קודמת - לא מורידים זנב
            player_data["growth"] -= 1
        else:
            # תנועה רגילה - מורידים זנב
            tail = body.pop()
            tail_x, tail_y, tail_ticket = tail[0], tail[1], tail[2]
            if tail not in body:
                self._object_remove(tail[0], tail[1], SNAKE_BODY, snake, tail_ticket)
        if not is_boosting:
            is_boosting = in_water
        if is_boosting and player_data["length"] > 4:
            if random.random() < 0.3 and not in_water:
                if len(body) > 5:
                    # אפשרות א': השחקן בתהליך גדילה (growth > 0)
                    if player_data["growth"] > 0:
                        # אנחנו פשוט "שורפים" את חוליית הגדילה הבאה
                        player_data["growth"] -= 1
                        player_data["length"] -= 1
                        # שים לב: לא עשינו body.pop(), לכן הזנב נשאר במקום והנחש פשוט יגדל פחות
                    # אפשרות ב': השחקן לא גדל כרגע (חייבים למחוק חוליה פיזית)
                    elif len(body) > 5:
                        extra_tail = body.pop()
                        extra_tail_x, extra_tail_y, extra_tail_ticket = extra_tail[0], extra_tail[1], extra_tail[2]
                        player_data["length"] -= 1
                        self._object_remove(extra_tail_x, extra_tail_y, SNAKE_BODY, snake, extra_tail_ticket)
                        self._spawn_apple(extra_tail_x, extra_tail_y, 1)

    def _is_snake_ate(self, x_y):  # game_lock needed when calling
        cx, cy = self.GRID.get_cell(x_y[0], x_y[1])
        points = self.GRID.get_points_in_cell((cx, cy))
        if points:
            for point in points:
                if x_y[0] == point[0] and x_y[1] == point[1] and point[2] == APPLE:
                    val = point[4]
                    self._remove_exist_apple(point[0], point[1], val)
                    return val
        return 0

    def _snake_died(self, snake):   # game_lock needed when calling
        body = self.in_game_players[snake]["body"]
        count = 1
        for x_y in body:
            if count != 1:
                self._object_remove(x_y[0], x_y[1], SNAKE_BODY, snake, x_y[2])
            else:
                self._object_remove(x_y[0], x_y[1], SNAKE_HEAD, snake, x_y[2])
            # think of better way
            if random.random() > 0.40:
                val = self.create_better_fruit_value()
                self._spawn_apple(x_y[0], x_y[1], val, force_spawn=True)
            elif random.random() > 0.80:
                self._spawn_coin(x_y[0], x_y[1], force_spawn=True)
                if self.waiting_coins_count > 0:
                    if random.random() > 0.35:
                        self.waiting_coins_count -= 1

            count += 1
        self.live_heads_pos.pop(snake, None)
        self.in_game_players.pop(snake, None)
        self.died_snakes.append(str(snake.tid))
        is_bot = snake in self.in_game_bots
        if is_bot:
            self.in_game_bots.remove(snake)
        with self.users_lock:
            # 2א: מחיקה מילונית עם Casting ל-String
            self.tid_to_obj.pop(str(snake.tid), None)
            self.tid_to_usernames.pop(str(snake.tid), None)
            if str(snake.tid) in self.player_to_color:
                del self.player_to_color[str(snake.tid)]
                self.changed = True
            # 2ב: אם זה בוט, מכניסים אותו בחזרה בצורה מוגנת!
            if is_bot:
                snake.tid = self.newest_bot - 1
                self.newest_bot = int(snake.tid)
                self.waiting_players.append((snake, True))

                color = [0, 0, 0]
                color[random.randint(0, 2)] = 255
                self._set_snake_color(str(snake.tid), [tuple(color)])
                self.changed = True

    def _is_snake_ate_check(self, x_y):  # game_lock needed when calling
        cx, cy = self.GRID.get_cell(x_y[0], x_y[1])
        points = self.GRID.get_points_in_cell((cx, cy))
        if points:
            for point in points:
                if x_y[0] == point[0] and x_y[1] == point[1] and point[2] == APPLE:
                    return point[4]
        return 0

    def _check_collisions(self, moving_snakes):  # game_lock needed when calling
        next_positions = {}
        collisions = set()
        heads_map = {}
        for snake, data in list(self.in_game_players.items()):
            head = data["body"][0]
            if snake in moving_snakes:
                dx, dy = self.directions_map[data["dir"]]
                new_head = (head[0] + dx, head[1] + dy)

                #  בודקים את ה-growth מתוך ה-data ולא מה-snake
                apple_val = self._is_snake_ate_check(new_head)
                is_growing = (apple_val > 0) or (data.get("growth", 0) > 0)

                tail_to_free = tuple(data["body"][-1]) if not is_growing else None
            else:
                new_head = (head[0], head[1])
                tail_to_free = None
            next_positions[snake] = {"new_head": new_head, "tail_to_free": tail_to_free}
        # . זיהוי התנגשויות
        for snake in moving_snakes:
            nh = next_positions[snake]["new_head"]
            if (nh[0], nh[1]) in self.GRID.wall:
                collisions.add(snake)
                continue
            if not (0 <= nh[0] < BOARD_WIDTH and 0 <= nh[1] < BOARD_HEIGHT):
                collisions.add(snake)
                continue
            if nh in heads_map:
                collisions.add(snake)
                collisions.add(heads_map[nh])  # both dead
            else:
                heads_map[nh] = snake
            cx, cy = self.GRID.get_cell(nh[0], nh[1])
            points = self.GRID.get_points_in_cell((cx, cy))
            if points:
                for px, py, kind, owner, ticket in points:
                    if (px, py) == nh and kind != APPLE:  # nh --> new head --> x,y
                        if kind == COIN:
                            with self.users_lock:
                                if snake in self.player_to_coin:
                                    self.player_to_coin[snake] += 1
                                else:
                                    self.player_to_coin[snake] = 1
                            self._remove_exist_coin(px, py)
                            self.waiting_coins_count += 1
                        elif owner != snake:
                            if (px, py) != next_positions.get(owner, {}).get("tail_to_free"):
                                collisions.add(snake)
        return collisions

    def update_bots(self, tick_id):
        turn_options = {"U": ["L", "R"], "D": ["L", "R"], "L": ["U", "D"], "R": ["U", "D"]}
        with self.game_lock:
            for i, bot in enumerate(self.in_game_bots):
                if bot not in self.in_game_players:
                    continue
                # בדיקה פעם ב-2 טיקים (מספיק מהיר להגיב, לא כבד לשרת)
                if (tick_id + i) % 2 != 0:
                    continue

                bot_data = self.in_game_players[bot]
                head_x, head_y = bot_data["body"][0][0], bot_data["body"][0][1]
                current_dir = bot_data["dir"]

                # ==========================================
                # 1. מיפוי כיוונים בטוחים (Survival First)
                # ==========================================
                forward = current_dir
                left, right = turn_options[current_dir]
                options = [forward, left, right]
                safe_options = []

                # בודקים אילו מהכיוונים באמת פנויים בצעד הבא
                for d in options:
                    dx, dy = self.directions_map[d]
                    nx, ny = head_x + dx, head_y + dy
                    if (0 <= nx < BOARD_WIDTH and 0 <= ny < BOARD_HEIGHT) and \
                            self.GRID.is_exact_cell_free_from_snakes(nx, ny) and \
                            (nx, ny) not in self.GRID.wall:
                        safe_options.append(d)

                if not safe_options:
                    continue  # אין לאן לברוח, מתים

                # חוק ברזל: אם קדימה חסום, חייבים לפנות עכשיו!
                if forward not in safe_options:
                    bot_data["dir"] = random.choice(safe_options)
                    continue

                # ==========================================
                # 2. רדאר מניעה (Lookahead)
                # ==========================================
                # למרות שקדימה פנוי כרגע, נסתכל 2 צעדים קדימה כדי לא להיכנס למלכודת
                fdx, fdy = self.directions_map[forward]
                nnx, nny = head_x + fdx * 2, head_y + fdy * 2

                forward_looks_dangerous = False
                if not (0 <= nnx < BOARD_WIDTH and 0 <= nny < BOARD_HEIGHT) or \
                        not self.GRID.is_exact_cell_free_from_snakes(nnx, nny) or \
                        (nnx, nny) in self.GRID.wall:
                    forward_looks_dangerous = True

                if forward_looks_dangerous and len(safe_options) > 1:
                    if random.random() < 0.70:
                        turn_choices = [d for d in safe_options if d != forward]
                        if turn_choices:
                            bot_data["dir"] = random.choice(turn_choices)
                            continue

                # ==========================================
                # 3. חיפוש אוכל "עצלן" (Lazy Food Seeking)
                # ==========================================
                VISION_RADIUS = 5
                apple_xy = self._get_closest_apple(head_x, head_y)

                is_tracking_food = False

                if apple_xy:
                    dist_to_apple = abs(head_x - apple_xy[0]) + abs(head_y - apple_xy[1])
                    if dist_to_apple <= VISION_RADIUS:
                        is_tracking_food = True
                        # 40% סיכוי להסתובב לכיוון האוכל (עדיין עצלן!)
                        if random.random() < 0.65:
                            wanted_dir = current_dir

                            if abs(head_x - apple_xy[0]) > abs(head_y - apple_xy[1]):
                                if apple_xy[0] > head_x:
                                    wanted_dir = "R"
                                elif apple_xy[0] < head_x:
                                    wanted_dir = "L"
                            else:
                                if apple_xy[1] > head_y:
                                    wanted_dir = "D"
                                elif apple_xy[1] < head_y:
                                    wanted_dir = "U"

                            if wanted_dir in safe_options:
                                bot_data["dir"] = wanted_dir
                                continue

                # ==========================================
                # 4. שוטטות מקומית (Local Loitering / Coiling)
                # ==========================================
                # אם הבוט לא עוקב אחרי אוכל כרגע, הוא יתחיל להסתובב סביב עצמו
                if not is_tracking_food:
                    # 15% סיכוי לפנייה יגרום לו לעשות לולאות ועיגולים קטנים
                    if random.random() < 0.25:
                        turn_choices = [d for d in safe_options if d != forward]
                        if turn_choices:
                            bot_data["dir"] = random.choice(turn_choices)


    """
    def update_bots(self, tick_id):
        options_dict = {"U": ("R", "L", "U"), "D": ("R", "L", "D"), "R": ("U", "D", "R"), "L": ("U", "D", "L")}
        directions = ["U", "D", "L", "R"]
        with self.game_lock:
            for i, bot in enumerate(self.in_game_bots):
                if (tick_id + i) % 2 != 0:  # separate the work --> less work
                    continue
                if bot not in self.in_game_players:
                    continue
                g_score = {}
                last_dir = self.in_game_players[bot]["dir"]
                options = options_dict[last_dir]
                # for now random movement, later smarter even A star
                # self.in_game_players[bot]["dir"] = options[random.randint(0, 2)]
                head = tuple(self.in_game_players[bot]["body"][0])
                apple_xy = self._get_closest_apple(head[0], head[1])
                if not apple_xy:
                    continue
                g_score[head] = 0
                open_list = [(head, self.f_calculation(head, apple_xy, 0))]
                final_way = {}
                dept = 0
                found_path = False
                default = None
                while open_list and dept < 80:
                    dept += 1
                    min_item = min(open_list, key=lambda x: x[1])
                    curr_head = min_item[0]
                    if curr_head == apple_xy:
                        found_path = True
                        node = apple_xy
                        first_dir = None
                        while node in final_way:
                            parent_node, dir_taken = final_way[node]
                            first_dir = dir_taken  # בסוף הלולאה זה יהיה הצעד הראשון!
                            node = parent_node
                        if first_dir:
                            if opposites[self.in_game_players[bot]["dir"]] != first_dir:
                                self.in_game_players[bot]["dir"] = first_dir
                        break
                    for item in directions:
                        new_x = curr_head[0] + self.directions_map[item][0]
                        new_y = curr_head[1] + self.directions_map[item][1]
                        if dept == 1:
                            if item not in options:
                                continue
                            else:
                                # default
                                if self.GRID.is_exact_cell_free_from_snakes(new_x, new_y):
                                    default = item
                        if not (0 <= new_x < BOARD_WIDTH and 0 <= new_y < BOARD_HEIGHT):
                            continue
                        if not self.GRID.is_exact_cell_free_from_snakes(new_x, new_y) and (new_x, new_y) != apple_xy:
                            continue
                        g = g_score[curr_head] + 1
                        f_calc = self.f_calculation((new_x, new_y), apple_xy, g)
                        if (new_x, new_y) not in g_score.keys():
                            g_score[(new_x, new_y)] = g
                            open_list.append(((new_x, new_y), f_calc))
                            final_way[(new_x, new_y)] = (curr_head, item)
                        elif (new_x, new_y) in g_score and (g_score[curr_head] + 1) < g_score[(new_x, new_y)]:
                            g_score[(new_x, new_y)] = g_score[curr_head] + 1
                            open_list.append(((new_x, new_y), f_calc))
                            final_way[(new_x, new_y)] = (curr_head, item)
                    open_list.remove(min_item)
                if not found_path:
                    if default:
                        self.in_game_players[bot]["dir"] = default
    """
    def pop_player_coins(self, cli_obj):
        """
        השרת קורא לפעולה הזו כששחקן מת.
        היא שולפת את כמות המטבעות שהשחקן אסף, ומוחקת אותו מהרישום הזמני.
        """
        with self.users_lock:
            return self.player_to_coin.pop(cli_obj, 0)

    def get_world_delta(self):
        with self.game_lock:
            remove_set = set(self.to_remove)  # o(1)
            final_add = [item for item in self.to_add if item not in remove_set]
            delta = {
                "add": final_add,
                "remove": list(self.to_remove),
                "died": list(self.died_snakes),
                "leaders": self._get_leaders(),
                "length": {str(snake.tid): data["length"] for snake, data in self.in_game_players.items()}
            }

            if self.changed:
                with self.users_lock:
                    delta["usernames"] = self.tid_to_usernames.copy()
                    delta["players_color"] = self.player_to_color.copy()
                self.changed = False

            self.to_add.clear()
            self.to_remove.clear()
            self.died_snakes.clear()
            return delta

    def _set_snake_color(self, player_tid, color):  # need call with users_lock
        self.player_to_color[player_tid] = color
        self.changed = True

    def set_snake_color_locked(self, player_tid, color):  # need call with users_lock
        with self.users_lock:
            self.player_to_color[player_tid] = color
            self.changed = True

    def _get_leaders(self):  # need call with game_lock
        best = []
        for key, value in list(self.in_game_players.items()):
            best.append((str(key.tid), value["length"]))
        best.sort(key=lambda x: x[1], reverse=True)
        return best[:5]

    def get_cli_obj(self, p_tid):
        with self.users_lock:
            return self.tid_to_obj.get(str(p_tid), None)

    def create_fruit_value(self):
        x = random.random()
        if x < 0.1:
            return -1
        if x < 0.6:
            return 1
        if x < 0.9:
            return 2
        return 3

    def create_better_fruit_value(self):
        x = random.random()
        if x < 0.4:
            return 1
        if x < 0.8:
            return 2
        return 3

    def set_boost(self, cli_obj, boost):
        with self.users_lock:
            self.player_to_boost[cli_obj] = boost

    def get_boost(self, cli_obj):
        with self.users_lock:
            return self.player_to_boost.get(cli_obj, None)

    def _get_closest_apple(self, head_x, head_y):  # game_lock needed when calling
        if not self.GRID.fruits:
            return None
        closest_apple = min(
            self.GRID.fruits,
            key=lambda apple: abs(head_x - apple[0]) + abs(head_y - apple[1])
        )
        return tuple(closest_apple)

    def f_calculation(self, box, target_box, g_score):  # tuple(,)
        x1 = box[0]
        y1 = box[1]
        x2 = target_box[0]
        y2 = target_box[1]
        return abs(y2 - y1) + abs(x2 - x1) + g_score
