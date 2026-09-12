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

from mechanics import CROPS
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


def _farmer_op(farm: FarmState, market_orders: list[Any]) -> list[Any]:
    """Decide the main farmer's single op this turn. May append a market
    order it depends on (buying a seed before it can plant)."""
    tasks = generate_tasks(farm)
    if not tasks:
        return ["PASS"]

    task = tasks[0]  # highest urgency

    if task.kind == "PLANT" and farm.seeds.get(DEFAULT_PLANT_CROP, 0) <= 0:
        cost = CROPS[DEFAULT_PLANT_CROP].seed_cost
        if farm.money >= cost:
            market_orders.append(["BUY_SEED", DEFAULT_PLANT_CROP, 1])
        # keep walking toward the tile in the meantime -- no reason to
        # idle while the seed purchase is in flight

    direction = _direction_toward(farm.farmer.x, farm.farmer.y, task.tile.x, task.tile.y)
    if direction is not None:
        return [direction]

    if task.kind == "PLANT":
        if farm.seeds.get(DEFAULT_PLANT_CROP, 0) <= 0:
            return ["PASS"]  # on the tile, but the seed hasn't landed yet
        return ["PLANT", DEFAULT_PLANT_CROP]

    return [task.kind]


def agent(obs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    try:
        farm = parse_observation(obs, config)
    except Exception:
        logger.exception("parse_observation failed; passing this turn as a safe fallback")
        return {"farmer": ["PASS"], "hands": [], "market": []}

    market_orders: list[Any] = []
    farmer_op = _farmer_op(farm, market_orders)

    for item, qty in shop_aware_sell_plan(farm):
        market_orders.append(["SELL", item, qty])

    # Hands aren't hired in this pass, so there's nothing to control yet --
    # HIRE and per-hand task assignment are the next real piece of work.
    hand_ops: list[Any] = []

    return {"farmer": farmer_op, "hands": hand_ops, "market": market_orders}
