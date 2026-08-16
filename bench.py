"""Local validation harness for Kaggriculture agents.

Usage:
  .venv/bin/python bench.py                      # vs random, starter, pass
  .venv/bin/python bench.py --agent main.py --opp starter --games 10
  .venv/bin/python bench.py --steps 720 --games 6 --seed 42
  .venv/bin/python bench.py --replay             # also dump replay.json + final states
"""

import argparse
import json
import os
import statistics

from kaggle_environments import make

HERE = os.path.dirname(os.path.abspath(__file__))
BUILTINS = ["pass", "random", "starter"]


def play(agent, opp, steps, seed):
    config = {"episodeSteps": steps}
    if seed is not None:
        config["seed"] = seed
    env = make("kaggriculture", configuration=config, debug=True)
    env.run([agent, opp])
    final = env.steps[-1]
    return (
        final[0].reward,
        final[1].reward,
        final[0].status,
        final[1].status,
        env,
    )


def summarize(name, results):
    diffs = [r0 - r1 for (r0, r1, s0, s1, _) in results if s0 == "DONE" and s1 == "DONE"]
    wins = sum(1 for d in diffs if d > 0)
    losses = sum(1 for d in diffs if d < 0)
    ties = len(diffs) - wins - losses
    errs = sum(1 for (r0, r1, s0, s1, _) in results if s0 == "ERROR" or s1 == "ERROR")
    avg_me = statistics.mean(r0 for (r0, r1, s0, s1, _) in results if s0 == "DONE")
    avg_opp = statistics.mean(r1 for (r0, r1, s0, s1, _) in results if s1 == "DONE")
    print(f"{name:12s}  W/L/T {wins:3d}/{losses:3d}/{ties:2d}  "
          f"avg bank {avg_me:9.0f} vs {avg_opp:9.0f}  "
          f"avg diff {statistics.mean(diffs):+9.0f}  (errors {errs})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="main.py")
    ap.add_argument("--opp", default=None)
    ap.add_argument("--games", type=int, default=6)
    ap.add_argument("--steps", type=int, default=720)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--replay", action="store_true")
    args = ap.parse_args()

    agent = args.agent if os.path.isabs(args.agent) else os.path.join(HERE, args.agent)
    opps = [args.opp] if args.opp else BUILTINS

    for opp in opps:
        results = []
        for g in range(args.games):
            seed = None if args.seed is None else args.seed + g
            r0, r1, s0, s1, env = play(agent, opp, args.steps, seed)
            results.append((r0, r1, s0, s1, env))
            if s0 == "ERROR":
                print(f"  ERROR in game {g} vs {opp}: {env.steps[-1][0].info.get('error')}")
        summarize(f"{agent} vs {opp}", results)
        if args.replay:
            env = results[-1][4]
            with open("replay.json", "w") as f:
                json.dump(env.toJSON(), f)
            for i, s in enumerate(env.steps[-1]):
                print(f"  final player {i}: reward={s.reward}, status={s.status}")


if __name__ == "__main__":
    main()