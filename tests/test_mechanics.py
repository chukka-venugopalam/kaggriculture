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

from mechanics import (
    CROPS,
    MARKET_PARAMS,
    MARKET_STARTING_INVENTORY,
    PRICE_FLOOR,
    TILES_PER_UNIT,
    decay_urgency,
    hire_cost,
    is_decaying,
    market_price,
    per_turn_shop_demand,
)
from state import FarmState, TileState, UnitState, size_keeper_pool
from strategy import (
    BASE_URGENCY,
    best_plantable_crop,
    critical_backlog_count,
    crop_roi,
    generate_tasks,
    harvest_urgency,
    market_aware_sell_plan,
)


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


def test_plant_urgency_drops_back_once_labor_capacity_reached() -> None:
    # Regression test for the confirmed over-expansion collapse: the
    # original expansion-trap fix had no ceiling on PLANT_ABUNDANT, so it
    # kept pushing units to claim more land forever as long as empty land
    # was abundant -- even once already-planted tiles far exceeded what
    # the labor force could actually maintain. A real run bought 2 extra
    # quadrants this way while labor stayed flat, and the original
    # quadrant decayed to weeds. With 1 unit, labor_capacity is
    # TILES_PER_UNIT (6.25) -- 7 already-planted tiles is over that, so
    # PLANT must drop back to its low base priority even with 10 empty
    # tiles sitting right there (room_to_expand alone is no longer enough).
    farm = _trap_farm(n_planted=7, n_empty=10, n_units=1, critical=False)
    plant_task = next(t for t in generate_tasks(farm) if t.kind == "PLANT")
    assert plant_task.urgency == BASE_URGENCY["PLANT"]


def test_plant_urgency_abundant_when_under_labor_capacity() -> None:
    # Sanity check on the same ceiling: with plenty of labor relative to
    # what's planted (4 units, labor_capacity = 25), PLANT_ABUNDANT still
    # applies -- this is the original confirmed-good 5855.0 scenario
    # (4 units, 4 planted, 21 empty), unaffected by the new cap.
    farm = _trap_farm(n_planted=4, n_empty=21, n_units=4, critical=False)
    plant_task = next(t for t in generate_tasks(farm) if t.kind == "PLANT")
    assert plant_task.urgency == BASE_URGENCY["PLANT_ABUNDANT"]


def test_critical_backlog_count_counts_only_genuine_loss_tasks() -> None:
    tasks = generate_tasks(_trap_farm(n_planted=4, n_empty=21, n_units=4, critical=True))
    # All 4 planted tiles are one missed watering from becoming weeds.
    assert critical_backlog_count(tasks) == 4


def test_critical_backlog_count_zero_when_nothing_is_critical() -> None:
    tasks = generate_tasks(_trap_farm(n_planted=4, n_empty=21, n_units=4, critical=False))
    assert critical_backlog_count(tasks) == 0


def test_market_aware_sell_plan_sells_any_nonzero_shed_quantity() -> None:
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
    plan = market_aware_sell_plan(farm)
    assert ("WHEAT", 2) in plan
    assert all(item != "CARROT" for item, _ in plan)  # zero quantity isn't sellable


def test_market_price_at_equilibrium_equals_base_price() -> None:
    for item, params in MARKET_PARAMS.items():
        assert market_price(item, params[1]) == params[0]


def test_market_price_falls_below_base_when_glutted() -> None:
    assert market_price("MELON", 10_500) < 250


def test_market_price_rises_above_base_when_scarce() -> None:
    assert market_price("MELON", 9_500) > 250


def test_market_price_never_drops_below_floor() -> None:
    assert market_price("WOOL", 50_000) == PRICE_FLOOR


def test_crop_roi_prefers_high_value_crop_at_equal_market_state() -> None:
    # At equilibrium (base price) for every crop, MELON (base 250) must
    # rank above WHEAT (base 25) -- the whole point of live-ROI selection
    # over a hardcoded single crop.
    prices = {name: profile.base_price for name, profile in CROPS.items()}
    inv = {name: MARKET_STARTING_INVENTORY for name in CROPS}
    assert crop_roi("MELON", prices, inv) > crop_roi("WHEAT", prices, inv)


def test_best_plantable_crop_falls_back_when_top_choice_unaffordable() -> None:
    farm = FarmState(
        step=0, day=0, hour=0, money=15,  # can't afford MELON (80) or most others
        shed={}, seeds={}, market_prices={}, market_inventory={},
        unlocked_shops=[], unlocked_quadrants=["NW"], hires_today=0,
        tiles=[], farmer=UnitState(unit_id="farmer", x=4, y=4), hands=[],
    )
    choice = best_plantable_crop(farm)
    assert choice is not None
    assert CROPS[choice].seed_cost <= 15


def test_glut_batch_cap_meters_steep_curve_items_below_full_shed() -> None:
    # WOOL has a small anchor throughput (105) and a steep glut curve --
    # a big batch must NOT be sold in one order while the shed has room.
    farm = FarmState(
        step=0, day=0, hour=0, money=3000,
        shed={"WOOL": 70}, seeds={}, market_prices={},  # 70 < 80 shed-pressure threshold
        market_inventory={"WOOL": MARKET_STARTING_INVENTORY},
        unlocked_shops=[], unlocked_quadrants=["NW"], hires_today=0,
        tiles=[], farmer=UnitState(unit_id="farmer", x=4, y=4), hands=[],
    )
    plan = market_aware_sell_plan(farm)
    assert plan and plan[0][0] == "WOOL"
    assert plan[0][1] < 70


def test_market_aware_sell_plan_ignores_metering_under_shed_pressure() -> None:
    # Same setup, but the shed is nearly full (>=80 total) -- metering
    # must be dropped so the goods sell now instead of being discarded by
    # the unheld end-of-day overflow rule.
    farm = FarmState(
        step=0, day=0, hour=0, money=3000,
        shed={"WOOL": 90}, seeds={}, market_prices={},
        market_inventory={"WOOL": MARKET_STARTING_INVENTORY},
        unlocked_shops=[], unlocked_quadrants=["NW"], hires_today=0,
        tiles=[], farmer=UnitState(unit_id="farmer", x=4, y=4), hands=[],
    )
    plan = market_aware_sell_plan(farm)
    assert ("WOOL", 90) in plan
