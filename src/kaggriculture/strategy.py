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
    decay_urgency,
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
    Sell whatever's in the shed. Unsold inventory earns nothing (the
    confirmed reward rule: "unsold items in inventory do not count"), so
    there's no reason to hold produce back at this scale.

    This replaces an earlier version that only sold once the shed was
    nearly full -- a reasonable-sounding "don't let it overflow"
    heuristic that was actually the reason a real test run showed money
    going steadily DOWN over 720 turns: with one or two crop tiles, the
    shed never gets anywhere near full, so that version silently never
    sold anything while still spending on seeds. Matches the pattern in
    AGENTS.md's own reference agent instead (sell unconditionally, no
    threshold). mechanics.py::per_turn_shop_demand is still there for a
    later pass that times sales around passive town demand -- not used
    to gate selling for now.
    """
    plan: list[tuple[str, int]] = [(item, qty) for item, qty in farm.shed.items() if qty > 0]
    plan.sort(key=lambda p: p[1], reverse=True)
    return plan[:max_orders]
