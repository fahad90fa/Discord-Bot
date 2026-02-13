import discord
from discord.ext import commands
import asyncio
from datetime import timedelta, datetime
from .utils import load_data, load_ban_limits, save_ban_limits, send_modlog, DAILY_BAN_LIMIT, is_owner_check

def is_admin_or_owner():
    async def predicate(ctx):
        data = load_data()
        return ctx.author.id in data["owners"] or ctx.author.id in data["admins"]
    return commands.check(predicate)

def is_mod_admin_owner():
    async def predicate(ctx):
        data = load_data()
        return (
            ctx.author.id in data["owners"]
            or ctx.author.id in data["admins"]
            or ctx.author.id in data["mods"]
        )
    return commands.check(predicate)

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @is_owner_check()
    async def kick(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Execute KICK sequence on a target entity"""
        load_msg = await ctx.send("👢 `EXECUTING DISCONNECT SEQUENCE...`")
        await member.kick(reason=reason)
        await asyncio.sleep(0.5)
        
        embed = discord.Embed(
            title="🛡️ ENTITY DISCONNECTED",
            description=(
                "```ansi\n"
                f"\u001b[1;31mTARGET  :\u001b[0m \u001b[0;37m{member}\u001b[0m\n"
                f"\u001b[1;31mSTATUS  :\u001b[0m \u001b[0;37mEVICTED\u001b[0m\n"
                f"\u001b[1;31mREASON  :\u001b[0m \u001b[0;37m{reason}\u001b[0m\n"
                "```"
            ),
            color=0xff4b4b
        )
        embed.set_author(name="TRADERS UNION SECURITY", icon_url=self.bot.user.display_avatar.url)
        await load_msg.delete()
        await ctx.send(embed=embed)
        await send_modlog(self.bot, ctx, "kick", target=member, reason=reason)

    @commands.command()
    @is_owner_check()
    async def mute(self, ctx, member: discord.Member, minutes: int = 60, *, reason="No reason provided"):
        """Execute TIMEOUT sequence on a target entity"""
        load_msg = await ctx.send("⏳ `ISOLATING ENTITY FROM COMMS...`")
        await member.timeout(timedelta(minutes=minutes), reason=reason)
        await asyncio.sleep(0.5)
        
        embed = discord.Embed(
            title="🛡️ COMMS ISOLATED",
            description=(
                "```ansi\n"
                f"\u001b[1;33mTARGET   :\u001b[0m \u001b[0;37m{member}\u001b[0m\n"
                f"\u001b[1;33mDURATION :\u001b[0m \u001b[0;37m{minutes} MINUTES\u001b[0m\n"
                f"\u001b[1;33mREASON   :\u001b[0m \u001b[0;37m{reason}\u001b[0m\n"
                "```"
            ),
            color=0xffa500
        )
        embed.set_author(name="TRADERS UNION SECURITY", icon_url=self.bot.user.display_avatar.url)
        await load_msg.delete()
        await ctx.send(embed=embed)
        await send_modlog(self.bot, ctx, "Mute", target=member, reason=reason, duration=minutes)

    @commands.command()
    @is_owner_check()
    async def unmute(self, ctx, member: discord.Member):
        await member.timeout(None)
        await ctx.send(f"🔓 Timeout removed for {member}")
        await send_modlog(self.bot, ctx, "UnMute", target=member)

    @commands.command()
    @is_owner_check()
    async def clear(self, ctx, amount: int):
        """Execute DATA WIPE in current channel"""
        load_msg = await ctx.send("🧹 `INITIALIZING DATA WIPE...`")
        await ctx.channel.purge(limit=amount + 2)
        await asyncio.sleep(0.5)
        
        embed = discord.Embed(
            title="🧹 SECTOR CLEANED",
            description=(
                "```ansi\n"
                f"\u001b[1;34mWIPE MAGNITUDE :\u001b[0m \u001b[0;37m{amount} MESSAGES\u001b[0m\n"
                f"\u001b[1;34mSTATUS         :\u001b[0m \u001b[0;37mSUCCESSFUL\u001b[0m\n"
                "```"
            ),
            color=0x3498db
        )
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(3)
        await msg.delete()
        await send_modlog(self.bot, ctx, "Clear", amount=amount)

    @commands.command()
    @is_owner_check()
    async def purgeuser(self, ctx, member: discord.Member, amount: int):
        deleted = await ctx.channel.purge(
            limit=amount + 1, check=lambda m: m.author == member
        )
        msg = await ctx.send(f"🧹 Deleted {len(deleted)-1} messages from {member}")
        await asyncio.sleep(2)
        await msg.delete()
        await send_modlog(self.bot, ctx, "Purge User", target=member, amount=amount)

    @commands.command()
    @is_owner_check()
    async def purgebot(self, ctx, amount: int):
        deleted = await ctx.channel.purge(
            limit=amount + 1, check=lambda m: m.author.bot
        )
        msg = await ctx.send(f"🤖 Deleted {len(deleted)-1} bot messages")
        await asyncio.sleep(2)
        await msg.delete()
        await send_modlog(self.bot, ctx, "Purge Bot", amount=amount)

    @commands.command()
    @is_owner_check()
    async def ban(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Execute TERMINATE sequence on a target entity"""
        data = load_data()
        ban_limits = load_ban_limits()
        admin_id = str(ctx.author.id)
        today = datetime.utcnow().strftime("%Y-%m-%d")

        load_msg = await ctx.send("🔨 `TERMINATING ENTITY ACCESS...`")
        
        await member.ban(reason=reason)

        embed = discord.Embed(
            title="🔨 ACCESS TERMINATED",
            description=(
                "```ansi\n"
                f"\u001b[1;31mENTITY   :\u001b[0m \u001b[0;37m{member}\u001b[0m\n"
                f"\u001b[1;31mSTRIKE   :\u001b[0m \u001b[0;37mHARD BAN\u001b[0m\n"
                f"\u001b[1;31mREASON   :\u001b[0m \u001b[0;37m{reason}\u001b[0m\n"
                "```"
            ),
            color=0x000000
        )
        embed.set_author(name="TRADERS UNION HIGH COMMAND", icon_url=self.bot.user.display_avatar.url)
        await load_msg.delete()
        await ctx.send(embed=embed)
        await send_modlog(self.bot, ctx, "Ban", target=member, reason=reason)

    @commands.command()
    @is_owner_check()
    async def unban(self, ctx, user_id: int):
        user = await self.bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"🔓 Unbanned {user}")
        await send_modlog(self.bot, ctx, "Unban", target=user_id)

    @commands.command()
    @is_owner_check()
    async def hide(self, ctx):
        overwrites = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrites.view_channel = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrites)
        await ctx.send(f"🔒 Channel hidden for everyone.")
        await send_modlog(self.bot, ctx, "Hide")

    @commands.command()
    @is_owner_check()
    async def unhide(self, ctx):
        overwrites = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrites.view_channel = True
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrites)
        await ctx.send(f"🔓 Channel is now visible for everyone.")
        await send_modlog(self.bot, ctx, "UnHide")

    @commands.command()
    @is_owner_check()
    async def lock(self, ctx):
        overwrites = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrites.send_messages = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrites)
        await ctx.send(f"🔒 Channel locked. Only admins can send messages.")
        await send_modlog(self.bot, ctx, "Lock")

    @commands.command()
    @is_owner_check()
    async def unlock(self, ctx):
        overwrites = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrites.send_messages = True
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrites)
        await ctx.send(f"🔓 Channel unlocked. Everyone can send messages now.")
        await send_modlog(self.bot, ctx, "UnLock")

async def setup(bot):
    await bot.add_cog(Moderation(bot))
