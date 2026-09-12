"""
Tests against a REAL observation (tests/fixtures/sample_observation.json,
pulled from an actual Kaggle run), not a hand-built synthetic dict --
checks real-world correctness, not just internal consistency with our own
schema guesses.
"""

from __future__ import annotations
import json
from pathlib import Path

from agent import agent, parse_observation

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


def test_agent_moves_toward_nearest_plantable_tile_on_a_fresh_farm() -> None:
    # On a completely empty farm, every unlocked tile is plantable, so the
    # farmer should move rather than PASS -- (4,4) itself is plantable, but
    # it's not the first one in row-major iteration order, so a real
    # decision (movement) is expected here, not an idle turn.
    obs = _load()
    result = agent(obs, config={})
    assert result["farmer"][0] in ("NORTH", "SOUTH", "EAST", "WEST")
