"""
agent.py — Kaggriculture submission entrypoint.

Rewritten against a REAL observation dump (sample_observation.json).
CONFIRMED by that file: obs["farms"][obs["player"]] is your farm; money
lives on the farm dict; tiles is a 10x10 grid, not a flat list; a cell is
`None` (empty), the string "LOCKED", or (unconfirmed -- no example yet)
presumably a dict; there is exactly one farmer right now, given as a bare
[x, y] pair with no id; unlocked_quadrants is a list of name strings.

STILL NOT CONFIRMED, flagged inline with `# VERIFY:`:
  1. The shape of an occupied tile (planted/growing/built) -- no example
     existed in a step-0 observation. Get one after a real PLANT/BUILD.
  2. The exact expected return format for actions. A single flat list
     (e.g. ["PLANT", "WHEAT"]) is this pass's best guess, replacing the
     earlier per-unit-id dict guess now that the observation shows no
     unit ids at all -- but this is still a guess.

The single fastest way to close out both of these: `AGENTS.md` and
`README.md` ship inside the installed kaggle_environments package itself.
Reading them directly (you have network access; this sandbox doesn't)
would very likely settle both in one pass instead of more guess-and-test
cycles. See the chat response for the exact commands to find and print
them.
"""

from __future__ import annotations
import logging
from typing import Any

from state import FarmState, TileState, UnitState, size_keeper_pool
from strategy import generate_tasks

logger = logging.getLogger("kaggriculture_agent")
logging.basicConfig(level=logging.WARNING)


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

    # VERIFY: whether "farmer" becomes a list of [x, y] pairs after a HIRE,
    # or something else entirely. Handled defensively either way -- a bare
    # [x, y] pair (current reality) is treated as one farmer; a list of
    # pairs would be treated as several.
    raw_farmer = my_farm.get("farmer", [])
    positions: list[tuple[int, int]]
    if raw_farmer and isinstance(raw_farmer[0], (int, float)):
        positions = [(int(raw_farmer[0]), int(raw_farmer[1]))]
    else:
        positions = [(int(p[0]), int(p[1])) for p in raw_farmer]

    # Best guess: private["inventories"] is a per-farmer carried-items list
    # -- its length (1) matched the farmer count (1) exactly in the sample.
    # Not yet confirmed against a turn where a farmer is actually carrying
    # something.
    raw_inventories = private.get("inventories", [])
    units: list[UnitState] = [
        UnitState(
            unit_id=f"farmer_{i}",
            x=x,
            y=y,
            carrying=raw_inventories[i] if i < len(raw_inventories) else {},
        )
        for i, (x, y) in enumerate(positions)
    ]

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
        units=units,
    )


def _direction_toward(from_x: int, from_y: int, to_x: int, to_y: int) -> str | None:
    """
    VERIFY: assumes index 0 of a position pair is x (column, increases
    EAST) and index 1 is y (row, increases SOUTH) -- a common convention,
    not yet confirmed. Locked tiles are confirmed passable, so no obstacle
    avoidance is needed -- straight-line greedy stepping is enough.
    """
    dx = to_x - from_x
    dy = to_y - from_y
    if dx == 0 and dy == 0:
        return None  # already there
    if abs(dx) >= abs(dy):
        return "EAST" if dx > 0 else "WEST"
    return "SOUTH" if dy > 0 else "NORTH"


def agent(obs: dict[str, Any], config: dict[str, Any]) -> list[Any]:
    """
    VERIFY: the return shape -- see module docstring. A single flat
    action list, matching the single farmer this game currently has.
    Selling (mechanics/strategy already support it via
    strategy.shop_aware_sell_plan) is deliberately left out of this pass:
    with only one action slot available per turn and no confirmed way to
    combine a move/tile-action with a market order in the same return
    value, guessing at that combination risks breaking both. Add it back
    once the return format is confirmed.
    """
    try:
        farm = parse_observation(obs, config)
    except Exception:
        logger.exception("parse_observation failed; passing this turn as a safe fallback")
        return ["PASS"]

    if not farm.units:
        return ["PASS"]

    tasks = generate_tasks(farm)
    if not tasks:
        return ["PASS"]

    unit = farm.units[0]  # exactly one farmer for now
    task = tasks[0]  # highest urgency

    direction = _direction_toward(unit.x, unit.y, task.tile.x, task.tile.y)
    if direction is not None:
        return [direction]

    # Already on the target tile -- perform its action.
    if task.kind == "PLANT":
        # VERIFY: PLANT's real argument shape; WHEAT is a placeholder
        # crop choice, not a real selection heuristic.
        return ["PLANT", "WHEAT"]
    return [task.kind]
