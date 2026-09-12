"""
mechanics.py — Verified Kaggriculture engine constants and reference data.

Every value here is confirmed against `kaggle_environments==1.32.7` source
and its bundled AGENTS.md / README.md, per this project's own verified-
mechanics report — not reconstructed from any prior agent file's comments.
Where a prior file's comments claimed a "confirmed" fact but cited a
PROJECT_STATE.md that doesn't exist anywhere in this environment, that
claim is deliberately NOT included here.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# Episode / board structure
# ---------------------------------------------------------------------------

TURNS_PER_DAY: int = 24
TOTAL_DAYS: int = 30
TOTAL_STEPS: int = TURNS_PER_DAY * TOTAL_DAYS  # 720, confirmed exact

BOARD_SIZE: int = 10  # four 5x5 quadrants
STARTING_MONEY: int = 3_000
QUADRANT_COSTS: tuple[int, ...] = (1_000, 2_000, 4_000)  # cost of the 2nd/3rd/4th quadrant; NW starts unlocked
# Confirmed via a real observation: unlocked_quadrants is a list of these
# name strings (e.g. ["NW"]), not a count.
QUADRANT_NAMES: tuple[str, ...] = ("NW", "NE", "SW", "SE")

# NOT resolved: how many quadrants a strong agent should buy. The prior
# main.py/new_agent_wip.py comments disagreed with each other (one claims
# real top players stopped at exactly 3, a different comment justifies a
# coordinate-ascent-found cap of 2). Real 9-game data shows all 9 winners
# reached a 3rd quadrant by day 9-11 -- a point in favor of 3, but not a
# direct A/B test against 2. Keep this tunable, resolve via real self-play:
MAX_QUADRANTS_CANDIDATES: tuple[int, ...] = (2, 3)

# ---------------------------------------------------------------------------
# Action vocabulary — every other string is a confirmed silent no-op
# ---------------------------------------------------------------------------


class Action(str, Enum):
    NORTH = "NORTH"
    SOUTH = "SOUTH"
    EAST = "EAST"
    WEST = "WEST"
    PASS = "PASS"
    PICKUP = "PICKUP"
    DROP = "DROP"
    PLACE = "PLACE"
    PLANT = "PLANT"
    WATER = "WATER"
    HARVEST = "HARVEST"
    FERTILIZE = "FERTILIZE"
    FEED = "FEED"
    COLLECT_FERTILIZER = "COLLECT_FERTILIZER"
    CARE = "CARE"
    BUILD_COOP = "BUILD_COOP"
    BUILD_PASTURE = "BUILD_PASTURE"
    DIG = "DIG"  # confirmed weed-removal action
    BUY_SEED = "BUY_SEED"
    BUY_PRODUCT = "BUY_PRODUCT"  # wheat / fertilizer only
    BUY_ANIMAL = "BUY_ANIMAL"
    SELL = "SELL"
    HIRE = "HIRE"
    BUY_LAND = "BUY_LAND"
    # NOTE: SELL_ANIMAL, REMOVE_WEED, and ["PICKUP", "WEED"] are confirmed
    # to NOT exist. Any code path that still emits them is a silent no-op.


MAX_MARKET_ORDERS_PER_TURN: int = 10  # extras silently dropped

# ---------------------------------------------------------------------------
# Crop yield / decay — the single most important newly-confirmed mechanic.
# No prior agent version modeled this correctly; the shipped fix (bumping
# HARVEST's tier ahead of WATER) never used max_lifespan_step directly.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CropProfile:
    seed_cost: int
    base_price: int
    first_yield_day: int
    max_yield_day: int  # confirmed exact for all 5 crops, incl. ongoing ones
    max_yield: int  # fertilized max, per confirmed table
    max_yield_unfertilized: int | None = None
    ongoing_interval_days: int | None = None  # tomato=1, strawberry=2
    ongoing_productions: int | None = None  # both ongoing crops: 4


# Confirmed against README.md's Object Types table exactly.
CROPS: dict[str, CropProfile] = {
    "WHEAT": CropProfile(seed_cost=10, base_price=25, first_yield_day=2, max_yield_day=4, max_yield=6, max_yield_unfertilized=4),
    "CARROT": CropProfile(seed_cost=20, base_price=35, first_yield_day=2, max_yield_day=3, max_yield=4, max_yield_unfertilized=3),
    "MELON": CropProfile(seed_cost=80, base_price=250, first_yield_day=10, max_yield_day=10, max_yield=6),
    "TOMATO": CropProfile(seed_cost=50, base_price=60, first_yield_day=8, max_yield_day=11, max_yield=4, ongoing_interval_days=1, ongoing_productions=4),
    "STRAWBERRY": CropProfile(seed_cost=100, base_price=120, first_yield_day=10, max_yield_day=16, max_yield=4, ongoing_interval_days=2, ongoing_productions=4),
}


def is_decaying(max_lifespan_step: int, current_step: int) -> bool:
    """True once a tile has passed max_lifespan_step. -1 means "not
    applicable" (an ongoing crop, whose decay trigger isn't step-based) —
    treated as never-decaying here since that path isn't modeled yet."""
    if max_lifespan_step is None or max_lifespan_step < 0:
        return False
    return current_step > max_lifespan_step


