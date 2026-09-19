# Kaggriculture — Handoff

Repo: github.com/chukka-venugopalam/kaggriculture (push/clone workflow
established; see "Kaggle setup" below).

## SCALE CORRECTION (read this first)

Every number below this section (5855.0, 3171.0) was measured a different
way than real Kaggriculture leaderboard scoring, and is NOT comparable to
"reach 3000" or "top 10" as goals. Confirmed from cached real-run output
inside a public evaluation notebook (`kaggriculture-rank-your-agent.ipynb`,
not part of this repo but reviewed this session):

- **The competition scores head-to-head Bradley-Terry rating, not bank.**
  An agent that does *nothing* all season ("Fallow Finn") still banks
  **3,000** (unspent starting money) — so a bank-based "3000" target is
  literally the do-nothing floor. Real competent-agent banks over a full
  720-turn season run from ~7,000 (wheat-only, no hired help) into the
  **hundreds of thousands** for strong agents (one real top-meta trace
  agent banked ~190K-200K against a mid-strength opponent). The
  Bradley-Terry ratings on that ladder run roughly 1500 (field average) to
  ~2060 (the strongest reference agent in that dataset) — nobody observed
  is near 3000 on that scale either. "Reach top 10" is a real leaderboard
  claim that can only be checked by actually submitting and getting a
  rank back from Kaggle; nothing in this repo or that notebook can predict
  leaderboard placement from local numbers alone.
- **This repo's own 5855.0/3171.0 numbers are not full-season bank
  values** — they're too low by roughly two orders of magnitude next to
  the reference ladder above, which strongly suggests they came from a
  shorter/partial test run (`scripts/test_harness.py`), not a full
  720-step episode. Treat them as directional (5855 > 3171, so the
  version that scored 5855 was doing something right) but NOT as
  calibrated against real competition scoring. Confirming a real 720-step
  bank number is the first thing to do before trusting any further
  "is this better" comparison — including everything below.
- **This session's biggest, most concrete gap-close:** this repo's own
  market pricing model was marked `directional only` (see the mechanics.py
  comment this replaced) — the actual curve shape and constants weren't
  known. They are now: confirmed by cross-checking three independent
  sources that landed on the exact same constants (two unrelated top-30
  competitors' shipped agents, plus `price_curves.csv` — an *empirically
  measured* table shipped in that same public notebook's reference-agent
  dataset, giving real observed `price_at_50_sold` / `price_at_150_sold`
  etc. that match this formula's output exactly). Now in
  `mechanics.py::MARKET_PARAMS` / `market_price()` / `sell_impact()`.
- **This repo also only ever planted WHEAT** (base price 25 — the
  cheapest crop in the game; MELON is 250) and sold everything in the shed
  unconditionally every turn with zero market awareness. That's very
  likely a bigger cap on the ceiling than any of the urgency/hiring/
  land-buying tuning below. Fixed this session — see "THIS SESSION" below.
- **Animal husbandry (COW/SHEEP/GOOSE, BUILD_PASTURE/BUILD_COOP,
  BUY_ANIMAL) is still completely unimplemented.** `generate_tasks()` has
  had a `PLACE` task type wired in since early in this project, but
  nothing ever builds a PASTURE/COOP tile in the first place, so it's
  dead code in practice — not a bug that's fired yet, but also not real
  strategy. MILK (160)/WOOL (200)/EGG (50) are real market items with
  confirmed prices, but this repo has no confirmed BUY_ANIMAL cost, feed
  schedule, or yield rate to build against, and guessing those numbers
  would violate this project's own standard (mechanics.py's header: every
  constant here is confirmed against real docs, not reconstructed from
  comments). **Next person: pull AGENTS.md/README.md's animal section
  from a real `kaggle_environments` install on Kaggle** (this sandbox has
  no network access to do it) and add an `ANIMALS` table to mechanics.py
  the same way `CROPS` is built, then wire BUILD_PASTURE/BUILD_COOP +
  BUY_ANIMAL into agent.py the way PLANT/BUY_SEED already work. This is
  very likely the single largest remaining score opportunity in the repo.

## THIS SESSION (no network access — code-only, tests pass, NOT yet run
against a real episode; see "next step" at the end)

- **Live market pricing model ported in** (`mechanics.py`): `market_price(item,
  inventory)` and `sell_impact(item, inventory, qty)`, using the confirmed
  `MARKET_PARAMS` table above. Replaces the old "directional only" note.
