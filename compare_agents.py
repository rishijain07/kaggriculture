"""Compare a candidate with its parent against the same opponents and seeds.

Example:
    .venv/bin/python compare_agents.py --candidate main.py \
        --baseline versions/main_v60_master.py \
        --opponents reference_v34/main.py starter --seed-start 10 --games 12
"""

import argparse
import importlib.util
import statistics
from pathlib import Path

from kaggle_environments import make


def load_agent(path, name):
    if path in {"pass", "random", "starter"}:
        return path
    source = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(name, source)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load agent: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.agent


def play(ours, opponent, seat, seed, steps):
    agents = [ours, opponent] if seat == 0 else [opponent, ours]
    env = make("kaggriculture", configuration={"episodeSteps": steps, "seed": seed}, debug=True)
    env.run(agents)
    final = env.steps[-1]
    own, rival = final[seat], final[1 - seat]
    if own.status != "DONE" or rival.status != "DONE":
        raise RuntimeError(
            f"seed={seed} seat={seat}: {own.status=} {rival.status=} "
            f"own_error={(own.info or {}).get('error')} "
            f"rival_error={(rival.info or {}).get('error')}"
        )
    return own.reward, rival.reward


def compare(candidate, baseline, opponent, seed_start, games, steps):
    bank_gains = []
    margin_gains = []
    outcome_changes = []
    for seed in range(seed_start, seed_start + games):
        for seat in (0, 1):
            old_own, old_rival = play(baseline, opponent, seat, seed, steps)
            new_own, new_rival = play(candidate, opponent, seat, seed, steps)
            bank_gains.append(new_own - old_own)
            margin_gains.append((new_own - new_rival) - (old_own - old_rival))
            old_outcome = (old_own > old_rival) - (old_own < old_rival)
            new_outcome = (new_own > new_rival) - (new_own < new_rival)
            outcome_changes.append(new_outcome - old_outcome)
    return {
        "games": len(bank_gains),
        "mean_bank_gain": statistics.mean(bank_gains),
        "median_bank_gain": statistics.median(bank_gains),
        "mean_margin_gain": statistics.mean(margin_gains),
        "bank_gains": (
            sum(gain > 0 for gain in bank_gains),
            sum(gain < 0 for gain in bank_gains),
            sum(gain == 0 for gain in bank_gains),
        ),
        "outcomes_improved": sum(change > 0 for change in outcome_changes),
        "outcomes_worsened": sum(change < 0 for change in outcome_changes),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", default="main.py")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--opponents", nargs="+", required=True)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--games", type=int, default=6, help="Seeds; both seats run for each seed")
    parser.add_argument("--steps", type=int, default=720)
    args = parser.parse_args()
    candidate = load_agent(args.candidate, "candidate_agent")
    baseline = load_agent(args.baseline, "baseline_agent")
    for index, path in enumerate(args.opponents):
        opponent = load_agent(path, f"opponent_agent_{index}")
        result = compare(candidate, baseline, opponent, args.seed_start, args.games, args.steps)
        plus, minus, ties = result["bank_gains"]
        print(
            f"{path}: {result['games']} games, "
            f"mean bank {result['mean_bank_gain']:+.1f}, "
            f"median {result['median_bank_gain']:+.1f}, "
            f"mean margin {result['mean_margin_gain']:+.1f}, "
            f"bank +/−/= {plus}/{minus}/{ties}, "
            f"outcomes improved/worsened "
            f"{result['outcomes_improved']}/{result['outcomes_worsened']}",
            flush=True,
        )


if __name__ == "__main__":
    main()
