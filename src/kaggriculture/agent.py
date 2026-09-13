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
from typing import Any

from mechanics import CROPS, hire_cost
from state import FarmState, TileState, UnitState
from strategy import generate_tasks, shop_aware_sell_plan

logger = logging.getLogger("kaggriculture_agent")
logging.basicConfig(level=logging.WARNING)

# Placeholder crop-selection heuristic -- always WHEAT. CROPS in
# mechanics.py has profiles for CARROT/TOMATO/STRAWBERRY/MELON too; a real
# selection heuristic (season timing, market price, land-use mix) is the
# next piece of strategy to build, not this pass.
DEFAULT_PLANT_CROP = "WHEAT"


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


# Keep this much cash in reserve on top of a hire's own cost, so a HIRE
# order doesn't get queued the same turn that empties the bank for a seed
# purchase or land buy.
HIRE_MONEY_BUFFER = 50


def _decide_ops(farm: FarmState) -> tuple[list[Any], list[list[Any]], list[Any]]:
    """
    Greedily assigns the highest-urgency remaining task to each unit in
    turn (farmer first, then hands in the order they appear), moving
    toward the task's tile if not already there. Units CAN share a tile
    (confirmed), so two units can legitimately be sent to the same tile
    to do two different things there in the same turn.

    Known limitation: assignment is by task-priority order only, not by
    which unit is actually closest -- a hand can end up walking further
    than necessary while a nearer task goes to someone else. Good enough
    for a first pass; real closest-unit assignment is a natural next
    improvement once this is confirmed working.
    """
    tasks = generate_tasks(farm)
    units = [farm.farmer, *farm.hands]
    ops: list[list[Any]] = []
    claimed: set[int] = set()
    market_orders: list[Any] = []
    wheat_seeds_committed = 0
    seed_buy_queued = False

    for unit in units:
        op: list[Any] = ["PASS"]
        for i, task in enumerate(tasks):
            if i in claimed:
                continue

            if task.kind == "PLANT":
                available = farm.seeds.get(DEFAULT_PLANT_CROP, 0) - wheat_seeds_committed
                if available <= 0:
                    # Confirmed: if two units both PLANT the same turn
                    # with insufficient seed for both, NEITHER plants.
                    # Send at most one unit at this task per seed actually
                    # in hand -- queue a purchase and let this unit walk
                    # over in the meantime, but leave the task claimed so
                    # no second unit piles onto the same shortfall.
                    claimed.add(i)
                    if not seed_buy_queued:
                        cost = CROPS[DEFAULT_PLANT_CROP].seed_cost
                        if farm.money >= cost:
                            market_orders.append(["BUY_SEED", DEFAULT_PLANT_CROP, 1])
                        seed_buy_queued = True
                    direction = _direction_toward(unit.x, unit.y, task.tile.x, task.tile.y)
                    op = [direction] if direction is not None else ["PASS"]
                    break

            claimed.add(i)
            direction = _direction_toward(unit.x, unit.y, task.tile.x, task.tile.y)
            if direction is not None:
                op = [direction]
            elif task.kind == "PLANT":
                op = ["PLANT", DEFAULT_PLANT_CROP]
                wheat_seeds_committed += 1
            else:
                op = [task.kind]
            break

        ops.append(op)

    # More backlog than hands to cover it, and we can afford another --
    # hire one. The new hand shows up next turn, not this one.
    if len(tasks) > len(units):
        cost = hire_cost(farm.hires_today)
        if farm.money >= cost + HIRE_MONEY_BUFFER:
            market_orders.append(["HIRE"])

    for item, qty in shop_aware_sell_plan(farm):
        market_orders.append(["SELL", item, qty])

    farmer_op, hand_ops = ops[0], ops[1:]
    return farmer_op, hand_ops, market_orders


def agent(obs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    try:
        farm = parse_observation(obs, config)
    except Exception:
        logger.exception("parse_observation failed; passing this turn as a safe fallback")
        return {"farmer": ["PASS"], "hands": [], "market": []}

    farmer_op, hand_ops, market_orders = _decide_ops(farm)
    return {"farmer": farmer_op, "hands": hand_ops, "market": market_orders}
