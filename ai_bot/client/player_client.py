
import asyncio
import math
import sys
from pathlib import Path

import grpc

# Windows global key polling without extra window (no admin needed)
import platform
if platform.system() == "Windows":
    import ctypes
    user32 = ctypes.windll.user32
    def _pressed(vk):
        return (user32.GetAsyncKeyState(vk) & 0x8000) != 0
else:
    # Fallback: always false (non-Windows)
    def _pressed(vk):  # type: ignore
        return False

# VK codes
VK_W = 0x57
VK_A = 0x41
VK_S = 0x53
VK_D = 0x44
VK_SPACE = 0x20

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from proto import arena_pb2, arena_pb2_grpc

class PlayerClient:
    """
    Human-controlled client (WASD + Space) using WinAPI key polling.
    - No extra window
    - No admin privileges required
    - Stable with pygame game window
    """
    def __init__(self, player_id="player1", bot_name="PLAYER", room_id="room_001", room_password="abc123"):
        self.player_id = player_id
        self.bot_name = bot_name
        self.room_id = room_id
        self.room_password = room_password
        self._stop = False
        self._aim_angle = 0.0

    async def _action_generator(self, action_queue: asyncio.Queue):
        while not self._stop:
            action = await action_queue.get()
            if action is None:
                break
            yield action

    async def _action_sender(self, action_queue: asyncio.Queue):
        try:
            while not self._stop:
                w = _pressed(VK_W); a = _pressed(VK_A); s = _pressed(VK_S); d = _pressed(VK_D)
                space = _pressed(VK_SPACE)

                x = float(d) - float(a)
                y = float(s) - float(w)

                mag = math.hypot(x, y)
                if mag > 1e-6:
                    self._aim_angle = math.atan2(y, x)
                    x /= mag; y /= mag

                action = arena_pb2.Action(
                    thrust=arena_pb2.Vec2(x=x, y=y),
                    aim_angle=self._aim_angle,
                    fire=bool(space),
                )
                await action_queue.put(action)
                await asyncio.sleep(1/60.0)
        except asyncio.CancelledError:
            pass

    async def _process_observation(self, observation: arena_pb2.Observation):
        try:
            # Only auto-aim when no manual direction pressed
            if not (_pressed(VK_W) or _pressed(VK_A) or _pressed(VK_S) or _pressed(VK_D)):
                dx = float(observation.enemy_pos.x) - float(observation.self_pos.x)
                dy = float(observation.enemy_pos.y) - float(observation.self_pos.y)
                if abs(dx) + abs(dy) > 1e-6:
                    self._aim_angle = math.atan2(dy, dx)
        except Exception:
            pass

    async def connect_and_play(self, host='localhost', port=50051):
        channel = grpc.aio.insecure_channel(f"{host}:{port}")
        stub = arena_pb2_grpc.ArenaBattleServiceStub(channel)
        registration = arena_pb2.BotRegistration(
            player_id=self.player_id,
            bot_name=f"{self.bot_name}|{self.room_id}|{self.room_password}"
        )
        resp = await stub.RegisterBot(registration)
        if not resp.success:
            raise RuntimeError(f"Register failed: {resp.message}")
        print(f"✅ Joined as {self.bot_name} in room {self.room_id}. Server assigned bot_id={resp.bot_id}")

        action_queue = asyncio.Queue()
        sender_task = asyncio.create_task(self._action_sender(action_queue))

        try:
            async for obs in stub.PlayGame(self._action_generator(action_queue)):
                await self._process_observation(obs)
        except Exception as e:
            print(f"💥 Game loop error: {e}")
        finally:
            self._stop = True
            sender_task.cancel()
            await channel.close()

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Human-controlled client (WASD + Space) using WinAPI polling")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--player_id", default="player1")
    parser.add_argument("--name", default="PLAYER")
    parser.add_argument("--room", default="room_001")
    parser.add_argument("--password", default="abc123")
    args = parser.parse_args()

    client = PlayerClient(player_id=args.player_id, bot_name=args.name, room_id=args.room, room_password=args.password)
    asyncio.run(client.connect_and_play(host=args.host, port=args.port))

if __name__ == "__main__":
    main()
