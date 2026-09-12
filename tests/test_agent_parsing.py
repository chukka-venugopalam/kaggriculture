"""
Tests against a REAL observation (tests/fixtures/sample_observation.json,
pulled from an actual Kaggle run), not a hand-built synthetic dict. This
is the specific gap flagged repeatedly in this project's history: passing
against synthetic data invented to match your own schema guesses checks
internal consistency, not real-world correctness. This suite checks the
latter, as far as one real (step-0, single-farmer, nothing-planted-yet)
sample allows -- it can't confirm the occupied-tile shape or the action
return format, since no example of either existed in this sample.
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
    assert len(farm.tiles) == 100  # 10x10, confirmed grid shape


def test_locked_and_unlocked_cells_split_correctly() -> None:
    farm = parse_observation(_load(), config={})
    locked = [t for t in farm.tiles if t.locked]
    unlocked = [t for t in farm.tiles if not t.locked]
    # NW quadrant only (5x5 = 25 cells) is unlocked; the other 75 are locked
    assert len(unlocked) == 25
    assert len(locked) == 75


def test_single_farmer_parsed_at_confirmed_position() -> None:
    farm = parse_observation(_load(), config={})
    assert len(farm.units) == 1
    assert (farm.units[0].x, farm.units[0].y) == (4, 4)


def test_unlocked_quadrants_is_a_name_list_not_a_count() -> None:
    farm = parse_observation(_load(), config={})
    assert farm.unlocked_quadrants == ["NW"]


def test_agent_returns_a_list_and_does_not_crash() -> None:
    # Doesn't confirm the return format is *correct* (that's still an open
    # question -- see agent.py's module docstring) -- only that this
    # first pass runs against real data without raising.
    obs = _load()
    result = agent(obs, config={})
    assert isinstance(result, list)
    assert len(result) >= 1
