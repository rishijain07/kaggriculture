"""Kaggriculture agent v3.2 - disciplined melon waves + late wheat filler.

Melon economics (base $250, seed $80, 6 units at age 10 -> ~$1.4k/tile) are
the best in the game, but the sq glut curve hits the $1 floor after ~158
cumulative units sold (price = 250 - (n/100)^2 style). So the money is in
BOUNDED waves, never a continuous farm: plant only inside wave windows,
cap alive plants, and let the market recover between waves.

Window structure (a melon needs 10 days to mature):
  Half A: plant days 0-1   -> harvest days 10-11
          plant days 10-11 -> harvest days 20-21
  Half B: plant days 5-6   -> harvest days 15-16
          plant days 15-16 -> harvest days 25-26
Wave 3 on any tile matures past day 30 - never planted.
Sold in batches of 10 as harvested; the market self-limits at ~120 units.

Wheat filler: the farmer is idle from day 21 on, so days 18-25 plant
wheat in the leftover NW tiles (2 full 4-day cycles -> ~+1.5k). Wheat's
log curve barely moves with 100-200 units and never touches melon stock.
"""



from __future__ import annotations
import math

SEED_COST = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50, "STRAWBERRY": 100, "MELON": 80}
MAX_YIELD_DAY = {"WHEAT": 4, "CARROT": 3, "TOMATO": 11, "STRAWBERRY": 16, "MELON": 10}
ONGOING = {"TOMATO", "STRAWBERRY"}

CROP = "MELON"
LAND_COST = {"NE": 1000, "SW": 2000, "SE": 4000}
MAX_HANDS = 3
PLANT_CAP = 20
RESERVE = 100
SELL_BATCH = 10
SELL_THRESHOLD = 10
MAX_MARKET_ORDERS = 10
LAND_DEADLINE_DAY = 99
MAX_GEESE = 6
FEED_RESERVE = 25
SHED_TILES = [(4, 4), (5, 4), (4, 5), (5, 5)]

# wave windows: (start_day, end_day) per half of the farm
HALF_A_WINDOWS = [(0, 1), (10, 11)]
HALF_B_WINDOWS = [(5, 6), (15, 16)]
WAVE_TARGET = 11          # max alive melons per half


def fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def _zones(tiles, n_units):
    board = len(tiles)
    half = board // 2
    unlocked = [(x, y) for y in range(board) for x in range(board)
                if tiles[y][x] != "LOCKED"]
    if not unlocked:
        return [set() for _ in range(n_units)]
    quads = []
    for qy, qx in [(0, 0), (0, 1), (1, 0), (1, 1)]:
        cells = [c for c in unlocked if c[0] // half == qx and c[1] // half == qy]
        if cells:
            quads.append(cells)
    total = sum(len(q) for q in quads)
    n_units = max(1, n_units)
    counts = [max(1, round(len(q) * n_units / total)) for q in quads]
    while sum(counts) > n_units:
        idx = max(range(len(counts)), key=counts.__getitem__)
        if counts[idx] <= 1:
            break
        counts[idx] -= 1
    while sum(counts) < n_units:
        idx = min(range(len(counts)), key=counts.__getitem__)
        counts[idx] += 1
    zones = []
    for q, nq in zip(quads, counts):
        q_sorted = sorted(q, key=lambda c: (c[1], c[0]))
        chunk = max(1, math.ceil(len(q_sorted) / nq))
        for k in range(nq):
            zones.append(set(q_sorted[k * chunk:(k + 1) * chunk]))
    cx = cy = board / 2 - 0.5
    zones.sort(key=lambda z: min(abs(x - cx) + abs(y - cy) for x, y in z) if z else 1e9)
    return zones[:n_units]


def _in_windows(day, windows):
    return any(a <= day <= b for (a, b) in windows)


def agent(obs):
    me = obs["farms"][obs["player"]]
    private = obs["private"]
    day = obs["day"]
    money = me["money"]
    board = len(me["tiles"])
    tiles = me["tiles"]
    fx, fy = me["farmer"]

    shed = private.get("shed", {})
    seeds = private.get("seeds", {})
    unlocked = set(me["unlocked_quadrants"])

    empty = []
    plants = []
    weeds = []
    for y in range(board):
        for x in range(board):
            t = tiles[y][x]
            if t is None:
                empty.append((x, y))
            elif isinstance(t, dict):
                if t.get("kind") == "PLANT":
                    plants.append((x, y, t))
                elif t.get("kind") == "WEED":
                    weeds.append((x, y))

    # ---------- market orders ----------
    market = []

    if day < LAND_DEADLINE_DAY:
        for q in ("NE", "SW", "SE"):
            if q not in unlocked:
                filled = len(plants) + len(weeds)
                if money >= LAND_COST[q] + 700 and filled >= 0.75 * (len(plants) + len(empty) + len(weeds)):
                    market.append(["BUY_LAND"])
                break

    # seeds: only top up inside a wave window; the alive count only counts
    # MATURING melons (age < 10) so a wave being harvested frees capacity
    # for the next wave's planting on the same day.
    n_melons = len(plants)
    if _in_windows(day, HALF_A_WINDOWS + HALF_B_WINDOWS) and n_melons < 2 * WAVE_TARGET:
        have = seeds.get(CROP, 0)
        want = 2 * WAVE_TARGET - n_melons - have
        if want > 0 and money - RESERVE >= SEED_COST[CROP]:
            afford = max(0, (money - RESERVE) // SEED_COST[CROP])
            market.append(["BUY_SEED", CROP, min(want, afford)])

    # late-game wheat filler: farmer is idle from day 21 on, wheat's log
    # curve barely moves with 100-200 extra units and it never touches the
    # melon inventory. Two full 4-day cycles (plant 18 -> harvest 22,
    # plant 22 -> harvest 26); planting stops at day 25 so every cycle
    # finishes before the season ends.
    n_wheat = sum(1 for (x, y, t) in plants if t["crop"] == "WHEAT")
    if 18 <= day <= 25:
        have_w = seeds.get("WHEAT", 0)
        want_w = 12 - n_wheat - have_w
        if want_w > 0 and money - RESERVE >= SEED_COST["WHEAT"]:
            market.append(["BUY_SEED", "WHEAT", min(want_w, 6)])

    n_hands = max(0, min(MAX_HANDS, math.ceil(n_melons / 8) - 1))
    for _ in range(n_hands - len(me["hands"])):
        cost = fib(me["hires_today"])
        if money - RESERVE < cost:
            break
        market.append(["HIRE"])
        me["hires_today"] += 1

    n = shed.get(CROP, 0)
    while n >= SELL_THRESHOLD and len(market) < MAX_MARKET_ORDERS:
        market.append(["SELL", CROP, SELL_BATCH])
        n -= SELL_BATCH

    n_w = shed.get("WHEAT", 0)
    while n_w >= SELL_THRESHOLD and len(market) < MAX_MARKET_ORDERS:
        market.append(["SELL", "WHEAT", SELL_BATCH])
        n_w -= SELL_BATCH


    # ---------- farm tasks ----------
    # ranks: 0 melon water (a missed day costs one $250 unit),
    #        1 melon harvest (age 10 after watering, or 11+),
    #        2 wheat water (melons first, wheat is filler),
    #        3 wheat harvest, 4 melon plant (wave-gated), 5 wheat plant, 6 dig
    tasks = []
    for (x, y, t) in plants:
        age = day - t["planted_day"]
        crop = t["crop"]
        if not t["watered_today"]:
            tasks.append((0 if crop == CROP else 2, x, y, ["WATER"]))
        ready = t["yield_units"] > 0 and (
            crop in ONGOING or
            (age == MAX_YIELD_DAY[crop] and t["watered_today"]) or
            age > MAX_YIELD_DAY[crop])
        if ready:
            tasks.append((1 if crop == CROP else 3, x, y, ["HARVEST"]))
    planted_today = sum(1 for (x, y, t) in plants if t["planted_day"] == day)
    can_plant = (_in_windows(day, HALF_A_WINDOWS + HALF_B_WINDOWS)
                 and n_melons < 2 * WAVE_TARGET
                 and obs["hour"] < 23 and planted_today < PLANT_CAP)
    if can_plant:
        budget = min(len(empty), 2 * WAVE_TARGET - n_melons)
        cx = cy = board / 2 - 0.5
        for (x, y) in sorted(empty, key=lambda c: abs(c[0] - cx) + abs(c[1] - cy))[:budget]:
            tasks.append((4, x, y, ["PLANT", CROP]))
    if 18 <= day <= 25 and n_wheat < 12 and obs["hour"] < 23:
        wheat_budget = min(len(empty), 12 - n_wheat)
        cx = cy = board / 2 - 0.5
        for (x, y) in sorted(empty, key=lambda c: -abs(c[0] - cx) - abs(c[1] - cy))[:wheat_budget]:
            tasks.append((5, x, y, ["PLANT", "WHEAT"]))
    for (x, y) in weeds:
        tasks.append((6, x, y, ["DIG"]))


    ops = {"farmer": ["PASS"], "hands": []}
    used = set()
    units = [("farmer", me["farmer"])] + [("hand", h) for h in me["hands"]]
    zones = _zones(tiles, len(units))

    def nearest(cands):
        best = None
        for rank, x, y, op in cands:
            if (x, y) in used:
                continue
            d = abs(pos[0] - x) + abs(pos[1] - y)
            key = (rank, d)
            if best is None or key < best[0]:
                best = (key, rank, x, y, op)
        return best

    for i, (name, pos) in enumerate(units):
        zone = zones[i]
        zone_unwatered = sum(1 for (x, y, t) in plants
                             if (x, y) in zone and not t["watered_today"])
        cands = (t for t in tasks if (t[1], t[2]) in zone
                 and (t[0] != 4 or zone_unwatered <= 1))
        pick = nearest(cands)
        if pick is None:
            action = ["PASS"]
        else:
            (_, rank, x, y, op) = pick
            used.add((x, y))
            if pos[0] == x and pos[1] == y:
                action = op
            else:
                dx, dy = x - pos[0], y - pos[1]
                if abs(dx) >= abs(dy):
                    action = ["EAST" if dx > 0 else "WEST"]
                else:
                    action = ["SOUTH" if dy > 0 else "NORTH"]
        if name == "farmer":
            ops["farmer"] = action
        else:
            ops["hands"].append(action)

    return {"farmer": ops["farmer"], "hands": ops["hands"], "market": market}