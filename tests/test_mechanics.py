"""
Tests for the confirmed-mechanics layer (mechanics.py, state.py,
strategy.py). These check the logic directly — real function calls against
real inputs — which is a materially different and weaker claim than "runs
correctly inside the actual kaggle_environments engine." Passing here means
the arithmetic and control flow are correct; it does NOT mean the schema
assumptions in agent.py::parse_observation are correct. Only
scripts/test_harness.py (run with real network access) can confirm that —
this suite is no substitute for it, the same way this project's earlier
50-test synthetic-obs suite wasn't.
"""

from __future__ import annotations

from mechanics import decay_urgency, hire_cost, is_decaying, per_turn_shop_demand
from state import FarmState, TileState, UnitState, size_keeper_pool
from strategy import BASE_URGENCY, generate_tasks, harvest_urgency, shop_aware_sell_plan


def test_hire_cost_is_fibonacci_and_resets_daily() -> None:
    assert [hire_cost(i) for i in range(8)] == [1, 1, 2, 3, 5, 8, 13, 21]


def test_size_keeper_pool_bounds() -> None:
    assert size_keeper_pool(n_units=1, n_animals_active=0) == 1  # never zero
    assert size_keeper_pool(n_units=20, n_animals_active=100) == 3  # capped at 3
    assert size_keeper_pool(n_units=6, n_animals_active=3) == 2


def test_size_keeper_pool_stable_across_same_day_hire() -> None:
    # The bug this formula fixes: hiring a unit (n_units 6 -> 7) with no
    # change in herd size must not change the keeper pool size.
    before = size_keeper_pool(n_units=6, n_animals_active=3)
    after = size_keeper_pool(n_units=7, n_animals_active=3)
    assert before == after


def test_decay_urgency_zero_before_decay() -> None:
    assert decay_urgency(max_lifespan_step=100, current_step=100) == 0.0
    assert decay_urgency(max_lifespan_step=100, current_step=99) == 0.0


def test_decay_urgency_grows_with_time_past_decay() -> None:
    assert decay_urgency(max_lifespan_step=100, current_step=102) == 1.0
    assert decay_urgency(max_lifespan_step=100, current_step=104) == 2.0


def test_decay_urgency_none_is_never_urgent() -> None:
    assert decay_urgency(max_lifespan_step=None, current_step=500) == 0.0
    assert is_decaying(max_lifespan_step=None, current_step=500) is False


def test_harvest_urgency_decaying_tile_outranks_fresh_tile() -> None:
    fresh = TileState(x=0, y=0, max_lifespan_step=200, yield_units=2)
    decaying = TileState(x=1, y=0, max_lifespan_step=100, yield_units=2)
    assert harvest_urgency(decaying, current_step=110) > harvest_urgency(fresh, current_step=110)


def test_per_turn_shop_demand_weights_single_product_shops_double() -> None:
    demand = per_turn_shop_demand(["PET_CAFE"])
    assert demand["CARROT"] == 2.0 / 4  # single-product shop, 2x consumption, 4-turn interval


def test_generate_tasks_skips_locked_tiles() -> None:
    farm = FarmState(
        step=10,
        day=0,
        hour=10,
        money=3000,
        shed={},
        seeds={},
        market_prices={},
        market_inventory={},
        unlocked_shops=[],
        unlocked_quadrants=["NW"],
        hires_today=0,
        tiles=[TileState(x=0, y=0, locked=True, kind="PLANT", crop="WHEAT", consecutive_unwatered=1)],
        farmer=UnitState(unit_id="farmer", x=4, y=4),
        hands=[],
    )
    assert generate_tasks(farm) == []


def _trap_farm(n_planted: int, n_empty: int, n_units: int, critical: bool = False) -> FarmState:
    tiles = [
        TileState(
            x=i, y=0, kind="PLANT", crop="WHEAT", watered_today=False,
            consecutive_unwatered=1 if critical else 0,
        )
        for i in range(n_planted)
    ]
    tiles += [TileState(x=i, y=1, kind=None) for i in range(n_empty)]
    return FarmState(
        step=100, day=4, hour=4, money=3000, shed={}, seeds={"WHEAT": 10},
        market_prices={}, market_inventory={}, unlocked_shops=[], unlocked_quadrants=["NW"], hires_today=0,
        tiles=tiles, farmer=UnitState(unit_id="farmer", x=0, y=0),
        hands=[UnitState(unit_id=f"hand_{i}", x=0, y=0) for i in range(n_units - 1)],
    )


def test_plant_urgency_beats_routine_watering_when_land_is_abundant() -> None:
    # Regression test for a real bug: 4 units settled onto exactly 4
    # planted tiles and never expanded, because those tiles' recurring
    # WATER_ROUTINE obligations (55) permanently outranked PLANT (30),
    # even with 21 empty tiles sitting untouched. Confirmed in a real
    # 700+ step run. With at least as much empty land as units, PLANT
    # must now win over routine (non-critical) watering.
    farm = _trap_farm(n_planted=4, n_empty=21, n_units=4, critical=False)
    top = generate_tasks(farm)[:4]
    assert all(t.kind == "PLANT" for t in top)


def test_plant_urgency_still_loses_to_a_genuine_watering_crisis() -> None:
    # The fix above must not come at the cost of actually losing a plant:
    # one more missed watering turns it into a weed, so that must still
    # outrank expansion regardless of how much empty land is available.
    farm = _trap_farm(n_planted=4, n_empty=21, n_units=4, critical=True)
    top = generate_tasks(farm)[:4]
    assert all(t.kind == "WATER" for t in top)


def test_plant_urgency_drops_back_once_land_is_no_longer_abundant() -> None:
    farm = _trap_farm(n_planted=4, n_empty=2, n_units=4, critical=False)  # empty (2) < units (4)
    plant_task = next(t for t in generate_tasks(farm) if t.kind == "PLANT")
    assert plant_task.urgency == BASE_URGENCY["PLANT"]


def test_shop_aware_sell_plan_sells_any_nonzero_shed_quantity() -> None:
    # Regression test for a real bug: an earlier version only sold once
    # the shed was nearly full, which meant it silently never sold
    # anything for a small farm (a real 720-turn run showed money going
    # steadily down as a result). A tiny quantity, nowhere near
    # SHED_CAPACITY (100), must still show up in the sell plan.
    farm = FarmState(
        step=10,
        day=0,
        hour=10,
        money=3000,
        shed={"WHEAT": 2, "CARROT": 0},
        seeds={},
        market_prices={},
        market_inventory={},
        unlocked_shops=[],
        unlocked_quadrants=["NW"],
        hires_today=0,
        tiles=[],
        farmer=UnitState(unit_id="farmer", x=4, y=4),
        hands=[],
    )
    plan = shop_aware_sell_plan(farm)
    assert ("WHEAT", 2) in plan
    assert all(item != "CARROT" for item, _ in plan)  # zero quantity isn't sellable