- **Crop selection is now live-ROI-based, not hardcoded WHEAT**
  (`strategy.py::crop_roi` / `best_plantable_crop`). Each planting decision
  re-picks the crop with the best `(max_yield * live_price - seed_cost) /
  max_yield_day` using the CURRENT market price, not the static base price
  — so as one crop's price gets driven down by repeated selling, the next
  planting decision naturally rotates to whatever's still valuable, with no
  hardcoded rotation rule. `agent.py::_decide_ops` now buys/plants whatever
  `best_plantable_crop` returns, buying enough seed for every PLANT task
  queued that turn (not just one).
  - Known, deliberately-not-solved-yet risk: this is a pure $/tile-day ROI
    metric with no time-value-of-money adjustment. MELON's ROI ranks far
    above WHEAT's at a fresh market (142 vs 35 in the unit test), but MELON
    takes 10 days to first yield vs WHEAT's 2 — so an early-game farm with
    only starting money could plausibly end up cash-starved waiting on its
    first melon harvest instead of cycling fast wheat/carrot money into
    hiring and seed for more tiles. Not fixed here because fixing it
    without real run data risks guessing a liquidity constant instead of
    measuring one — flagging it as the first thing to check once real runs
    are possible again.
- **Selling is now market-aware, not "dump everything every turn"**
  (`strategy.py::market_aware_sell_plan`, replacing `shop_aware_sell_plan`):
  ranks shed contents by net value (gross revenue minus this sale's own
  price impact, via `sell_impact`), skips items already sitting at the
  price floor unless the shed is nearly full (SHED_CAPACITY=100, and
  overflow is discarded, not held, at end of day), and meters glut-prone
  items (steep above-equilibrium curve, small anchor throughput) to at
  most half their confirmed anchor-throughput per order instead of
  dumping a whole harvest into one price-crashing sale.
- **Local economics sanity check added** (`scripts/economics_sim.py`) —
  NOT a game simulator (doesn't model tiles/movement/weeds/RNG; see the
  file's own docstring for exactly what it does and doesn't claim). Only
  purpose: confirm `crop_roi`'s live-market feedback loop actually
  self-diversifies over many sequential decisions, not just in a single
  isolated unit-test call. Run: used 4 of 5 crops over 60 simulated
  planting cycles, never got stuck repeating one crop forever — the
  mechanism works as intended at that level.
- 8 new tests added (39 → 47, all passing): market price at/above/below
  equilibrium and floored correctly, crop ROI ranking, affordability
  fallback when the top-ROI crop is out of reach, glut-batch metering
  firing under normal conditions and correctly standing down under shed
  pressure. Two existing tests updated for the new expected behavior
  (crop selection picks MELON instead of hardcoded WHEAT on the real
  fixture, at its default $3000/empty-market state).
- `submission/main.py` rebuilt and verified as valid Python.
- **Next step, in order:** (1) get a real 720-step bank number for the
  current code on Kaggle to replace the false 5855.0/3171.0 comparison
  baseline; (2) get real animal mechanics from a real `kaggle_environments`
  install and implement husbandry (see above — probably the biggest lever
  left); (3) check whether the MELON liquidity risk noted above is real by
  comparing early-game money-over-time between this version and a
  wheat-first variant; (4) once there's a trustworthy local score, actually
  run `kaggriculture-rank-your-agent.ipynb`'s reference ladder against this
  agent to get a real Bradley-Terry number before drawing any "did this
  help" conclusion, since nothing in this repo can produce that number
  itself.

## Older TL;DR (pre-this-session; numbers below are on the uncorrected,
non-comparable scale described above — keep for directional context only)

- Best **confirmed real result so far: 5855.0** (hiring working, capped
  correctly, no land-buying yet). This is still the only number verified
  against a real 720-turn episode.
- The land-buying run that followed regressed to **3171.0** due to the
  over-expansion collapse (land tripled, labor stayed flat at 4, original
  quadrant decayed to weeds — full detail kept below for context).
