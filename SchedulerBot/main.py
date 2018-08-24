import discord
from discord.ext import commands
import asyncio
import json
import pathlib
from datetime import datetime
import calendar
import time

# Constants
CONFIG_FILENAME = "config.json"
DATA_FILENAME = "data.json"

# Load data
with open(CONFIG_FILENAME, 'r') as f:
    CONFIG = json.load(f)
if pathlib.Path(DATA_FILENAME).is_file():
    with open(DATA_FILENAME, 'r') as f:
        DATA = json.load(f)
else:
    with open(DATA_FILENAME, 'w') as f:
        DATA = {}
        json.dump(DATA, f, indent=4)
DATA_LOCK = asyncio.Lock()

# Connect to discord
client: discord.Client = discord.Client()
bot: commands.Bot = commands.Bot(command_prefix=CONFIG["command_prefix"])


@bot.event
async def on_ready():
    print("Bot is ready.")


@bot.command(name="schedule", aliases=["s"], pass_context=True)
async def command_schedule(ctx: commands.Context, day: str, time: str, message: str):
    server_id = ctx.message.server.id
    # Check if schedule channel is set up
    if server_id not in DATA or "schedule_channel" not in DATA[server_id]:
        await bot.say("Must set up channel first with `~here`")
        return

    async with DATA_LOCK:
        if "schedules" not in DATA[server_id]:
            DATA[server_id]["schedules"] = []

        DATA[server_id]["schedules"].append({"day": day, "time": time, "message": message})

        with open(DATA_FILENAME, 'w') as f:
            json.dump(DATA, f, indent=4)

    await bot.say(f'Scheduled "{message}" for {day} {time}.')
    print(f'Scheduled "{message}" for {day} {time}.')


@bot.command(name="here", pass_context=True)
async def command_here(ctx: commands.Context):
    if ctx.message.server.id not in DATA:
        DATA[ctx.message.server.id] = {}

    async with DATA_LOCK:
        DATA[ctx.message.server.id]["schedule_channel"] = ctx.message.channel.id

        with open(DATA_FILENAME, 'w') as f:
            json.dump(DATA, f, indent=4)

    await bot.say(f"Messages will go here now.")


async def continuously_run_schedules():
    await bot.wait_until_ready()
    while True:
        try:
            t = datetime.now()
            for s in DATA.values():
                # Check if theres a channel
                if "schedule_channel" not in s:
                    continue

                for schedule in s["schedules"]:
                    # Check for day
                    if calendar.day_name[t.weekday()].lower() != schedule["day"].lower():
                        continue

                    # Check for time
                    if t.hour != int(schedule["time"].split(":")[0]) or t.minute != int(schedule["time"].split(":")[1]):
                        continue

                    await bot.send_message(bot.get_channel(s["schedule_channel"]), schedule["message"])
                    print(f"Sent message. {t.hour}:{t.minute}")

        except Exception as e:
            print(f"Error: {e}")

        await asyncio.sleep(60)


# Reload data every once in a while
async def continuously_reload_data():
    global DATA
    while True:
        await asyncio.sleep(60)
        t0 = time.time()

        with open(DATA_FILENAME, 'r') as f:
            DATA = json.load(f)

        print(f"Reloaded data in {int(round((time.time() - t0) * 1000))} ms.")


bot.loop.create_task(continuously_run_schedules())
bot.loop.create_task(continuously_reload_data())
bot.run(CONFIG["token"])
