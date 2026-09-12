"""
strategy.py — Task generation and prioritization.

Rewritten against the official tile schema (kind-discriminated: "PLANT",
"WEED", "COOP", "PASTURE", or empty). HARVEST priority is driven directly
by max_lifespan_step (decay) for one-time crops -- the single biggest gap
in every prior version of this project.

Known gaps, intentionally not solved here:
- Ongoing-crop (tomato/strawberry) decay isn't modeled: their
  max_lifespan_step is always -1 (the engine tracks their decay trigger
  by cumulative production count, not a step number), and that count
  isn't derivable from a single observation.
- Crop selection for empty tiles is a placeholder (always WHEAT).
- Only the main farmer is assigned a task; hands (once hiring is
  implemented) aren't scheduled yet.
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


BASE_URGENCY: dict[str, float] = {
    "FEED_CRITICAL": 100.0,
    "WATER_CRITICAL": 95.0,
    "HARVEST_DECAYING": 90.0,
    "PLACE": 80.0,
    "FEED_ROUTINE": 60.0,
    "WATER_ROUTINE": 55.0,
    "HARVEST_FRESH": 50.0,
    "CARE": 45.0,
    "DIG": 40.0,
    "BUILD": 35.0,
    "PLANT": 30.0,
    "FERTILIZE": 20.0,
    "COLLECT_FERTILIZER": 10.0,
}


def harvest_urgency(tile: TileState, current_step: int) -> float:
    """Decay-aware HARVEST urgency for a PLANT tile. Reads
    max_lifespan_step directly rather than inferring decay."""
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

        if tile.kind == "WEED":
            tasks.append(Task("DIG", tile, BASE_URGENCY["DIG"]))
            continue

        if tile.kind == "PLANT":
            u = harvest_urgency(tile, farm.step)
            if u > 0:
                tasks.append(Task("HARVEST", tile, u))
            if not tile.watered_today:
                grace_left = MAX_CONSECUTIVE_UNWATERED - tile.consecutive_unwatered
                key = "WATER_CRITICAL" if grace_left <= 1 else "WATER_ROUTINE"
                tasks.append(Task("WATER", tile, BASE_URGENCY[key]))
            if not tile.is_fertilized(farm.day):
                tasks.append(Task("FERTILIZE", tile, BASE_URGENCY["FERTILIZE"]))
            continue

        if tile.kind in ("COOP", "PASTURE"):
            if tile.animal is None:
                tasks.append(Task("PLACE", tile, BASE_URGENCY["PLACE"]))
            else:
                if tile.yield_units > 0:
                    tasks.append(Task("HARVEST", tile, BASE_URGENCY["HARVEST_FRESH"]))
                if not tile.fed_today:
                    grace_left = MAX_CONSECUTIVE_UNFED - tile.consecutive_unfed
                    key = "FEED_CRITICAL" if grace_left <= 1 else "FEED_ROUTINE"
                    tasks.append(Task("FEED", tile, BASE_URGENCY[key]))
                if not tile.cared_today:
                    tasks.append(Task("CARE", tile, BASE_URGENCY["CARE"]))
                if tile.fertilizer_available:
                    tasks.append(Task("COLLECT_FERTILIZER", tile, BASE_URGENCY["COLLECT_FERTILIZER"]))
            continue

        # tile.kind is None -- empty, unlocked, plantable
        tasks.append(Task("PLANT", tile, BASE_URGENCY["PLANT"]))

    tasks.sort(key=lambda t: t.urgency, reverse=True)
    return tasks


def shop_aware_sell_plan(farm: FarmState, max_orders: int = 8) -> list[tuple[str, int]]:
    """
    Sell targeting informed by the real per-shop demand table instead of a
    shop-count proxy. Prioritizes selling products with the lowest expected
    town/shop demand relative to shed quantity first.
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
