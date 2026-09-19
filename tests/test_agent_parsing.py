"""
Tests against a REAL observation (tests/fixtures/sample_observation.json,
pulled from an actual Kaggle run), not a hand-built synthetic dict --
checks real-world correctness, not just internal consistency with our own
schema guesses.
"""

from __future__ import annotations
import json
from pathlib import Path

from agent import _decide_ops, _max_hires_for_day, agent, parse_observation
from mechanics import MAX_MARKET_ORDERS_PER_TURN, QUADRANT_NAMES
from state import FarmState, TileState, UnitState

FIXTURE = Path(__file__).parent / "fixtures" / "sample_observation.json"


def _load() -> dict:
    with open(FIXTURE) as f:
        return json.load(f)


def test_parses_real_observation_without_error() -> None:
    obs = _load()
    farm = parse_observation(obs, config={})
    assert farm.money == 3000.0
    assert farm.step == 0
    assert farm.day == 0
    assert farm.hour == 0


def test_parses_all_100_grid_cells() -> None:
    farm = parse_observation(_load(), config={})
    assert len(farm.tiles) == 100  # 10x10 grid


def test_locked_and_unlocked_cells_split_correctly() -> None:
    farm = parse_observation(_load(), config={})
    locked = [t for t in farm.tiles if t.locked]
    unlocked = [t for t in farm.tiles if not t.locked]
    # NW quadrant only (5x5 = 25 cells) is unlocked; the other 75 are locked
    assert len(unlocked) == 25
    assert len(locked) == 75


def test_farmer_parsed_at_confirmed_position_with_no_hands_yet() -> None:
    farm = parse_observation(_load(), config={})
    assert (farm.farmer.x, farm.farmer.y) == (4, 4)
    assert farm.hands == []  # hires_today == 0 in the sample


def test_unlocked_quadrants_is_a_name_list_not_a_count() -> None:
    farm = parse_observation(_load(), config={})
    assert farm.unlocked_quadrants == ["NW"]


def test_agent_returns_the_confirmed_dict_shape() -> None:
    obs = _load()
    result = agent(obs, config={})
    assert isinstance(result, dict)
    assert set(result.keys()) == {"farmer", "hands", "market"}
    assert isinstance(result["farmer"], list) and len(result["farmer"]) >= 1
    assert isinstance(result["hands"], list)
    assert isinstance(result["market"], list)


def test_agent_does_not_walk_away_from_an_equally_urgent_tile_under_its_feet() -> None:
    # Regression test for a real inefficiency: with many equally-urgent
    # empty tiles (a fresh farm), a lone farmer used to walk to whichever
    # tile was first in list order even when it was already standing on
    # an equally valid one. It should recognize its own tile as just as
    # good (distance 0) and act there instead of wasting the whole walk --
    # here, that means queuing the seed purchase and waiting, not moving.
    obs = _load()
    result = agent(obs, config={})
    assert result["farmer"] == ["PASS"]
    # Live-ROI crop selection (strategy.py::best_plantable_crop), not a
    # hardcoded crop: with an empty/fresh market (this fixture has no
    # market_prices set) every crop prices at its base_price, and MELON's
    # (max_yield * base_price - seed_cost) / max_yield_day beats WHEAT's
    # by about 4x -- so a farm that can afford the $80 seed (this one can,
    # $3000 starting money) buys MELON, not WHEAT.
    # Buys enough seed for every PLANT task queued this turn (all 25 empty
    # NW tiles at step 0), not just one -- so check for a MELON BUY_SEED
    # order rather than an exact quantity.
    assert any(o[:2] == ["BUY_SEED", "MELON"] for o in result["market"])


def test_agent_plants_immediately_once_seed_is_in_hand() -> None:
    obs = _load()
    obs["private"]["seeds"]["MELON"] = 1  # as if the queued purchase already landed
    result = agent(obs, config={})
    assert result["farmer"] == ["PLANT", "MELON"]


