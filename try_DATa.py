__author__ = "Leehu Shacht"

import threading
import random
from PIL import Image

opposites = {"U": "D", "D": "U", "L": "R", "R": "L"}
BOARD_HEIGHT = 100
BOARD_WIDTH = 100
BLOCK_SIZE = 10

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


class SpatialGrid:
    def __init__(self):
        self.grid = {}
        self.wall = set()
        self.water = set()
        self.fruits = set()
        self.coins = set()

    def get_cell(self, x, y):
        return x//BLOCK_SIZE, y//BLOCK_SIZE

    def add_point(self, x, y, kind, player, color_index=None):
        # add part to grid, if in new cell we create the cell first
        # also add to self sets
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
        # every point is unique so we can easily remove it
        # also remove from self sets
        cell = self.get_cell(x, y)
        if cell in self.grid:
            target = (x, y, kind, player, ticket)
            self.grid[cell].discard(target)
            if kind == APPLE:
                self.fruits.discard((x, y))
            elif kind == COIN:
                self.coins.discard((x, y))
            if not self.grid[cell]:
                del self.grid[cell]

    def get_spawn_safety_distance(self, x, y, is_player=False):
        # check if in water or wall
        safe_radius = 2 if is_player else 0
        for dx in range(-safe_radius, safe_radius + 1):
            for dy in range(-safe_radius, safe_radius + 1):
                if (x + dx, y + dy) in self.wall or (x + dx, y + dy) in self.water:
                    return 0

        points = self.nearby_points_c(x, y)
        closest_snake_dist = 10000
        for point in points:
            kind = point[2]
            distance = abs(x - point[0]) + abs(y - point[1])
            if kind in (APPLE, COIN):
                if distance == 0:
                    return 0

            elif kind in (SNAKE_HEAD, SNAKE_BODY):
                if is_player and distance < 3:
                    return 0
                if distance < closest_snake_dist:
                    closest_snake_dist = distance
        return closest_snake_dist

    def nearby_points_c(self, x, y):
        cell_x, cell_y = self.get_cell(x, y)
        points = []
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                cell = (cell_x + dx, cell_y + dy)
                if cell in self.grid:
                    points.extend(self.grid[cell])
        return points

    def is_exact_point_free_from_snakes(self, x, y):
        # made for check next step
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
        self.flowers = set()
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
            self.fruit_to_tick[(x, y)] = int(self.cur_tick)
        else:
            # too many apples, ask for cleaning
            self.board_is_full_A = True

    def _spawn_coin(self, x, y, force_spawn=False):
        if self.coins_num < MAX_COINS or force_spawn:
            self._object_add(x, y, COIN, None, 1)
            self.coins_num += 1
            self.coin_to_tick[(x, y)] = int(self.cur_tick)
        else:
            # too many coins, ask for cleaning
            self.board_is_full_C = True

    def _remove_exist_apple(self, x, y, val):
        self._object_remove(x, y, APPLE, None, val)
        self.fruits_num -= 1
        self.fruit_to_tick.pop((x, y), None)

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

    def spawn_flower(self, x, y):
        with self.game_lock:
            self.flowers.add((x, y))

    def build_fruits_and_coins_board(self, target_amount=500, ingame=False):
        max_x = BOARD_WIDTH - 1
        max_y = BOARD_HEIGHT - 1
        items_spawned = 0
        attempts = 0
        max_attempts = target_amount * 3
        with self.game_lock:
            # all the occupied points
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
        if random.random() > 0.5:
            image_path = "special_map.png"
        img = Image.open(image_path).convert('RGB')
        width, height = img.size
        for x in range(width):
            for y in range(height):
                r, g, b = img.getpixel((x, y))
                if r == 0 and g == 0 and b == 0:
                    self.spawn_wall(x, y)
                elif r == 255 and g == 255 and b == 255:
                    self.spawn_water(x, y)
                elif r == 0 and g == 0 and b == 255:
                    self.spawn_flower(x, y)

    def _find_safe_spawn(self, min_dist=GOOD_APPLE_VALUE, max_attempts=10, direction=False):
        for _ in range(max_attempts):
            x = random.randint(5, BOARD_WIDTH - 6)
            y = random.randint(5, BOARD_HEIGHT - 6)
            dist_from_objects = self.GRID.get_spawn_safety_distance(x, y, direction)
            if dist_from_objects >= min_dist:
                if direction:
                    options = ["U", "D", "R", "L"]
                    return (x, y), options[random.randint(0, 3)]
                return (x, y), None
        return None, None

    def add_new_player_to_game(self, cli_obj, bot=False):
        # new player want to join
        with self.game_lock:
            pos, x_y = self._find_safe_spawn(GOOD_VALUE, 20, True)
            if pos and x_y:
                # found good start spot
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
                    self._object_add(pos[0], pos[1], SNAKE_HEAD, cli_obj, 1)
                    self.changed = True
                    if bot:
                        self.in_game_bots.append(cli_obj)
                        self.newest_bot = int(cli_obj.tid)
                        self.tid_to_usernames[str(cli_obj.tid)] = cli_obj.username
                    else:
                        self.tid_to_usernames[str(cli_obj.tid)] = cli_obj.username
                        cli_obj.is_ready = True
                return True
            else:
                # not found good start spot, we add him to the waiting list
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
            # we need to compare to the last dir in list not to the last dir done unless the list is empty
            last_requested = queue[-1] if queue else self.in_game_players[cli_obj]["dir"]

            if last_requested == direction:
                return "spam ignored"

            # check legal
            if opposites[last_requested] != direction:
                if len(queue) < 2:  # list size
                    queue.append(direction)
                return "success"
            else:
                return "opposite"

    def move_all_players(self, server_tick):
        self.cur_tick = server_tick
        # print(self.fruits_num, "|", self.coins_num)

        self.update_bots(server_tick)
        with self.game_lock:
            if self.board_is_full_A:
                if random.random() > 0.25:
                    # print("cleaning apples!")
                    self._cleanup_unseen_apples_fast()
                    self.board_is_full_A = False
            if self.board_is_full_C:
                if random.random() > 0.25:
                    # print("cleaning coins!")
                    self._clean_old_coins()
                    self.board_is_full_C = False
            # who moves this tick
            moving_this_tick = []
            with self.users_lock:
                boosts = self.player_to_boost.copy()

            for snake in list(self.in_game_players.keys()):
                is_boosting = boosts.get(snake, False)

                player_data = self.in_game_players[snake]
                # if player boosting or on water we add him also
                head_x = player_data["body"][0][0]
                head_y = player_data["body"][0][1]
                in_water = (head_x, head_y) in self.GRID.water
                if (is_boosting or in_water) and self.in_game_players[snake]["length"] > 5:
                    moving_this_tick.append(snake)
                elif server_tick % 2 == 0:
                    moving_this_tick.append(snake)

            # only moving snakes this turn
            for snake in moving_this_tick:
                # update direction
                queue = self.in_game_players[snake]["dir_queue"]
                if queue:
                    self.in_game_players[snake]["dir"] = queue.pop(0)
            # update all the collision snakes
            self.coli = self._check_collisions(moving_this_tick)
            # moving all snakes
            for snake in moving_this_tick:
                is_boosting = boosts.get(snake, False)
                self._move_player_by_direction(snake, is_boosting)
        # update fruit and coin board
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
        # we add one snake at a time from waiting list
        with self.users_lock:
            if self.waiting_players:
                waiting_player_data = self.waiting_players.pop(0)

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
                            self.in_game_bots.append(player)
                            #self.newest_bot = int(player.tid)
                            self.tid_to_usernames[str(player.tid)] = player.username
                        else:
                            self.tid_to_usernames[str(player.tid)] = player.username
                            player.is_ready = True
                        self.changed = True
                    if not bot:
                        # print("send NEW_BOARD from file")
                        player.need_new_board = True
                        return True, player
                else:
                    with self.users_lock:
                        self.waiting_players.append((player, bot))
        return False, None

    def _cleanup_unseen_apples_fast(self, amount=10, hard_core=False):
        count = 0
        visible_cells = set()
        # all seen cells
        for cli_obj, (hx, hy) in self.live_heads_pos.items():
            if cli_obj in self.in_game_bots:
                continue
            head_cell_x, head_cell_y = self.GRID.get_cell(hx, hy)
            for cx in range(head_cell_x - 2, head_cell_x + 3):
                for cy in range(head_cell_y - 2, head_cell_y + 3):
                    visible_cells.add((cx, cy))

        candidates = []
        for cell_xy, points in list(self.GRID.grid.items()):
            if cell_xy not in visible_cells:
                for px, py, kind, owner, ticket in points:
                    if kind == APPLE:
                        candidates.append((px, py, ticket))

        # we take random apples, so it keep the map balanced
        apples_to_delete = random.sample(candidates, min(amount, len(candidates)))
        for px, py, ticket in apples_to_delete:
            self._remove_exist_apple(px, py, ticket)
        if apples_to_delete:
            pass
            # print(f"{len(apples_to_delete)} apples cleanly scattered-removed!")

    def _clean_old_coins(self, amount=5):
        visible_cells = set()
        # all seen cells
        for cli_obj, (hx, hy) in self.live_heads_pos.items():
            if cli_obj in self.in_game_bots:
                continue
            head_cell_x, head_cell_y = self.GRID.get_cell(hx, hy)
            for cx in range(head_cell_x - 2, head_cell_x + 3):
                for cy in range(head_cell_y - 2, head_cell_y + 3):
                    visible_cells.add((cx, cy))

        # only unseen and old
        candidates = []
        for (cx, cy), tick_spawned in self.coin_to_tick.items():
            if self.cur_tick - tick_spawned > 100:
                cell_coords = self.GRID.get_cell(cx, cy)
                if cell_coords not in visible_cells:
                    candidates.append((cx, cy))

        # random remove
        coins_to_delete = random.sample(candidates, min(amount, len(candidates)))
        for cx, cy in coins_to_delete:
            self._remove_exist_coin(cx, cy)

    def get_full_sync(self, new_map=False):
        # return full board data
        with self.game_lock:
            with self.users_lock:
                full_grid = []
                for points in list(self.GRID.grid.values()):
                    for px, py, kind, player, ticket in list(points):
                        p_id = str(player.tid) if player else None
                        full_grid.append((px, py, kind, p_id, ticket))
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
                    msg["flowers"] = list(self.flowers)
                return msg

    def _move_player_by_direction(self, snake, is_boosting):
        # set next move
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

        # check if he made collision
        if snake in self.coli:
            self._snake_died(snake)
            return
        in_water = tuple(new_head) in self.GRID.water
        # if he ate
        apple_val = self._is_snake_ate(new_head)
        if apple_val > 0:
            player_data["growth"] += apple_val
            player_data["length"] += apple_val
            self.waiting_fruits_count += 1
        elif apple_val < 0:
            shrink = abs(apple_val)
            actual_shrink = min(shrink, player_data["length"] - 5)  # min length = 5
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
        # add new head to grid
        self._object_add(new_head[0], new_head[1], SNAKE_HEAD, snake, current_ticket)
        self._object_remove(old_head[0], old_head[1], SNAKE_HEAD, snake, old_head[2])
        self._object_add(old_head[0], old_head[1], SNAKE_BODY, snake, old_head[2])

        if player_data["growth"] > 0:
            # if we in grow -- keep the tail
            player_data["growth"] -= 1
        else:
            tail = body.pop()
            tail_x, tail_y, tail_ticket = tail[0], tail[1], tail[2]
            if tail not in body:
                self._object_remove(tail[0], tail[1], SNAKE_BODY, snake, tail_ticket)
        # boost logic
        if not is_boosting:
            is_boosting = in_water
        if is_boosting and player_data["length"] > 4:
            if random.random() < 0.3 and not in_water:
                if len(body) > 5:
                    if player_data["growth"] > 0:
                        # no remove, just decrease the growth, no pop
                        player_data["growth"] -= 1
                        player_data["length"] -= 1
                    # remove tail, spawn apple
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

    def _snake_died(self, snake):  # game_lock needed when calling
        body = self.in_game_players[snake]["body"]
        count = 1
        dropped_items_pos = set()
        for x_y in body:
            if count != 1:
                self._object_remove(x_y[0], x_y[1], SNAKE_BODY, snake, x_y[2])
            else:
                self._object_remove(x_y[0], x_y[1], SNAKE_HEAD, snake, x_y[2])
            # think of better way
            pos = (x_y[0], x_y[1])
            r = random.random()
            if pos not in dropped_items_pos:
                if r < 0.60:
                    val = self.create_better_fruit_value()
                    self._spawn_apple(x_y[0], x_y[1], val, force_spawn=True)
                    dropped_items_pos.add(pos)
                elif r > 0.90:
                    self._spawn_coin(x_y[0], x_y[1], force_spawn=True)
                    dropped_items_pos.add(pos)
                    if self.waiting_coins_count > 0:
                        if random.random() > 0.35:
                            self.waiting_coins_count -= 1

            count += 1
        self.player_to_boost.pop(snake, None)
        self.live_heads_pos.pop(snake, None)
        self.in_game_players.pop(snake, None)
        self.died_snakes.append(str(snake.tid))
        is_bot = snake in self.in_game_bots
        if is_bot:
            self.in_game_bots.remove(snake)
        with self.users_lock:
            self.tid_to_obj.pop(str(snake.tid), None)
            self.tid_to_usernames.pop(str(snake.tid), None)
            if str(snake.tid) in self.player_to_color:
                del self.player_to_color[str(snake.tid)]
                self.changed = True
            if is_bot:
                self.player_to_coin.pop(snake, None)
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
                # head move
                dx, dy = self.directions_map[data["dir"]]
                new_head = (head[0] + dx, head[1] + dy)
                # check if he will grow
                apple_val = self._is_snake_ate_check(new_head)
                is_growing = (apple_val > 0) or (data.get("growth", 0) > 0)
                # tail move or stay
                tail_to_free = tuple(data["body"][-1]) if not is_growing else None
            else:
                # head stay
                new_head = (head[0], head[1])
                tail_to_free = None
            # add head position, and tail movement by snake
            next_positions[snake] = {"new_head": new_head, "tail_to_free": tail_to_free}
        for snake in moving_snakes:
            # if made collision we add him
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
                            # will meet tail that not move
                            if (px, py) != next_positions.get(owner, {}).get("tail_to_free"):
                                collisions.add(snake)
        return collisions

    def update_bots(self, tick_id):
        turn_options = {"U": ["L", "R"], "D": ["L", "R"], "L": ["U", "D"], "R": ["U", "D"]}
        with self.game_lock:
            for i, bot in enumerate(self.in_game_bots):
                if bot not in self.in_game_players:
                    continue
                # spread bot update to different ticks
                if (tick_id + i) % 2 != 0:
                    continue

                bot_data = self.in_game_players[bot]
                head_x, head_y = bot_data["body"][0][0], bot_data["body"][0][1]
                current_dir = bot_data["dir"]

                forward = current_dir
                left, right = turn_options[current_dir]
                options = [forward, left, right]
                safe_options = []

                # which dir safe
                for d in options:
                    dx, dy = self.directions_map[d]
                    nx, ny = head_x + dx, head_y + dy
                    if (0 <= nx < BOARD_WIDTH and 0 <= ny < BOARD_HEIGHT) and \
                            self.GRID.is_exact_point_free_from_snakes(nx, ny) and \
                            (nx, ny) not in self.GRID.wall:
                        safe_options.append(d)

                if not safe_options:
                    continue  # die

                if forward not in safe_options:
                    bot_data["dir"] = random.choice(safe_options)
                    continue

                # forward look
                fdx, fdy = self.directions_map[forward]
                nnx, nny = head_x + fdx * 2, head_y + fdy * 2
                forward_looks_dangerous = False
                if not (0 <= nnx < BOARD_WIDTH and 0 <= nny < BOARD_HEIGHT) or \
                        not self.GRID.is_exact_point_free_from_snakes(nnx, nny) or \
                        (nnx, nny) in self.GRID.wall:
                    forward_looks_dangerous = True
                # random option to avoid danger
                if forward_looks_dangerous and len(safe_options) > 1:
                    if random.random() < 0.70:
                        turn_choices = [d for d in safe_options if d != forward]
                        if turn_choices:
                            bot_data["dir"] = random.choice(turn_choices)
                            continue
                # food hunt
                VISION_RADIUS = 5
                apple_xy = self._get_closest_apple(head_x, head_y)
                if apple_xy:
                    dist_to_apple = abs(head_x - apple_xy[0]) + abs(head_y - apple_xy[1])
                    if dist_to_apple <= VISION_RADIUS:
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

                # random travel
                if random.random() < 0.25:
                    turn_choices = [d for d in safe_options if d != forward]
                    if turn_choices:
                        bot_data["dir"] = random.choice(turn_choices)

    def pop_player_coins(self, cli_obj):
        """
        השרת קורא לפעולה הזו כששחקן מת.
        היא שולפת את כמות המטבעות שהשחקן אסף, ומוחקת אותו מהרישום הזמני.
        """
        with self.users_lock:
            return self.player_to_coin.pop(cli_obj, 0)

    def get_world_delta(self):
        with self.game_lock:
            remove_set = set(self.to_remove)
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
        if x < 0.7:
            return 1
        return 2

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
