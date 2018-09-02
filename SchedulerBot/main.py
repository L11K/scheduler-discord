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
import re

WEEKDAYS_NUMBERS = {
    "sunday": 1,
    "monday": 2,
    "tuesday": 3,
    "wednesday": 4,
    "thursday": 5,
    "friday": 6,
    "saturday": 7
}
NUMBERS_WEEKDAYS = {v: k for k, v in WEEKDAYS_NUMBERS.items()}

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


def format_time(time_str: str) -> str:
    try:
        only_time = re.findall("(?:\d(?:\S*)\d)|\d", time_str)[0]
        am_pm = ""
        if "am" in time_str.lower():
            am_pm = " AM"
        elif "pm" in time_str.lower():
            am_pm = " PM"

        format = "%H" if am_pm == "" else "%I"
        if ':' in only_time:
            format += ":%M"

        if am_pm != "":
            format += " %p"

        final_time = datetime.strptime(f"{only_time}{am_pm}", format)
        return final_time.strftime("%H:%M")
    except Exception as e:
        print(f"Time formatting error: {e}")
        return None


@bot.event
async def on_ready():
    print("Bot is ready.")


@bot.command(name="schedule", aliases=["s"])
async def command_schedule(ctx: commands.Context, *, message_to_schedule):
    guild_id_str = str(ctx.guild.id)

    # Check if schedule channel is set up
    if guild_id_str not in DATA or "schedule_channel" not in DATA[guild_id_str]:
        await ctx.send("Set up a channel first with `~here`")
        return
    # Check if timezone is set up
    if "schedule_timezone" not in DATA[guild_id_str]:
        await ctx.send("Set up timezone first with `~tz <timezone>`")
        return
    # Initialize schedules list
    if "schedules" not in DATA[guild_id_str]:
        DATA[guild_id_str]["schedules"] = []

    schedule = {"message": message_to_schedule, "days": [], "time": "", "repeat": False}

    # Ask for days and repeat
    days_message: discord.Message = await ctx.send(":calendar_spiral: Choose days and if you want to repeat.")
    reactions = [f"{n}\u20e3" for n in NUMBERS_WEEKDAYS] + ["🔁", "✅"]
    for r in reactions:
        await days_message.add_reaction(r)
    # Wait for answer
    try:
        await bot.wait_for("reaction_add", timeout=60, check=lambda r, u: u == ctx.author and str(r.emoji) == "✅")
    except TimeoutError:
        pass

    async with ctx.typing():
        days_message = await ctx.channel.get_message(days_message.id)
        # Set question results
        for r in days_message.reactions:
            if str(r.emoji) in reactions[:-1] and r.count > 1 and ctx.author in await r.users().flatten():
                # If day
                try:
                    if int(str(r.emoji)[0]) in NUMBERS_WEEKDAYS:
                        schedule["days"].append(NUMBERS_WEEKDAYS[int(str(r.emoji)[0])])
                        continue
                except ValueError:
                    pass
                # If repeat
                if str(r.emoji) == "🔁":
                    schedule["repeat"] = True

    # Time
    while True:
        # Ask for time
        await ctx.send(":clock3: Enter the time.")
        # Wait for answer
        try:
            answer_message: discord.Message = await bot.wait_for("message", timeout=60, check=lambda m: m.author == ctx.author)
        except TimeoutError:
            return

        async with ctx.typing():
            formatted_time = format_time(answer_message.content)
            if formatted_time is not None:
                schedule["time"] = formatted_time
                break

    # Send confirmation
    async with ctx.typing():
        repeat_str = "once" if schedule["repeat"] is not True else ("weekly" if len(schedule["days"]) > 0 else "daily")
        days_str = (" on " + ", ".join([f"`{d}`" for d in schedule["days"]])) if len(schedule["days"]) > 0 else ""
        await ctx.send(f"Your message `{message_to_schedule}` will be sent `{repeat_str}`{days_str} at `{schedule['time'].lstrip('0')}`.")

    # Save the schedule
    DATA[guild_id_str]["schedules"].append(schedule)
    await save_data()


@bot.command(name="here")
async def command_here(ctx: commands.Context):
    if str(ctx.guild.id) not in DATA:
        DATA[str(ctx.guild.id)] = {}

    DATA[str(ctx.guild.id)]["schedule_channel"] = ctx.channel.id
    await save_data()

    await ctx.send(f"Messages will go here now.")


@bot.command(name="timezone", aliases=["tz"])
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
            continue

        # Iterate each guild
        for guild in DATA.values():
            # Check if theres channel and timezone
            if "schedule_channel" not in guild or "schedule_timezone" not in guild or "schedules" not in guild:
                continue

            curr_time = datetime.now(pytz.timezone(guild["schedule_timezone"]))

            try:
                # Iterate each schedule
                for schedule in guild["schedules"]:
                    # Check for day
                    curr_day = calendar.day_name[curr_time.weekday()].lower()
                    if len(schedule["days"]) > 0 and curr_day not in schedule["days"]:
                        continue

                    # Check for time
                    schedule_time = datetime.strptime(schedule["time"], "%H:%M")
                    if curr_time.hour != schedule_time.hour or curr_time.minute != schedule_time.minute:
                        continue

                    # Send the message
                    await bot.get_channel(guild["schedule_channel"]).send(schedule["message"])

                    # Delete schedule data if repeats once
                    if schedule["repeat"] is False:
                        if len(schedule["days"]) > 0:
                            schedule["days"].remove(curr_day)

                        if len(schedule["days"]) == 0:
                            guild["schedules"].remove(schedule)

                        await save_data()

            except Exception as e:
                print(f"Error: {e}")


# Reload data every once in a while
async def continuously_reload_data():
    global DATA
    while await asyncio.sleep(60, result=True):
        t0 = time.time()

        with open(DATA_FILENAME, 'r') as f:
            DATA = json.load(f)

        print(f"Reloaded data in {int(round((time.time() - t0) * 1000))} ms.")


bot.loop.create_task(continuously_run_schedules())
bot.loop.create_task(continuously_reload_data())
bot.run(CONFIG["token"])