def _bare_farm(**overrides) -> FarmState:
    defaults = dict(
        step=0, day=0, hour=0, money=3000.0,
        shed={}, seeds={}, market_prices={}, market_inventory={},
        unlocked_shops=[], unlocked_quadrants=["NW"], hires_today=0,
        tiles=[], farmer=UnitState(unit_id="farmer", x=0, y=0), hands=[],
    )
    defaults.update(overrides)
    return FarmState(**defaults)


def test_decide_ops_returns_one_op_per_hand() -> None:
    farm = _bare_farm(
        seeds={"WHEAT": 5},
        tiles=[TileState(x=i, y=0) for i in range(5)],
        hands=[UnitState(unit_id="hand_0", x=1, y=0), UnitState(unit_id="hand_1", x=2, y=0)],
    )
    farmer_op, hand_ops, _ = _decide_ops(farm)
    assert len(hand_ops) == 2
    assert isinstance(farmer_op, list) and len(farmer_op) >= 1


def test_decide_ops_hires_when_backlog_exceeds_units_and_affordable() -> None:
    farm = _bare_farm(tiles=[TileState(x=i, y=0) for i in range(10)])  # 10 tasks, 1 unit
    _, _, market_orders = _decide_ops(farm)
    assert ["HIRE"] in market_orders


def test_decide_ops_stops_hiring_at_the_daily_cap() -> None:
    # Regression test for a real bug: hiring had no cap, so with a large
    # backlog (any farm early on) it fired every single turn, and cost
    # (fib(hires_today), resetting daily) escalated fast enough within
    # one day to crash a 3000-money bank down to ~40 in a single real run.
    farm = _bare_farm(
        hires_today=3,  # already at MAX_HIRES_PER_DAY
        tiles=[TileState(x=i, y=0) for i in range(20)],  # huge backlog, still shouldn't hire
    )
    _, _, market_orders = _decide_ops(farm)
    assert ["HIRE"] not in market_orders


def test_decide_ops_skips_hire_when_money_too_low() -> None:
    farm = _bare_farm(money=10.0, tiles=[TileState(x=i, y=0) for i in range(10)])
    _, _, market_orders = _decide_ops(farm)
    assert ["HIRE"] not in market_orders


def test_decide_ops_does_not_double_commit_scarce_seed() -> None:
    # Two units both already standing on an empty tile, only 1 wheat seed
    # available. Confirmed rule: if two units both PLANT the same turn
    # with insufficient seed for both, NEITHER plants -- so at most one of
    # them may actually be told to PLANT this turn.
    farm = _bare_farm(
        money=15.0,  # affords WHEAT (seed_cost 10) only, so crop selection can't drift to MELON
        seeds={"WHEAT": 1},
        tiles=[TileState(x=0, y=0), TileState(x=1, y=0)],
        farmer=UnitState(unit_id="farmer", x=0, y=0),
        hands=[UnitState(unit_id="hand_0", x=1, y=0)],
    )
    farmer_op, hand_ops, _ = _decide_ops(farm)
    plant_ops = [op for op in [farmer_op, *hand_ops] if op[0] == "PLANT"]
    assert len(plant_ops) == 1


def _mostly_planted_nw(empty_count: int) -> list[TileState]:
    """25 NW tiles, all but `empty_count` already planted with wheat."""
    planted = [
        TileState(x=x, y=y, kind="PLANT", crop="WHEAT", watered_today=True)
        for x in range(5)
        for y in range(5)
    ]
    n_planted = 25 - empty_count
    return planted[:n_planted] + [TileState(x=3, y=4), TileState(x=4, y=4)][: max(0, 25 - n_planted)]


def test_decide_ops_buys_land_once_empty_tiles_run_low() -> None:
    farm = _bare_farm(money=5000.0, unlocked_quadrants=["NW"], tiles=_mostly_planted_nw(empty_count=2))
    _, _, market_orders = _decide_ops(farm)
    assert ["BUY_LAND"] in market_orders


