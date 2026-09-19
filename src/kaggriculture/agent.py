"""
agent.py — Kaggriculture submission entrypoint.

Rewritten against the official AGENTS.md / README.md shipped inside the
installed kaggle_environments package. Both the observation shape and the
action format below are direct matches to that documentation, not guesses:

    return {
        "farmer": [op, ...args],
        "hands":  [[op, ...args], ...],   # one per hired hand, in order
        "market": [[op, ...args], ...],
    }

This is the fix for the earlier version, which returned a bare list
(["WEST"]) — silently wrong, since the engine expects this dict shape.
That's almost certainly why reward stayed pinned at exactly $3000 even
once the observation parsing itself was corrected.
"""

from __future__ import annotations
import logging
import math
from typing import Any

from mechanics import CROPS, MAX_MARKET_ORDERS_PER_TURN, QUADRANT_COSTS, QUADRANT_NAMES, TILES_PER_UNIT, hire_cost
from state import FarmState, TileState, UnitState
from strategy import Task, best_plantable_crop, critical_backlog_count, generate_tasks, market_aware_sell_plan


def parse_observation(obs: dict[str, Any], config: dict[str, Any]) -> FarmState:
    player_idx = obs["player"]
    my_farm = obs["farms"][player_idx]
    private = obs["private"]
    market = obs["market"]
    town = obs["town"]

    tiles: list[TileState] = [
        TileState.from_raw(x, y, cell)
        for y, row in enumerate(my_farm["tiles"])
        for x, cell in enumerate(row)
    ]

    # private["inventories"][0] is the main farmer; [1:] are hands, in the
    # same order as farm["hands"].
    raw_inventories = private.get("inventories", [])

    fx, fy = my_farm["farmer"]
    farmer = UnitState(
        unit_id="farmer",
        x=fx,
        y=fy,
        carrying=raw_inventories[0] if raw_inventories else {},
    )

    hands: list[UnitState] = []
    for i, (hx, hy) in enumerate(my_farm.get("hands", [])):
        carrying = raw_inventories[i + 1] if i + 1 < len(raw_inventories) else {}
        hands.append(UnitState(unit_id=f"hand_{i}", x=hx, y=hy, carrying=carrying))

    return FarmState(
        step=obs.get("step", 0),
        day=obs.get("day", 0),
        hour=obs.get("hour", 0),
        money=my_farm.get("money", 0.0),
        shed=private.get("shed", {}),
        seeds=private.get("seeds", {}),
        market_prices=market.get("prices", {}),
        market_inventory=market.get("inventory", {}),
        unlocked_shops=town.get("unlocked_shops", []),
        unlocked_quadrants=my_farm.get("unlocked_quadrants", []),
        hires_today=my_farm.get("hires_today", 0),
        tiles=tiles,
        farmer=farmer,
        hands=hands,
    )


def _direction_toward(from_x: int, from_y: int, to_x: int, to_y: int) -> str | None:
    """Greedy straight-line stepping -- locked tiles are confirmed
    passable, so no pathfinding/obstacle-avoidance is needed."""
    dx = to_x - from_x
    dy = to_y - from_y
    if dx == 0 and dy == 0:
        return None
    if abs(dx) >= abs(dy):
        return "EAST" if dx > 0 else "WEST"
    return "SOUTH" if dy > 0 else "NORTH"


def _distance(ax: int, ay: int, bx: int, by: int) -> int:
    """Manhattan distance -- matches 4-directional movement exactly."""
    return abs(ax - bx) + abs(ay - by)


# Keep this much cash in reserve on top of a hire's own cost, so a HIRE
# order doesn't get queued the same turn that empties the bank for a seed
# purchase or land buy.
HIRE_MONEY_BUFFER = 50

