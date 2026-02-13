import discord
from discord.ext import commands
import json
import os
import asyncio
from dotenv import load_dotenv
from cogs.utils import load_json

# Load environment variables
load_dotenv()

# Core Configuration
FILE = "moderation.json"
OWNER_ID = [1368206959316041894]
PREFIXES = ["-", ""]

def get_prefix(bot, message):
    try:
        with open("info.json", "r") as f:
            data = json.load(f)
            no_prefix_users = data.get("np", [])
            if message.author.id in no_prefix_users:
                return PREFIXES
            else:
                return "-"
    except:
        return "-"

# Bot Initialization
intents = discord.Intents.all()
intents.message_content = True

bot = commands.Bot(
    command_prefix=get_prefix,
    intents=intents,
    owner_ids=set(OWNER_ID),
    case_insensitive=True,
    strip_after_prefix=True
)
bot.remove_command('help')

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"------ SYSTEM ONLINE ------")

async def setup_hook():
    # Load Extensions
    extensions = [
        "cogs.forex",
        "cogs.moderation",
        "cogs.utility",
        "cogs.admin",
        "cogs.events",
        "cogs.general",
        "cogs.union_points",
        "cogs.forex_ai",
        "cogs.attendance"
    ]
    
    for ext in extensions:
        try:
            await bot.load_extension(ext)
            print(f"✅ Loaded {ext}")
        except Exception as e:
            print(f"❌ Failed to load {ext}: {e}")

bot.setup_hook = setup_hook

# Core Message Handler (Mainly for Mention Responder)
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Bot Mention Trigger
    if bot.user in message.mentions and len(message.content.split()) == 1:
        embed = discord.Embed(
            title="🤖 TRADERS UNION | SYSTEM INFO",
            description=(
                f"**STATUS:** `OPERATIONAL`\n"
                f"**PREFIX:** `-`\n"
                f"**TYPE:** `INSTITUTIONAL MANAGER`"
            ),
            color=0x2b2d31
        )
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        embed.set_footer(text="Traders Union v4.0 • Level 5 Authorization")
        await message.channel.send(embed=embed)

    await bot.process_commands(message)

# Run Global Security Protocol
if __name__ == "__main__":
    # Get token from environment variable
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    if not DISCORD_TOKEN:
        print("❌ ERROR: DISCORD_TOKEN not found in .env file!")
        exit(1)
    
    bot.run(DISCORD_TOKEN)
