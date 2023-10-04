"""Common configuration items used by the application."""
import json
import pathlib
import random

BASE_DIRECTORY = pathlib.Path(__file__).parent.resolve()


def random_user_agent():
    """Choose a user agent from a list of commonly used agents."""
    with open(f"{BASE_DIRECTORY}/data/common_user_agents.json", "r") as fileh:
        user_agents = json.load(fileh)

    random.shuffle(user_agents)
    return [x["ua"] for x in user_agents][0]