# Hands disappear at the end of every day and must be re-hired from
# scratch (confirmed) -- and cost is fib(hires_today), resetting daily,
# so it escalates fast WITHIN a day: 1, 1, 2, 3, 5, 8, 13, 21, ... A
# "backlog exceeds units" trigger alone never stops firing early on --
# 25 empty tiles outnumbers even a dozen units -- so an early real run
# hired every single turn and the escalating fibonacci cost crashed the
# bank from 3000 to 40 in one day.
#
# Originally capped at a flat MAX_HIRES_PER_DAY = 3, confirmed working
# and profitable in a real run (3934 -> 5855). But that flat cap was
# tuned only for the original 25-tile NW quadrant -- once land-buying was
# added, a real run expanded to 75 tiles while labor stayed capped at 4
# units, and the original quadrant decayed to weeds from neglect (5855 ->
# 3171). Fixed here by scaling the cap with unlocked land instead of a
# flat number, using the same TILES_PER_UNIT ratio (mechanics.py) that
# produced the one confirmed-good data point. Still gated by
# HIRE_MONEY_BUFFER below, so this raises the ceiling without forcing
# spending the game can't afford. Not yet re-run against a real episode.
def _max_hires_for_day(farm: FarmState) -> int:
    unlocked_tiles = 25 * len(farm.unlocked_quadrants)
    target_units = max(1, math.ceil(unlocked_tiles / TILES_PER_UNIT))
    return max(1, target_units - 1)  # -1: the farmer isn't hired, already free


# Land-buying: unlike hiring, each quadrant is a one-time purchase (no
# fibonacci-style escalation risk -- QUADRANT_COSTS is fixed, and
# unlocked_quadrants only grows), so the failure mode here is different:
# buying too early wastes money that could hire/seed instead, buying too
# late leaves units idle with nowhere left to plant. Buy once unlocked,
# empty (plantable) tiles run low relative to how much labor there is.
LAND_BUY_MIN_EMPTY_TILES = 3
LAND_BUY_MONEY_BUFFER = 500  # bigger buffer than hiring's -- land costs up to $4k

# Confirmed root cause of the over-expansion collapse: land was bought
# while the existing quadrant still had real maintenance debt, and the
# expansion-trap fix (PLANT_ABUNDANT) then pulled units toward the new
# land instead of clearing that debt, so the original quadrant decayed
# to weeds. Gate land-buying on maintenance health first: don't spend on
# more land while there's a genuine critical backlog (watering/feeding
# emergencies, decaying harvests) on what's already owned.
LAND_BUY_MAX_CRITICAL_BACKLOG = 0


def _maybe_buy_land(farm: FarmState, tasks: list[Task]) -> list[Any] | None:
    if len(farm.unlocked_quadrants) >= len(QUADRANT_NAMES):
        return None  # fully unlocked already

    if critical_backlog_count(tasks) > LAND_BUY_MAX_CRITICAL_BACKLOG:
        return None  # existing land isn't well cared for yet -- don't expand

    empty_tiles = sum(1 for t in farm.tiles if not t.locked and t.kind is None)
    if empty_tiles > LAND_BUY_MIN_EMPTY_TILES:
        return None  # still room to plant -- don't spend on land yet

    # BUY_LAND takes no arguments (confirmed) -- the engine decides which
    # quadrant unlocks. Cost is fixed by how many you already own:
    # $1k/$2k/$4k for the 2nd/3rd/4th (QUADRANT_COSTS[len(unlocked)-1]).
    cost = QUADRANT_COSTS[len(farm.unlocked_quadrants) - 1]
    if farm.money >= cost + LAND_BUY_MONEY_BUFFER:
        return ["BUY_LAND"]
    return None


