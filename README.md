# Kaggriculture

Fresh build. Every piece of this -- observation schema, tile shapes, and
the action return format -- is confirmed directly against the official
`AGENTS.md`/`README.md` shipped inside the installed `kaggle_environments`
package, plus a real observation pulled from a live run. Nothing here is
guessed or reconstructed from a prior agent file's comments.

## Layout

```
src/kaggriculture/   the actual logic -- mechanics, state, strategy, agent
notebooks/           run_episode.ipynb -- clone, install, run a real episode
scripts/             build_submission.py, test_harness.py (non-notebook use)
submission/main.py   auto-generated, single-file, ready to submit as-is
tests/               unit tests, incl. tests against a REAL observation
```

## Why there's both `src/` and `submission/main.py`

Kaggle simulation competitions load the submitted file in isolation --
your repo's other files aren't present at grading time. `src/` is split
into modules for readability and testing; `submission/main.py` is the
same code auto-flattened into one file by `scripts/build_submission.py`,
already committed and ready to submit as-is.

**After any change under `src/kaggriculture/`, re-run the build and
commit the new output:**

```bash
python scripts/build_submission.py
```

## Confirmed, straight from AGENTS.md / README.md

- **Action format** (this was the actual bug behind reward staying pinned
  at $3000 -- the engine expects a dict, not a bare list):
  ```py
  {
    "farmer": [op, ...args],
    "hands":  [[op, ...args], ...],
    "market": [[op, ...args], ...],
  }
  ```
- **Tile shape** is `kind`-discriminated: `None` (empty), `"LOCKED"`, or a
  dict with `"kind"` one of `"PLANT"`, `"WEED"`, `"COOP"`, `"PASTURE"` --
  each with its own documented fields (`state.py::TileState.from_raw`
  matches this exactly, field for field)
- `money` lives on the farm dict; `tiles` is a 10x10 grid (`tiles[y][x]`);
  the main farmer is one `[x, y]` pair (`"farmer"`), hired hands are a
  separate list (`"hands"`); `unlocked_quadrants` is a list of names
- Crop table (seed cost, base price, yield timing) matches the README's
  Object Types table exactly, including per-crop unfertilized caps
- `mechanics.py` -- action vocabulary, shed cap, hire cost formula, shop
  demand table, market price shape functions
- `strategy.py::harvest_urgency()` -- decay-driven for one-time crops,
  reading `max_lifespan_step` directly

## Verified against real episodes

- A full 720-turn run confirmed the action-format fix and the sell-plan
  fix together: 3934.0 (from 3000 starting money) with just the farmer
  working alone.
- Hiring, once capped correctly at 3/day, took the same run to 5855.0 --
  roughly 3x the net profit (934 -> 2855).
- Land-buying and the nearest-tied-task fix are new this pass, verified
  directly (7 scenarios covering every trigger condition) but not yet
  run in a full episode.

`submission/main.py` re-verified identical to the modular source after
every change above.

## What's still open

- **Whether land-buying and the nearest-tied-task fix actually improve
  the real result** -- both are directly simulated and unit-tested (7
  hand-verified scenarios: nearest-tied-task selection, land purchase
  triggering/not-triggering in every relevant case, the market-order cap
  never being exceeded), but not yet run end-to-end for real.
- **Task assignment is a greedy nearest-pair heuristic**, not a true
  optimal assignment -- fine for a handful of units against a few dozen
  tasks, not guaranteed optimal
- **Ongoing-crop decay** (tomato/strawberry) isn't modeled --
  `max_lifespan_step` is always `-1` for these
- **Crop selection** for empty tiles is a placeholder (always WHEAT)
- `LAND_BUY_MIN_EMPTY_TILES = 3` and `LAND_BUY_MONEY_BUFFER = 500` are
  starting guesses, not tuned

## Deliberately left open (tunable -- resolve via real self-play, not a guess)

- `MAX_QUADRANTS` -- how many quadrants to actually buy, and when
- Opening animal ratio and unit ceiling once hiring is implemented

## Get this running on Kaggle, no local setup

1. Push to GitHub: `git init && git add . && git commit -m "..." && git
   remote add origin <url> && git push -u origin main`
2. Open `notebooks/run_episode.ipynb` on Kaggle (or paste its cells into
   a new notebook)
3. Turn **Internet ON** in the notebook's settings panel (right sidebar)
4. Edit `REPO_URL` in the first code cell
5. Run All -- **restart the session first if you've run an older version
   of `agent.py` in the same kernel already**; Python won't reload a
   module it's already imported just because the file on disk changed

## Tests

```bash
pip install pytest
pytest tests/
```

`tests/test_agent_parsing.py` runs against a real observation
(`tests/fixtures/sample_observation.json`), not just hand-built synthetic
dicts.
