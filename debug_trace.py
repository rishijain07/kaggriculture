"""Deep trace: per-turn, per-unit decisions for the first 2 days."""
from kaggle_environments import make
import main

TRACE_TURNS = 48


def wrap(agent):
    def inner(obs):
        me = obs["farms"][obs["player"]]
        private = obs["private"]
        day, hour = obs["day"], obs["hour"]
        t = obs.get("step", 0)
        tiles = me["tiles"]
        board = len(tiles)
        if t < TRACE_TURNS:
            print(f"--- t{t} d{day} h{hour} money={me['money']:.0f} "
                  f"seeds={private['seeds'].get('WHEAT', 0)} shed_w={private['shed'].get('WHEAT', 0)} "
                  f"farmer={me['farmer']} hands={me['hands']}")
            for y in range(board):
                row = []
                for x in range(board):
                    tl = tiles[y][x]
                    if tl is None:
                        row.append(".")
                    elif tl == "LOCKED":
                        row.append("#")
                    elif tl.get("kind") == "WEED":
                        row.append("W")
                    elif tl.get("kind") == "PLANT":
                        row.append(f"P{day - tl['planted_day']}y{tl['yield_units']}{'u' if not tl['watered_today'] else ''}")
                    else:
                        row.append("?")
                print("   " + " ".join(row))
        action = agent(obs)
        if t < TRACE_TURNS:
            print(f"   -> farmer={action['farmer']} hands={action['hands']} market={action['market']}")
        return action
    return inner


env = make("kaggriculture", configuration={"episodeSteps": 720}, debug=True)
env.run([wrap(main.agent), "pass"])
print("final:", [(s.reward, s.status) for s in env.steps[-1]])