- **THIS SESSION (no network/Kaggle access — code-only, unit-tested, NOT
  yet run against a real episode):** implemented all three candidate
  fixes from the root-cause hypothesis below, in one pass since they're
  complementary rather than competing (see "Process lessons" — normally
  fix one at a time, but these three directly target three different
  mechanisms of the same one bug, not three independent changes):
  1. **Plant expansion now capped by labor capacity**, not just empty
     land. `PLANT_ABUNDANT` used to apply forever as long as empty tiles
     >= units, with no ceiling — that's what let a run keep claiming new
     land indefinitely. Now it also requires `planted_count <
     n_units * TILES_PER_UNIT` (6.25, mechanics.py — derived from the
     confirmed 25-tile/4-unit/5855.0 data point). Once labor is already
     saturated, PLANT drops back to base priority regardless of how much
     empty land is sitting there.
  2. **Land-buying gated on maintenance health.** `_maybe_buy_land` now
     refuses to buy while `critical_backlog_count(tasks) > 0` (any
     WATER_CRITICAL/FEED_CRITICAL/HARVEST_DECAYING task pending) — this
     was the literal root cause: land got bought while the existing
     quadrant still had real upkeep debt.
  3. **Hiring cap now scales with unlocked land** instead of a flat
     `MAX_HIRES_PER_DAY = 3`. New `_max_hires_for_day(farm)` derives the
     cap from `TILES_PER_UNIT`, reproducing exactly 3 for the
     single-quadrant case (unchanged from the confirmed-good baseline)
     and rising as more land is unlocked.
  - `TILES_PER_UNIT = 6.25` (mechanics.py) is the one new shared constant
    behind (1) and (3) — same ratio, two use sites.
  - 8 new tests added (31 → 39, all passing) covering: the labor-capacity
    ceiling on PLANT_ABUNDANT in both directions, `critical_backlog_count`
    correctness, the hire cap reproducing 3 at 25 tiles and rising above
    it at 75 tiles, hiring actually firing past the old flat cap once
    land is expanded, and land-buying correctly refusing when a critical
    task is pending under otherwise-identical conditions to the existing
    "buys land" test.
  - **Next step for whoever picks this up:** per the "reconfirm the
    baseline first" note below (not done this session — no Kaggle/network
    access here), run `scripts/test_harness.py` for (a) a clean rerun of
    the no-land-buying 5855.0 baseline to confirm nothing silently
    regressed, then (b) a fresh land-buying run with these three fixes
    together to see whether the collapse is actually resolved. Everything
    here is unit-tested against synthetic scenarios only — this project's
    own history (4 separate bugs, all first surfaced by a real run, not
    reasoning) is a direct warning not to trust this without one.
- Everything about the engine (schema, action format, mechanics) is fully
  confirmed from the official docs — nothing left to reverse-engineer
  there. What's left is strategy tuning and confirming the fix above.

## What's fully confirmed, don't re-derive

