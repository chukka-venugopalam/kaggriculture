"""
strategy.py — Task generation and prioritization.

The one thing every prior agent version got wrong or left unfinished:
HARVEST priority needs to be driven directly by max_lifespan_step (decay),
not a fixed tier number reasoned about in the abstract. This module
computes a continuous urgency score per task instead of a fixed tier, so
decay pressure and routine upkeep can be weighed against each other rather
than lexicographically ordered.

Known gap, intentionally not solved here: crop selection for empty,
plantable tiles is a placeholder (always WHEAT — see generate_tasks). A
real heuristic (season timing, market price, quadrant mix) is the next
piece of strategy to build, not included in this pass.
"""

from __future__ import annotations
from dataclasses import dataclass

from mechanics import (
    MAX_CONSECUTIVE_UNFED,
    MAX_CONSECUTIVE_UNWATERED,
    SHED_CAPACITY,
    decay_urgency,
    per_turn_shop_demand,
)
from state import FarmState, TileState


@dataclass
class Task:
    kind: str
    tile: TileState
    urgency: float  # higher = more urgent; used to sort, not a fixed tier


# Base urgency per task kind, before decay/backlog adjustments. Tunable —
# starting points informed by this project's process history (CARE and
# weed-DIG were previously under-prioritized and had to be bumped after
# observed failures), not re-derived from scratch here.
BASE_URGENCY: dict[str, float] = {
    "FEED_CRITICAL": 100.0,  # one more miss loses the animal
    "WATER_CRITICAL": 95.0,  # one more miss turns the tile into a weed
    "HARVEST_DECAYING": 90.0,  # scales up further the longer it's ignored
    "PLACE": 80.0,
    "FEED_ROUTINE": 60.0,
    "WATER_ROUTINE": 55.0,
    "HARVEST_FRESH": 50.0,  # ripe but not yet decaying — still worth prioritizing over routine upkeep
    "CARE": 45.0,
    "DIG": 40.0,  # weed removal — DIG is confirmed real; ["PICKUP","WEED"] is not
    "BUILD": 35.0,
    "PLANT": 30.0,
    "FERTILIZE": 20.0,
    "COLLECT_FERTILIZER": 10.0,
}


def harvest_urgency(tile: TileState, current_step: int) -> float:
    """
    Decay-aware HARVEST urgency. Every prior fix (tier 1 -> 5 -> 4) reasoned
    about this qualitatively ("land isn't earning"); this computes it
    directly from the confirmed mechanic: once max_lifespan_step passes,
    yield_units drops by 1 every other turn until the tile becomes a weed.
    """
    urgency = decay_urgency(tile.max_lifespan_step, current_step)
    if urgency > 0:
        return BASE_URGENCY["HARVEST_DECAYING"] + min(urgency, 10.0) * max(tile.yield_units, 1)
    if tile.yield_units > 0:
        return BASE_URGENCY["HARVEST_FRESH"]
    return 0.0


def generate_tasks(farm: FarmState) -> list[Task]:
    tasks: list[Task] = []

    for tile in farm.tiles:
        if tile.locked:
            continue  # every tile action no-ops on an unbought quadrant

        if tile.is_weed:
            tasks.append(Task("DIG", tile, BASE_URGENCY["DIG"]))
            continue

        if tile.yield_units > 0 or tile.max_lifespan_step is not None:
            u = harvest_urgency(tile, farm.step)
            if u > 0:
                tasks.append(Task("HARVEST", tile, u))

        if tile.crop is not None:
            grace_left = MAX_CONSECUTIVE_UNWATERED - tile.consecutive_unwatered
            key = "WATER_CRITICAL" if grace_left <= 1 else "WATER_ROUTINE"
            tasks.append(Task("WATER", tile, BASE_URGENCY[key]))
            if not tile.fertilized:
                tasks.append(Task("FERTILIZE", tile, BASE_URGENCY["FERTILIZE"]))

        if tile.animal is not None:
            grace_left = MAX_CONSECUTIVE_UNFED - tile.consecutive_unfed
            key = "FEED_CRITICAL" if grace_left <= 1 else "FEED_ROUTINE"
            tasks.append(Task("FEED", tile, BASE_URGENCY[key]))
            tasks.append(Task("CARE", tile, BASE_URGENCY["CARE"]))

        if tile.structure is not None and tile.animal is None:
            tasks.append(Task("PLACE", tile, BASE_URGENCY["PLACE"]))

        if (
            tile.crop is None
            and tile.structure is None
            and tile.animal is None
            and tile.yield_units == 0
        ):
            # Empty, plantable tile. Crop choice is a placeholder (always
            # WHEAT) — see module docstring.
            tasks.append(Task("PLANT", tile, BASE_URGENCY["PLANT"]))

    tasks.sort(key=lambda t: t.urgency, reverse=True)
    return tasks


def shop_aware_sell_plan(farm: FarmState, max_orders: int = 8) -> list[tuple[str, int]]:
    """
    Sell targeting informed by the real per-shop demand table instead of a
    shop-count proxy. Prioritizes selling products with the lowest expected
    town/shop demand relative to shed quantity first — those are least
    likely to get picked up by passive town drains, and most likely to
    approach SHED_CAPACITY and be destroyed unsold at end-of-day.
    """
    demand = per_turn_shop_demand(farm.unlocked_shops)
    plan: list[tuple[str, int]] = []
    for item, qty in farm.shed.items():
        if qty <= 0:
            continue
        expected_drain = demand.get(item, 0.0)
        pressure = qty / SHED_CAPACITY - expected_drain
        if pressure > 0.3:
            plan.append((item, qty))
    plan.sort(key=lambda p: p[1], reverse=True)
    return plan[:max_orders]
