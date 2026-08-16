"""Debug runner: wraps main.agent, logging internal task decisions per turn."""
import sys
from kaggle_environments import make
import main

LOG_TURNS = 48


def wrap(agent):
    def inner(obs):
        action = agent(obs)
        me = obs["farms"][obs["player"]]
        t = obs.get("step", 0)
        if (t >= 144 and t < 168) or t % 24 == 0:
            tiles = me["tiles"]
            plants = [tt for row in tiles for tt in row if isinstance(tt, dict) and tt.get("kind") == "PLANT"]
            n_risk = sum(1 for tt in plants if tt["consecutive_unwatered"] >= 1)
            n_wat = sum(1 for tt in plants if not tt["watered_today"])
            print(f"t{t:3d} h{obs['hour']:2d}: money={me['money']:.0f} units={1 + len(me['hands'])} "
                  f"plants={len(plants)} risk={n_risk} unwatered={n_wat} "
                  f"f={action['farmer']} fpos={me['farmer']} "
                  f"h0={action['hands'][0] if action['hands'] else '-'} "
                  f"h0pos={me['hands'][0] if me['hands'] else '-'} "
                  f"market={action['market'][:3]}")
        return action
    return inner


env = make("kaggriculture", configuration={"episodeSteps": 720}, debug=True)
env.run([wrap(main.agent), "pass"])
final = env.steps[-1]
print("final:", [(s.reward, s.status) for s in final])