def test_decide_ops_skips_land_when_plenty_of_room_left() -> None:
    farm = _bare_farm(
        money=5000.0,
        unlocked_quadrants=["NW"],
        tiles=[TileState(x=x, y=y) for x in range(5) for y in range(5)],  # all 25 empty
    )
    _, _, market_orders = _decide_ops(farm)
    assert ["BUY_LAND"] not in market_orders


def test_decide_ops_skips_land_once_fully_unlocked() -> None:
    farm = _bare_farm(
        money=5000.0,
        unlocked_quadrants=list(QUADRANT_NAMES),  # all 4 already owned
        tiles=[TileState(x=0, y=0)],  # even with a lone empty tile "shortage"
    )
    _, _, market_orders = _decide_ops(farm)
    assert ["BUY_LAND"] not in market_orders


def test_decide_ops_skips_land_when_money_too_low() -> None:
    farm = _bare_farm(money=1200.0, unlocked_quadrants=["NW"], tiles=_mostly_planted_nw(empty_count=2))
    _, _, market_orders = _decide_ops(farm)
    assert ["BUY_LAND"] not in market_orders  # $1000 cost + $500 buffer > $1200


def test_max_hires_for_day_matches_the_confirmed_good_baseline_at_25_tiles() -> None:
    # The one confirmed-good real data point: 25 tiles (NW only), cap of
    # 3 hires -> 4 total units, scored 5855.0. The new scaling formula
    # must reproduce this exact number for the unchanged, single-quadrant
    # case, or it risks regressing the one thing already known to work.
    farm = _bare_farm(unlocked_quadrants=["NW"])
    assert _max_hires_for_day(farm) == 3


def test_max_hires_for_day_scales_up_with_more_land() -> None:
    # Regression test for the confirmed over-expansion collapse: a flat
    # cap of 3 stayed fixed even after land tripled to 75 tiles, so labor
    # never grew to match and the original quadrant decayed to weeds.
    # The cap must rise once there's more land to maintain.
    farm = _bare_farm(unlocked_quadrants=["NW", "NE", "SW"])  # 75 tiles
    assert _max_hires_for_day(farm) > 3


def test_decide_ops_hires_past_the_old_flat_cap_when_land_is_expanded() -> None:
    # With 3 quadrants unlocked (75 tiles) and hires_today already at the
    # old flat cap (3), hiring should still fire -- the point of scaling
    # the cap with land is exactly to keep hiring past where the old flat
    # cap would have silently stopped it.
    farm = _bare_farm(
        money=50_000.0,
        unlocked_quadrants=["NW", "NE", "SW"],
        hires_today=3,
        tiles=[TileState(x=i, y=0) for i in range(20)],  # big backlog, 1 unit
    )
    _, _, market_orders = _decide_ops(farm)
    assert ["HIRE"] in market_orders


def test_decide_ops_skips_land_when_critical_backlog_pending() -> None:
    # Regression test for the confirmed root cause of the over-expansion
    # collapse: land was bought while the existing quadrant still had
    # real maintenance debt. Same empty-tile shortage and money as
    # test_decide_ops_buys_land_once_empty_tiles_run_low, but with one
    # planted tile one missed watering from becoming a weed -- land-buying
    # must now stand down until that's cleared, even though every other
    # buy condition is met.
    tiles = _mostly_planted_nw(empty_count=2)
    tiles[0] = TileState(
        x=tiles[0].x, y=tiles[0].y, kind="PLANT", crop="WHEAT",
        watered_today=False, consecutive_unwatered=1,  # WATER_CRITICAL
    )
    farm = _bare_farm(money=5000.0, unlocked_quadrants=["NW"], tiles=tiles)
    _, _, market_orders = _decide_ops(farm)
    assert ["BUY_LAND"] not in market_orders


def test_decide_ops_never_exceeds_market_order_cap() -> None:
    farm = _bare_farm(
        money=5000.0,
        unlocked_quadrants=["NW"],
        shed={k: 50 for k in ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER")},
        tiles=_mostly_planted_nw(empty_count=2),
    )
    _, _, market_orders = _decide_ops(farm)
    assert len(market_orders) <= MAX_MARKET_ORDERS_PER_TURN
