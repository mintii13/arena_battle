
from ai_bot.client.player_client import PlayerClient
import asyncio

def run():
    client = PlayerClient()
    asyncio.run(client.connect_and_play())

if __name__ == "__main__":
    run()
