"""Commands across a real broker: a late one is never carried out.

The other tests hand the bridge a recording client. This one connects it to a
real MQTT broker, as it runs in a building, and plays the platform's side with
a second client: what is checked is what a door would do.

It backs turzi-apps BUILDING_CONNECTOR.md §9 (step 0, test 1): with the broker
in the building, a command can reach the bridge late only by being delayed on
its way, and it must then be refused by its own `issued_at` and `ttl_seconds`.

Skipped unless TURZI_LAB_BROKER=host:port names a broker that takes anonymous
clients (a throwaway Mosquitto: never a broker anything else uses). The test
harness only allows 127.0.0.1, so a remote one is reached through a tunnel.
"""

import asyncio
import json
import os
import time
import uuid

import aiomqtt
import pytest
from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.turzi_bridge.mqtt_bridge import TurziMqttBridge

from .helpers import bridge_entry, domain_filter

BROKER = os.environ.get("TURZI_LAB_BROKER")
pytestmark = pytest.mark.skipif(not BROKER, reason="set TURZI_LAB_BROKER=host:port to run against a real broker")

DOOR = "lock.puerta_principal"


async def test_a_late_command_is_refused_and_a_repeated_one_runs_once(hass: HomeAssistant, socket_enabled) -> None:
    host, port = BROKER.rsplit(":", 1)
    house = f"lab-{uuid.uuid4().hex[:8]}"
    entry = bridge_entry(
        hass,
        domain_filter("lock"),
        data={"mode": "cloud", "house_id": house, "broker": host, "port": int(port), "use_tls": False},
    )
    hass.states.async_set(DOOR, "locked", {})
    unlocked: list[ServiceCall] = []

    async def unlock(call: ServiceCall) -> None:
        unlocked.append(call)

    hass.services.async_register("lock", "unlock", unlock)

    acks: dict[str, list[dict]] = {}
    online = asyncio.Event()

    async with aiomqtt.Client(host, int(port)) as platform:
        await platform.subscribe(f"house/{house}/ack/#", qos=1)
        await platform.subscribe(f"house/{house}/availability", qos=1)

        async def listen() -> None:
            async for message in platform.messages:
                body = json.loads(message.payload)
                if str(message.topic).endswith("/availability"):
                    if body.get("state") == "online":
                        online.set()
                else:
                    acks.setdefault(body["command_id"], []).append(body)

        listener = asyncio.create_task(listen())
        bridge = TurziMqttBridge.from_config_entry(hass, entry)
        await bridge.async_start()
        try:
            await asyncio.wait_for(online.wait(), 15)

            async def send(command_id: str, age: float, ttl: int = 30) -> None:
                """The platform's command, as it looks when it arrives `age` seconds after it was issued."""
                await platform.publish(
                    f"house/{house}/command/lock/puerta_principal",
                    json.dumps({
                        "command": "lock.unlock",
                        "command_id": command_id,
                        "issued_at": time.time() - age,
                        "ttl_seconds": ttl,
                        "metadata": {"user_name": "Ana", "user_email": ""},
                    }),
                    qos=1,
                )

            async def ack(command_id: str) -> dict:
                for _ in range(100):
                    if command_id in acks:
                        return acks[command_id][0]
                    await asyncio.sleep(0.05)
                raise AssertionError(f"no ack for {command_id}")

            # On time: the door opens.
            await send("on-time", age=1)
            assert (await ack("on-time"))["status"] == "executed"
            assert len(unlocked) == 1

            # Late by more than its own time (30 s, and 10 s of clock tolerance).
            await send("late", age=45)
            assert ((await ack("late"))["status"], acks["late"][0]["reason"]) == ("failed", "expired")

            # A sender cannot keep an old command alive with a huge time to live:
            # the bridge's own ceiling (300 s) decides.
            await send("late-with-a-long-ttl", age=400, ttl=86400)
            assert (await ack("late-with-a-long-ttl"))["reason"] == "expired"
            assert len(unlocked) == 1

            # The same command delivered twice (a retry, a replay): once.
            await send("twice", age=1)
            await send("twice", age=1)
            assert (await ack("twice"))["status"] == "executed"
            await asyncio.sleep(0.5)
            assert len(unlocked) == 2
            assert len(acks["twice"]) == 1
        finally:
            await bridge.async_stop()
            listener.cancel()
            await asyncio.gather(listener, return_exceptions=True)
