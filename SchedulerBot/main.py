import discord
from discord.ext import commands
import asyncio
import json
import pathlib
from datetime import datetime
import pytz
import calendar
import time
import difflib

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
bot: commands.Bot = commands.Bot(command_prefix=CONFIG["command_prefix"])


async def save_data():
    async with DATA_LOCK:
        with open(DATA_FILENAME, 'w') as f:
            json.dump(DATA, f, indent=4)


@bot.event
async def on_ready():
    print("Bot is ready.")


@bot.command(name="schedule", aliases=["s"])
async def command_schedule(ctx: commands.Context, day: str, time: str, *, message: str):
    guild_id_str = str(ctx.guild.id)
    # Check if schedule channel is set up
    if guild_id_str not in DATA or "schedule_channel" not in DATA[guild_id_str]:
        await ctx.send("Set up a channel first with `~here`")
        return

    if "schedule_timezone" not in DATA[guild_id_str]:
        await ctx.send("Set up timezone first with `~tz <timezone>`")
        return

    if "schedules" not in DATA[guild_id_str]:
        DATA[guild_id_str]["schedules"] = []

    DATA[guild_id_str]["schedules"].append({"day": day, "time": time, "message": message})
    await save_data()

    await ctx.send(f'Scheduled `{message}` for `{day}` `{time}`.')
    print(f'Scheduled `{message}` for `{day}` `{time}`.')


@bot.command(name="here", pass_context=True)
async def command_here(ctx: commands.Context):
    if str(ctx.guild.id) not in DATA:
        DATA[str(ctx.guild.id)] = {}

    DATA[str(ctx.guild.id)]["schedule_channel"] = ctx.channel.id
    await save_data()

    await ctx.send(f"Messages will go here now.")


@bot.command(name="timezone", aliases=["tz"], pass_context=True)
async def command_timezone(ctx: commands.Context, timezone: str):
    async def set_timezone(timezone: str):
        DATA[str(ctx.guild.id)]["schedule_timezone"] = timezone
        await save_data()
        await ctx.send(f"Timezone `{timezone}` set.")

    # Search for timezone in existing timezones
    for i in range(len(pytz.all_timezones)):
        if timezone.lower() == pytz.all_timezones[i].lower():
            await set_timezone(pytz.all_timezones[i])
            return

    # Get most similar timezones
    matches = difflib.get_close_matches(timezone, pytz.all_timezones, n=1, cutoff=0)
    if len(matches) > 0:
        # Ask author if he meant the similar timezone
        message: discord.Message = await ctx.send(f"Did you mean `{matches[0]}`?")
        await message.add_reaction("✅")
        await message.add_reaction("❌")
        # Wait for answer
        try:
            reaction = (await bot.wait_for("reaction_add", timeout=60, check=lambda r, u: u == ctx.author and str(r.emoji) in ("✅", "❌")))[0]
        except TimeoutError:
            return
        finally:
            await message.delete()

        if str(reaction.emoji) == "✅":
            await set_timezone(matches[0])
        else:
            await ctx.send("Timezone not found.")


async def continuously_run_schedules():
    await bot.wait_until_ready()
    while await asyncio.sleep(10, result=True):

        if datetime.now().second >= 10:
            print(datetime.now().second)
            continue

        try:
            for guild in DATA.values():
                # Check if theres channel and timezone
                if "schedule_channel" not in guild or "schedule_timezone" not in guild or "schedules" not in guild:
                    continue

                t = datetime.now(pytz.timezone(guild["schedule_timezone"]))

                for schedule in guild["schedules"]:
                    # Check for day
                    if calendar.day_name[t.weekday()].lower() != schedule["day"].lower():
                        continue

                    # Check for time
                    if t.hour != int(schedule["time"].split(":")[0]) or t.minute != int(schedule["time"].split(":")[1]):
                        continue

                    await bot.get_channel(guild["schedule_channel"]).send(schedule["message"])
                    print(f"Sent message. {t.hour}:{t.minute}")

        except Exception as e:
            print(f"Error: {e}")


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
