"""
scripts/test_harness.py — Run this anywhere with real network access: a
Kaggle notebook cell, a free VM, or CI. This project's history: every
synthetic-obs test across three prior agent files had at least one flaw
that took extra debugging to catch. A real harness run doesn't have that
failure mode.

Usage (from the repo root):
    pip install -r requirements.txt
    python scripts/test_harness.py
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src" / "kaggriculture"))

from agent import agent  # noqa: E402 (must follow the sys.path insert above)


def main() -> None:
    try:
        from kaggle_environments import make
    except ImportError:
        print("kaggle-environments isn't installed here.")
        print("Run: pip install -r requirements.txt")
        sys.exit(1)

    # VERIFY: the exact registered environment id. "kaggriculture" is a
    # guess based on the competition's name — check `kaggle_environments.envs`
    # or the competition page for the real id if this raises.
    env = make("kaggriculture")

    steps = env.run([agent, "random"])

    final_state = steps[-1][0]
    print("Episode finished.")
    print("Final reward (should reflect farm['money'] at episode end):")
    print(json.dumps(final_state.get("reward"), indent=2))

    # Dump the first observation so the two `# VERIFY:` spots in
    # src/kaggriculture/agent.py can be resolved against the real schema
    # instead of guessed at.
    first_obs = steps[0][0]["observation"]
    print("\nFirst observation top-level keys:", list(first_obs.keys()))
    out_path = REPO_ROOT / "sample_observation.json"
    with open(out_path, "w") as f:
        json.dump(first_obs, f, indent=2, default=str)
    print(f"Full first observation written to {out_path}")


if __name__ == "__main__":
    main()