def decay_urgency(max_lifespan_step: int, current_step: int) -> float:
    """Higher = more urgent to harvest NOW. Once decaying, yield_units drops
    by 1 every other turn until the tile becomes a weed — so every 2 turns
    of delay past max_lifespan_step is a full unit of yield, permanently
    lost. Ongoing crops (max_lifespan_step == -1) aren't modeled here yet —
    their decay trigger is a cumulative-production count, not a step
    number, and isn't derivable from a single observation."""
    if max_lifespan_step is None or max_lifespan_step < 0:
        return 0.0
    turns_past_decay = current_step - max_lifespan_step
    if turns_past_decay <= 0:
        return 0.0
    return turns_past_decay / 2.0


# ---------------------------------------------------------------------------
# Watering / feeding — miss 2 consecutive end-of-day refreshes = unrecoverable
# ---------------------------------------------------------------------------

MAX_CONSECUTIVE_UNWATERED: int = 2  # on the 2nd miss, tile becomes a weed
MAX_CONSECUTIVE_UNFED: int = 2  # on the 2nd miss, animal escapes
FRESH_PLANT_STARTING_UNWATERED: int = 1  # no grace period
FRESH_ANIMAL_STARTING_UNFED: int = 0  # one free day

# ---------------------------------------------------------------------------
# Shed
# ---------------------------------------------------------------------------

SHED_CAPACITY: int = 100  # flat cap; seeds live in a separate, uncapped slot
# Overflow at end-of-day drop is discarded, not held anywhere.

# ---------------------------------------------------------------------------
# Hiring
# ---------------------------------------------------------------------------


def hire_cost(hires_today: int) -> int:
    """Fibonacci cost, resets each day: 1, 1, 2, 3, 5, 8, 13, 21, ..."""
    a, b = 1, 1
    for _ in range(hires_today):
        a, b = b, a + b
    return a


# ---------------------------------------------------------------------------
# Town / shops — real per-shop demand table. Every prior agent used only a
# shop-count proxy; this table lets selling logic anticipate actual drains.
# ---------------------------------------------------------------------------

SHOPS: dict[str, tuple[str, ...]] = {
    "BAKERY": ("EGG", "WHEAT"),
    "PIZZA_SHOP": ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT": ("EGG", "WHEAT", "STRAWBERRY"),
    "YARN_STORE": ("WOOL",),  # single-product: 2x consumption
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"),
    "PET_CAFE": ("CARROT",),  # single-product: 2x consumption
    "SMOOTHIE_SHOP": ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}
SINGLE_PRODUCT_SHOPS: frozenset[str] = frozenset({"YARN_STORE", "PET_CAFE"})

TOWN_SHOP_SELL_INTERVAL: int = 4  # turns; each unlocked shop instance drains 1 of every listed product
TOWN_CENTER_SELL_INTERVAL: int = 24  # turns; drains 1 of every non-fertilizer product, flat rate
SHOP_UNLOCK_INTERVAL_DAYS: int = 3  # a new shop is drawn (with replacement) every 3 days
MAX_SHOP_INSTANCES: int = 8


def per_turn_shop_demand(unlocked_shops: list[str]) -> dict[str, float]:
    """Expected per-turn drain for each product from town/shop mechanics,
    given the current list of unlocked shop instances (duplicates allowed)."""
    demand: dict[str, float] = {}
    for shop in unlocked_shops:
        products = SHOPS.get(shop, ())
        weight = 2.0 if shop in SINGLE_PRODUCT_SHOPS else 1.0
        for product in products:
            demand[product] = demand.get(product, 0.0) + weight / TOWN_SHOP_SELL_INTERVAL
    return demand


# ---------------------------------------------------------------------------
# Market pricing — shape differs per resource. Exact amp/curve constants
# weren't captured in the source report, so this is directional only:
# melon/wool ("sq"): crash hard on gluts, sell early and steadily.
# wheat ("log"): forgiving on gluts, safe to sell in bulk.
# carrot/tomato/egg ("hinge"): stays near base until a scarcity knee, then
#   rises fast — avoid dumping inventory that resets this knee.
# ---------------------------------------------------------------------------

MARKET_STARTING_INVENTORY: int = 10_000  # I0, every product
