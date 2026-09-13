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

## Verified against a real episode

A full 720-turn run (via a real Kaggle notebook) confirmed the action
format fix: the farmer walked, bought a seed, and planted, exactly on
schedule. It also surfaced a real bug -- `shop_aware_sell_plan` only sold
once the shed was nearly full, so with one or two crop tiles it silently
never sold anything, and money went steadily down (seed purchases with
no offsetting sales). Fixed to sell unconditionally, matching AGENTS.md's
own reference agent, and confirmed directly:
```
{"farmer": ["WEST"], "hands": [], "market": [["BUY_SEED","WHEAT",1], ["SELL","WHEAT",3]]}
```
`submission/main.py` re-verified identical to the modular source after
the fix.

## What's still open

- **Whether hiring actually helps in a real episode** -- HIRE fires when
  task backlog exceeds available units and the buffer is affordable
  (`HIRE_MONEY_BUFFER = 50`), and each hand gets assigned its own task the
  same way the farmer does, including the two-units-can't-plant-the-same-
  scarce-seed guard. Unit-tested; not yet run against a real 720-turn
  episode.
- **Task assignment is priority-order, not closest-unit** -- a hand can
  end up walking further than necessary while a nearer task goes to
  someone else assigned earlier in the loop
- **Ongoing-crop decay** (tomato/strawberry) isn't modeled --
  `max_lifespan_step` is always `-1` for these
- **Crop selection** for empty tiles is a placeholder (always WHEAT)
- **Land buying** (`BUY_LAND`) isn't attempted yet

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
