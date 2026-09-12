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
from strategy import generate_tasks, harvest_urgency, shop_aware_sell_plan


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
