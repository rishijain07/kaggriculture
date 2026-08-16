"""Kaggriculture agent v1 - wheat monoculture.

Strategy:
- Plant WHEAT on every unlocked tile; water the planting day and daily through
  the bonus window so yield peaks at 4 units on day 4.
- Harvest on day 4, but only AFTER that day's final watering (the bonus lands
  then); harvest any day-5+ straggler before decay eats it.
- Sell in batches of 50. Wheat absorbs gluts well (log shape, 0.20 target
  above I0) so aggressive selling costs little.
- Buy the three extra quadrants (NE 1k, SW 2k, SE 4k) when the current farm is
  ~75% full; each 5x5 quadrant adds ~$400-500/day of wheat revenue.
- Hire farm hands proportional to the workload (fib costs; ~6 tiles per unit).
- Strict per-unit zones: units only service their own sub-zone (cross-zone
  help costs more movement than it saves), ranked by urgency: survival water,
  final-bonus-day water, harvest, window water, pre-window water, plant, dig.
- Planting is capped per day and gated per zone on watering being caught up,
  so the farm grows at its watering pace instead of overextending.
"""

from __future__ import annotations
import math

SEED_COST = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50, "STRAWBERRY": 100, "MELON": 80}
MAX_YIELD_DAY = {"WHEAT": 4, "CARROT": 3, "TOMATO": 11, "STRAWBERRY": 16, "MELON": 10}
ONGOING = {"TOMATO", "STRAWBERRY"}

CROP = "WHEAT"
LAND_COST = {"NE": 1000, "SW": 2000, "SE": 4000}
MAX_HANDS = 8
TILES_PER_UNIT = 6
PLANT_CAP = 15
RESERVE = 400
SELL_BATCH = 50
SELL_THRESHOLD = 50
MAX_MARKET_ORDERS = 10
LAND_DEADLINE_DAY = 20


def fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def _zones(tiles, n_units):
    """One contiguous sub-zone per unit, quadrant-major, shed-nearest first."""
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


def agent(obs):
    me = obs["farms"][obs["player"]]
    private = obs["private"]
    day = obs["day"]
    money = me["money"]
    board = len(me["tiles"])
    tiles = me["tiles"]

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

    have = seeds.get(CROP, 0)
    if have < len(empty):
        afford = max(0, (money - RESERVE) // SEED_COST[CROP])
        if afford > 0:
            market.append(["BUY_SEED", CROP, min(len(empty) - have, afford)])

    n_hands = max(0, min(MAX_HANDS,
                     math.ceil((len(plants) + len(empty)) / TILES_PER_UNIT) - 1))
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

    # ---------- farm tasks ----------
    # ranks: 0 water survival (planted today / at-risk),
    #        1 water final bonus day (age == max_yield_day: must be watered
    #          before harvest or the last yield unit is lost),
    #        2 harvest (yield complete: watered on the final day, or past it),
    #        3 water bonus window, 4 water pre-window (spread the load),
    #        5 plant, 6 dig
    tasks = []
    window_start = (MAX_YIELD_DAY[CROP] + 1) // 2
    for (x, y, t) in plants:
        age = day - t["planted_day"]
        if not t["watered_today"]:
            if t["planted_day"] == day or t["consecutive_unwatered"] >= 1:
                tasks.append((0, x, y, ["WATER"]))
            elif CROP in ONGOING or age == MAX_YIELD_DAY[CROP]:
                tasks.append((1, x, y, ["WATER"]))
            elif CROP in ONGOING or window_start <= age < MAX_YIELD_DAY[CROP]:
                tasks.append((3, x, y, ["WATER"]))
            elif age < window_start:
                tasks.append((4, x, y, ["WATER"]))
        ready = t["yield_units"] > 0 and (
            CROP in ONGOING or
            (age == MAX_YIELD_DAY[CROP] and t["watered_today"]) or
            age > MAX_YIELD_DAY[CROP])
        if ready:
            tasks.append((2, x, y, ["HARVEST"]))
    # plant tasks always exist (per-day cap); picking is gated per zone below
    planted_today = sum(1 for (x, y, t) in plants if t["planted_day"] == day)
    if have > 0 and obs["hour"] < 23 and planted_today < PLANT_CAP:
        budget = min(len(empty), PLANT_CAP - planted_today)
        cx = cy = board / 2 - 0.5
        for (x, y) in sorted(empty, key=lambda c: abs(c[0] - cx) + abs(c[1] - cy))[:budget]:
            tasks.append((5, x, y, ["PLANT", CROP]))
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

    # strict zones: units only service their own sub-zone. Cross-zone help costs
    # more movement than it saves (walk there + back >> the action itself), so
    # idle is cheaper than stealing. Ranks encode priority: survival water,
    # final-bonus-day water, harvest, window water, pre-window water, plant,
    # dig. Planting is gated per-zone: a unit only plants when its own zone's
    # watering is caught up, so each zone expands at its own watering pace.
    for i, (name, pos) in enumerate(units):
        zone = zones[i]
        zone_unwatered = sum(1 for (x, y, t) in plants
                             if (x, y) in zone and not t["watered_today"])
        cands = (t for t in tasks if (t[1], t[2]) in zone
                 and (t[0] != 5 or zone_unwatered <= 2))
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