def _decide_ops(farm: FarmState) -> tuple[list[Any], list[list[Any]], list[Any]]:
    """
    Repeatedly takes the highest remaining urgency level and, within that
    tied group, picks whichever (task, unit) pairing is physically
    closest -- so equal-priority tasks get resolved by distance instead
    of arbitrary list order. This matters a lot in practice: with a
    single farmer and 25 equally-urgent empty tiles, list order alone
    previously sent it walking across the whole quadrant while an
    equally urgent, zero-distance tile (the one it was already standing
    on) sat ignored. Units CAN share a tile (confirmed), so two units can
    legitimately be sent to the same tile to do two different things.

    Known limitation: this is a greedy nearest-pair heuristic, not a true
    optimal assignment (Hungarian-algorithm territory) -- good enough for
    a handful of units against a few dozen tasks.
    """
    tasks = generate_tasks(farm)  # sorted by urgency, descending
    units = [farm.farmer, *farm.hands]
    ops: dict[int, list[Any]] = {}
    remaining_task_idxs = list(range(len(tasks)))
    remaining_units = list(range(len(units)))
    market_orders: list[Any] = []
    seeds_committed = 0

    # Re-picked every turn from the LIVE market (strategy.py::crop_roi), so
    # as one crop's price gets glutted from repeated selling, planting
    # naturally shifts to whichever crop is currently the best live ROI --
    # no fixed rotation, no hardcoded single crop. Held fixed for the rest
    # of this turn: every unit that plants this turn plants the same thing,
    # so the seed-commitment count below stays a single running total
    # instead of needing a per-crop dict.
    plant_crop = best_plantable_crop(farm)

    # Proactively keep seed in the pipeline whenever a PLANT task is
    # pending -- buying only once a unit physically arrives at an empty
    # tile would waste however many turns the walk took. Buy enough for
    # every PLANT task queued this turn, not just one, so a batch of
    # simultaneous plantings isn't seed-starved after the first.
    pending_plants = sum(1 for t in tasks if t.kind == "PLANT")
    if plant_crop is not None and pending_plants > 0:
        held = farm.seeds.get(plant_crop, 0)
        need = max(0, pending_plants - held)
        if need > 0:
            cost_each = CROPS[plant_crop].seed_cost
            affordable = int(farm.money // cost_each) if cost_each > 0 else need
            buy_qty = min(need, max(0, affordable))
            if buy_qty > 0:
                market_orders.append(["BUY_SEED", plant_crop, buy_qty])

    while remaining_task_idxs and remaining_units:
        top_urgency = tasks[remaining_task_idxs[0]].urgency
        tied = [ti for ti in remaining_task_idxs if tasks[ti].urgency == top_urgency]
        ti, ui = min(
            ((t, u) for t in tied for u in remaining_units),
            key=lambda pair: _distance(
                units[pair[1]].x, units[pair[1]].y, tasks[pair[0]].tile.x, tasks[pair[0]].tile.y
            ),
        )
        remaining_task_idxs.remove(ti)
        remaining_units.remove(ui)
        task, unit = tasks[ti], units[ui]

        direction = _direction_toward(unit.x, unit.y, task.tile.x, task.tile.y)
        if direction is not None:
            ops[ui] = [direction]
            continue

        if task.kind != "PLANT":
            ops[ui] = [task.kind]
            continue

        # Standing on an empty tile -- plant if there's seed left after
        # what's already been committed to other units this same turn.
        # Confirmed: if two units both PLANT the same turn with
        # insufficient seed for both, NEITHER plants.
        if plant_crop is not None and farm.seeds.get(plant_crop, 0) - seeds_committed > 0:
            ops[ui] = ["PLANT", plant_crop]
            seeds_committed += 1
        else:
            ops[ui] = ["PASS"]  # seed queued above but hasn't landed yet

    for ui in remaining_units:
        ops[ui] = ["PASS"]  # more units than tasks this turn

    # More backlog than units to cover it, and we can afford another --
    # hire one, up to the daily cap (scaled to unlocked land -- see
    # _max_hires_for_day). The new hand shows up next turn.
    if len(tasks) > len(units) and farm.hires_today < _max_hires_for_day(farm):
        cost = hire_cost(farm.hires_today)
        if farm.money >= cost + HIRE_MONEY_BUFFER:
            market_orders.append(["HIRE"])

    land_order = _maybe_buy_land(farm, tasks)
    if land_order:
        market_orders.append(land_order)

    # Sell whatever fits in whatever market-order slots are left this
    # turn (utility orders above take priority; extras past
    # MAX_MARKET_ORDERS_PER_TURN are silently dropped by the engine, so
    # sizing this dynamically means a sell never crowds out a buy/hire).
    remaining_slots = max(0, MAX_MARKET_ORDERS_PER_TURN - len(market_orders))
    for item, qty in market_aware_sell_plan(farm, max_orders=remaining_slots):
        market_orders.append(["SELL", item, qty])

    farmer_op = ops.get(0, ["PASS"])
    hand_ops = [ops.get(i, ["PASS"]) for i in range(1, len(units))]
    return farmer_op, hand_ops, market_orders


def agent(obs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    try:
        farm = parse_observation(obs, config)
    except Exception:
        logger.exception("parse_observation failed; passing this turn as a safe fallback")
        return {"farmer": ["PASS"], "hands": [], "market": []}

    farmer_op, hand_ops, market_orders = _decide_ops(farm)
    return {"farmer": farmer_op, "hands": hand_ops, "market": market_orders}
