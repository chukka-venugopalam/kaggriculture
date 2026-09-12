"""
agent.py — Kaggriculture submission entrypoint.

CONFIRMED (verified against installed kaggle_environments==1.32.7 and its
AGENTS.md/README.md, per this project's verified-mechanics report): every
field name used in parse_observation() below under obs["private"],
obs["market"], and obs["town"], plus max_lifespan_step and the
consecutive_unwatered/consecutive_unfed tile fields.

NOT YET CONFIRMED — flagged inline with `# VERIFY:` — exactly two things:
  1. The top-level container shape for iterating tiles and units.
  2. The expected return format for actions.
Both are isolated to this file. state.py, strategy.py, and mechanics.py
don't need to change once you confirm them — run test_harness.py, inspect
the dumped sample_observation.json, and fix the two spots below.

Also not yet implemented: unit-to-tile movement/pathing. Tasks are
assigned to units directly with no travel step modeled — the next real
piece of work once the schema is confirmed, not guessed at here.
"""

from __future__ import annotations
import logging
from typing import Any

from state import FarmState, TileState, UnitState, size_keeper_pool
from strategy import generate_tasks, shop_aware_sell_plan

logger = logging.getLogger("kaggriculture_agent")
logging.basicConfig(level=logging.WARNING)  # flip to INFO/DEBUG for local runs; keep quiet in competition


def parse_observation(obs: dict[str, Any], config: dict[str, Any]) -> FarmState:
    private = obs["private"]
    market = obs["market"]
    town = obs["town"]

    # VERIFY: adjust these two lines to the real top-level obs shape once
    # you've inspected sample_observation.json from test_harness.py.
    raw_tiles = obs.get("tiles", [])
    raw_units = obs.get("units", [])

    tiles = [
        TileState(
            x=t["x"],
            y=t["y"],
            crop=t.get("crop"),
            yield_units=t.get("yield_units", 0),
            max_lifespan_step=t.get("max_lifespan_step"),
            consecutive_unwatered=t.get("consecutive_unwatered", 0),
            fertilized=t.get("fertilized", False),
            structure=t.get("structure"),
            animal=t.get("animal"),
            consecutive_unfed=t.get("consecutive_unfed", 0),
            is_weed=t.get("is_weed", False),
            quadrant=t.get("quadrant", 0),
            locked=t.get("locked", False),
        )
        for t in raw_tiles
    ]
    units = [
        UnitState(unit_id=u["id"], x=u["x"], y=u["y"], carrying=u.get("carrying", {}))
        for u in raw_units
    ]

    return FarmState(
        step=obs.get("step", 0),
        day=obs.get("day", obs.get("step", 0) // 24),  # VERIFY: obs may expose "day" directly
        money=private.get("money", 0),
        shed=private.get("shed", {}),
        seeds=private.get("seeds", {}),
        market_prices=market.get("prices", {}),
        market_inventory=market.get("inventory", {}),
        unlocked_shops=town.get("unlocked_shops", []),
        unlocked_quadrants=private.get("unlocked_quadrants", 1),
        hires_today=private.get("hires_today", 0),
        tiles=tiles,
        units=units,
    )


def agent(obs: dict[str, Any], config: dict[str, Any]) -> dict[str, list[Any]]:
    """
    VERIFY: the return shape. Assumed here — a dict mapping unit_id to an
    action list, e.g. {"unit_3": ["PICKUP", "WHEAT", 5]} — is the common
    convention for multi-unit Kaggle simulation competitions, but this
    project's source material never pinned down the exact expected format.
    Confirm against AGENTS.md/README.md or a real successful env.run()
    before trusting this in a real submission.
    """
    try:
        farm = parse_observation(obs, config)
    except Exception:
        logger.exception("parse_observation failed; returning no actions as a safe fallback")
        return {}

    n_animals_active = sum(1 for t in farm.tiles if t.animal is not None)
    n_keepers = size_keeper_pool(len(farm.units), n_animals_active)
    keepers = farm.units[:n_keepers]  # first-k, stable across same-day hires
    crop_crew = farm.units[n_keepers:]

    tasks = generate_tasks(farm)
    sell_plan = shop_aware_sell_plan(farm)

    # First-pass allocator, not a solved scheduler: no movement/pathing
    # between a unit and its assigned tile is modeled yet.
    animal_tasks = [t for t in tasks if t.kind in ("FEED", "CARE", "PLACE", "BUILD")]
    crop_tasks = [t for t in tasks if t.kind in ("HARVEST", "WATER", "FERTILIZE", "PLANT", "DIG", "COLLECT_FERTILIZER")]

    actions: dict[str, list[Any]] = {}
    for unit, task in zip(keepers, animal_tasks + crop_tasks):
        actions[unit.unit_id] = [task.kind]
    for unit, task in zip(crop_crew, crop_tasks + animal_tasks):
        actions.setdefault(unit.unit_id, [task.kind])

    if sell_plan:
        # VERIFY: who/what submits a market order. ["SELL", item, n] is the
        # confirmed action shape; attaching it under "_market" here is a
        # placeholder, not a confirmed submission convention.
        market_orders: list[Any] = []
        for item, qty in sell_plan[: len(sell_plan)]:
            market_orders.extend(["SELL", item, qty])
        if market_orders:
            actions["_market"] = market_orders

    return actions