- **Action format**: `{"farmer": [op, ...args], "hands": [[op,...],...], "market": [[op,...],...]}`
  — a dict, not a list. Confirmed from `AGENTS.md`/`README.md`, which
  ship *inside* the installed `kaggle_environments` package
  (`pip install kaggle-environments`, then find `AGENTS.md` under the
  package's `envs/kaggriculture/` directory).
- **Observation schema**: `obs["farms"][obs["player"]]` is your farm;
  `money` lives on the farm dict; `tiles` is a 10×10 grid (`tiles[y][x]`);
  a tile is `None` (empty), `"LOCKED"`, or a dict with `"kind"` one of
  `"PLANT"` / `"WEED"` / `"COOP"` / `"PASTURE"`, each with documented
  fields (see `src/kaggriculture/state.py::TileState.from_raw`). One
  farmer (`farm["farmer"]`, a bare `[x,y]`) plus a separate `hands` list.
- **Crop table, shed cap, hire formula, shop demand table** — all in
  `src/kaggriculture/mechanics.py`, matching the README's Object Types
  table exactly.
- **Repo/build pipeline**: `src/kaggriculture/` is the real modular
  source; `scripts/build_submission.py` flattens it into
  `submission/main.py` (Kaggle grades a single file in isolation — the
  rest of the repo isn't present at grading time). Re-run the build
  script and commit the new output after any `src/` change. Byte-verified
  identical to the modular source every time so far.

## Bug history — every one found via an actual real run, not guessed

1. **Action-format bug**: returned a bare list (`["WEST"]`) instead of
   the dict shape above. Fixed once the real spec was read. Confirmed:
   farmer moved, bought a seed, planted, all correctly.
2. **Sell-threshold bug**: `shop_aware_sell_plan` only sold once the shed
   was nearly full — silently never sold with just 1–2 crop tiles, so
   money only went down (seed purchases, no sales). Fixed to sell
   unconditionally (matches the reference agent in `AGENTS.md`). Result:
   **3934.0** — first confirmed profitable run.
3. **Runaway-hire bug**: `HIRE` fired every single turn (task backlog
   almost always exceeds a small unit count early on), and hire cost is
   `fib(hires_today)`, resetting daily — escalated fast enough within one
   day to crash the bank from 3000 to 40. Fixed with a hard
   `MAX_HIRES_PER_DAY = 3` cap. Result: **5855.0** — best confirmed
   result. Roughly 3x the net profit of the no-hiring baseline.
4. **Expansion-trap bug**: `PLANT` urgency (30) always lost to routine
   `WATER`/`HARVEST` urgency (50–55). A real run's tile map showed 4
   units permanently stuck maintaining exactly 4 planted tiles, 21 of 25
   NW tiles untouched the whole episode — once anything is planted, its
   recurring upkeep permanently outranks planting anything new. Fixed by
   making `PLANT` urgency rise to 65 (still below anything genuinely
   critical) whenever empty land ≥ unit count. Verified directly against
   the exact trap scenario, both the realistic case and a genuine-crisis
   case (confirmed critical watering still correctly wins).
5. **UNRESOLVED — over-expansion collapse**: built in the same pass as
   #4, land-buying (`BUY_LAND` once empty tiles run low and money
   allows). A real run bought NE (step 44) and SW (step 338) — expanding
   to 75 tiles total — but labor stayed capped at 4 units
   (`MAX_HIRES_PER_DAY = 3`, tuned for a 25-tile farm). By step 700, the
   *entire original NW quadrant* (all 25 tiles) had decayed into weeds.
   Final reward: 3171.0, worse than pre-land-buying. Land-buying and
   hiring aren't coordinated with each other, and fix #4's expansion
   pressure made it worse by continuing to push toward new tiles rather
   than reining in scope once land already outscaled labor.

## Root-cause hypothesis for #5 (not yet tried)

Candidate directions, none implemented yet:

- **Tie land-buying to maintenance health**: don't buy land unless the
  current backlog of CRITICAL tasks (watering/feeding emergencies) is
  near zero — i.e., only expand once what's already planted is well
  cared for, not just when empty tiles run low.
- **Scale hiring with land size**: `MAX_HIRES_PER_DAY = 3` was sized for
  25 tiles; make it dynamic (e.g., proportional to unlocked tile count)
  so labor actually grows with land instead of staying flat.
- **Cap total active-plant commitment** relative to `n_units`,
  independent of how much empty land exists — i.e., don't let the
  expansion-trap fix (#4) keep pushing PLANT priority up once the farm
  already has more planted tiles than the labor force can realistically
  maintain.
- **Reconfirm the baseline first**: before trying any of the above, redo
  a clean run of the pre-land-buying, pre-trap-fix version (the commit
  tagged "improved workers logic", the one that produced 5855.0) to make
  sure that number still reproduces and nothing else silently regressed,
  *then* reintroduce land-buying and the trap fix one at a time — not
  both together again. Bundling them this session made it genuinely
  harder to isolate which change caused the regression.

## Process lessons from this whole project (worth keeping)

- Every "obvious" fix so far has had a real, unanticipated side effect,
  visible only from an actual run: sell-threshold too strict → fixed,
  hiring was uncapped → runaway → capped, task-priority trapped growth →
  fixed, expansion then outran labor → collapse. None of this was
  visible from reasoning alone; all four bugs surfaced from real
  episodes.
- Fix one thing at a time and re-test before bundling the next change —
  this session's land-buying + trap-fix pass being bundled together is
  exactly why isolating the new regression will take an extra step.
- Kaggle notebook gotchas that bit twice this project: (a) Python caches
  an imported module per kernel — re-cloning a repo doesn't force a
  reload; evict via `sys.modules.pop()` or restart the session before
  every re-test. (b) a relative-path clone-into-existing-directory cell
  nests repos if re-run from inside the target dir; use absolute paths
  and `rm -rf` the exact target before cloning, every time.
- `AGENTS.md`/`README.md` ship inside the installed `kaggle_environments`
  package — read them directly before guessing at anything schema- or
  format-related. This resolved essentially every open question in one
  pass, after several rounds of guessing that each needed correcting.

## Kaggle setup (for whoever continues this)

```python
import os, subprocess
REPO_URL = "https://github.com/chukka-venugopalam/kaggriculture.git"
REPO_ROOT = "/kaggle/working/kaggriculture"
os.chdir("/kaggle/working")
subprocess.run(["rm", "-rf", REPO_ROOT])
subprocess.run(["git", "clone", REPO_URL, REPO_ROOT], check=True)
os.chdir(REPO_ROOT)

import sys
sys.path.insert(0, f"{REPO_ROOT}/src/kaggriculture")
for mod in ("agent", "state", "strategy", "mechanics"):
    sys.modules.pop(mod, None)

!pip install -q -r requirements.txt
from kaggle_environments import make
from agent import agent
env = make("kaggriculture", configuration={"episodeSteps": 720}, debug=True)
steps = env.run([agent, "random"])
print("Final reward:", steps[-1][0].get("reward"))
```

Internet must be ON in the notebook's settings panel for both the clone
and the pip install.
