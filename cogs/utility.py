import discord
from discord.ext import commands
import asyncio
import re
import aiohttp
import io
import os
from datetime import datetime
import db
from .utils import load_data, send_modlog, is_owner_check

SNIPE_FILE = "snipe_cache.json"
MAX_SNIPES_PER_CHANNEL = 20

def _trim_snipes(snipes, max_len):
    if len(snipes) <= max_len:
        return snipes
    return snipes[-max_len:]

def is_admin_or_owner():
    async def predicate(ctx):
        data = load_data(ctx.guild.id)
        return ctx.author.id in data["owners"] or ctx.author.id in data["admins"]
    return commands.check(predicate)

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or not message.channel:
            return
        if message.author and message.author.bot:
            return

        guild_id = str(message.guild.id)
        channel_id = str(message.channel.id)
        # insert into table

        attachments = []
        for a in (message.attachments or []):
            try:
                attachments.append({"filename": a.filename, "url": a.url})
            except Exception:
                continue

        stickers = []
        for s in (message.stickers or []):
            try:
                stickers.append({"name": s.name, "url": s.url})
            except Exception:
                continue

        reply_info = None
        if message.reference and message.reference.message_id:
            reply_info = {
                "message_id": str(message.reference.message_id),
                "channel_id": str(message.reference.channel_id) if message.reference.channel_id else None,
                "author_id": str(message.reference.resolved.author.id) if message.reference.resolved and message.reference.resolved.author else None
            }

        db.execute(
            """
            INSERT INTO snipe_cache
            (guild_id, channel_id, message_id, author_id, author_name, content, attachments, stickers, created_at, deleted_at, reply_to_message_id, reply_to_author_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                int(guild_id),
                int(channel_id),
                int(message.id),
                int(message.author.id) if message.author else None,
                str(message.author) if message.author else "Unknown",
                message.content or "",
                ",".join(a["url"] for a in attachments),
                ",".join(s["url"] for s in stickers),
                message.created_at.isoformat() if message.created_at else None,
                datetime.utcnow().isoformat(),
                int(reply_info["message_id"]) if reply_info and reply_info.get("message_id") else None,
                int(reply_info["author_id"]) if reply_info and reply_info.get("author_id") else None
            )
        )

    @commands.command(name="snipe")
    @commands.guild_only()
    async def snipe(self, ctx, channel: discord.TextChannel = None, index: int = 1):
        """Show recently deleted messages. Usage: -snipe [#channel] [index]"""
        channel = channel or ctx.channel
        if index < 1:
            return await ctx.send("❌ Index must be 1 or higher.")

        channel_snipes = db.execute(
            """
            SELECT * FROM snipe_cache
            WHERE guild_id = %s AND channel_id = %s
            ORDER BY deleted_at DESC
            LIMIT %s
            """,
            (int(ctx.guild.id), int(channel.id), MAX_SNIPES_PER_CHANNEL),
            fetchall=True
        ) or []
        if not channel_snipes:
            return await ctx.send("❌ Nothing to snipe in this channel.")

        if index > len(channel_snipes):
            return await ctx.send(f"❌ Only {len(channel_snipes)} snipes available for this channel.")

        item = channel_snipes[index - 1]

        embed = discord.Embed(
            title="🛰️ SNIPE CAPTURE",
            color=0x2b2d31,
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Author", value=f"<@{item['author_id']}> (`{item['author_id']}`)" if item.get("author_id") else item.get("author_name", "Unknown"), inline=False)
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(name="Index", value=f"`{index}/{len(channel_snipes)}`", inline=True)

        content = item.get("content") or "`(no text)`"
        if len(content) > 1800:
            content = content[:1800] + "..."
        embed.add_field(name="Content", value=content, inline=False)

        if item.get("attachments"):
            urls = [u for u in (item.get("attachments") or "").split(",") if u]
            files = "\n".join(f"- {u}" for u in urls[:5])
            embed.add_field(name="Attachments", value=files, inline=False)

        if item.get("stickers"):
            urls = [u for u in (item.get("stickers") or "").split(",") if u]
            st = "\n".join(f"- {u}" for u in urls[:5])
            embed.add_field(name="Stickers", value=st, inline=False)

        if item.get("reply_to_message_id"):
            reply_text = f"Message ID: `{item.get('reply_to_message_id')}`"
            if item.get("reply_to_author_id"):
                reply_text += f"\nAuthor: <@{item.get('reply_to_author_id')}>"
            embed.add_field(name="Reply To", value=reply_text, inline=False)

        if item.get("created_at"):
            try:
                created = datetime.fromisoformat(item["created_at"])
                embed.set_footer(text=f"Sent at {created.strftime('%b %d, %I:%M %p UTC')}")
            except Exception:
                pass

        await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True)
    async def ping(self, ctx):
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 Pong! `{latency}ms`")

    @commands.command(name="userinfo", aliases=['ui'])
    async def userinfo(self, ctx, member: discord.Member = None):
        """Deep scan a user profile using the Quantum Terminal interface"""
        member = member or ctx.author
        
        load_msg = await ctx.send(f"💾 `INITIALIZING SCAN FOR {member.name.upper()}...`")
        await asyncio.sleep(0.5)
        await load_msg.edit(content="🛰️ `CONNECTING TO DISCORD GATEWAY GATEWAY...`")
        await asyncio.sleep(0.5)
        await load_msg.edit(content="💎 `DECRYPTING USER ENTITY DATA...`")

        guild = ctx.guild
        roles = [role.mention for role in member.roles[1:]]
        roles_display = ", ".join(roles) if roles else "None"
        
        joined_at = member.joined_at.strftime("%b %d, %Y")
        created_at = member.created_at.strftime("%b %d, %Y")
        status = str(member.status).title()
        avatar_url = member.display_avatar.url
        
        devices = []
        if member.desktop_status != discord.Status.offline: devices.append("Desktop")
        if member.mobile_status != discord.Status.offline: devices.append("Mobile")
        if member.web_status != discord.Status.offline: devices.append("Web")
        device_info = "/".join(devices) if devices else "Offline"

        members = sorted(guild.members, key=lambda m: m.joined_at)
        join_pos = members.index(member) + 1
        acc_age = (discord.utils.utcnow() - member.created_at).days

        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        
        embed = discord.Embed(title=f"| USER INTELLIGENCE | {member.name.upper()}", color=member.color or 0x2b2d31)
        embed.set_author(name="TRADERS UNION TERMINAL", icon_url=logo)
        embed.set_thumbnail(url=avatar_url)

        identity_block = (
            "```ansi\n"
            f"\u001b[1;36mDISPLAY NAME :\u001b[0m \u001b[0;37m{member.display_name}\u001b[0m\n"
            f"\u001b[1;36mENTITY ID    :\u001b[0m \u001b[0;37m{member.id}\u001b[0m\n"
            f"\u001b[1;36mTOP ROLE     :\u001b[0m \u001b[0;37m{member.top_role.name}\u001b[0m\n"
            "```"
        )
        embed.add_field(name="🆔 IDENTITY SIGNATURE", value=identity_block, inline=False)

        network_block = (
            "```ansi\n"
            f"\u001b[1;32mCURRENT STATUS :\u001b[0m \u001b[0;37m{status}\u001b[0m\n"
            f"\u001b[1;32mACTIVE RADIUS  :\u001b[0m \u001b[0;37m{device_info}\u001b[0m\n"
            f"\u001b[1;32mBOT STATUS     :\u001b[0m \u001b[0;37m{member.bot}\u001b[0m\n"
            "```"
        )
        embed.add_field(name="📡 NETWORK PRESENCE", value=network_block, inline=False)

        timeline_block = (
            "```ansi\n"
            f"\u001b[1;34mACCOUNT BORN   :\u001b[0m \u001b[0;37m{created_at} ({acc_age}d)\u001b[0m\n"
            f"\u001b[1;34mSECTOR JOINED  :\u001b[0m \u001b[0;37m{joined_at} (Pos: #{join_pos})\u001b[0m\n"
            "```"
        )
        embed.add_field(name="🕒 TIMELINE PULSE", value=timeline_block, inline=False)

        try:
            user_data = await self.bot.fetch_user(member.id)
            if user_data.banner:
                embed.set_image(url=user_data.banner.url)
        except:
            pass

        if len(roles) > 0:
            embed.add_field(name="📜 ASSIGNED SECTORS", value=roles_display[:1024], inline=False)

        embed.set_footer(text=f"Sourced via Traders Union Gateway • Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        
        await load_msg.delete()
        await ctx.send(embed=embed)

    @commands.command(name="serverinfo", aliases=['si'])
    @commands.guild_only()
    async def serverinfo(self, ctx):
        """Deep scan the current server mainframe using the Quantum Terminal interface"""
        guild = ctx.guild
        
        load_msg = await ctx.send(f"💾 `INITIALIZING SCAN FOR {guild.name.upper()}...`")
        await asyncio.sleep(0.5)
        await load_msg.edit(content="🛰️ `CONNECTING TO GUILD METADATA ENGINE...`")
        await asyncio.sleep(0.5)
        await load_msg.edit(content="💎 `DECRYPTING SECTOR ARCHITECTURE...`")

        # Member Stats
        total_members = guild.member_count
        humans = len([m for m in guild.members if not m.bot])
        bots = len([m for m in guild.members if m.bot])
        
        online = len([m for m in guild.members if m.status == discord.Status.online])
        idle = len([m for m in guild.members if m.status == discord.Status.idle])
        dnd = len([m for m in guild.members if m.status == discord.Status.dnd])
        offline = len([m for m in guild.members if m.status == discord.Status.offline])

        # Channel Stats
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        stage_channels = len(guild.stage_channels)
        forum_channels = len(guild.forum_channels)
        total_channels = text_channels + voice_channels + stage_channels + forum_channels

        # Other Stats
        roles = len(guild.roles)
        emojis = len(guild.emojis)
        stickers = len(guild.stickers)
        boost_level = guild.premium_tier
        boost_count = guild.premium_subscription_count
        
        created_at = guild.created_at.strftime("%b %d, %Y")
        server_age = (discord.utils.utcnow() - guild.created_at).days
        
        owner = guild.owner
        verif_level = str(guild.verification_level).replace("_", " ").title()
        content_filter = str(guild.explicit_content_filter).replace("_", " ").title()
        
        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        
        embed = discord.Embed(title=f"| GUILD INTELLIGENCE | {guild.name.upper()}", color=0x2b2d31)
        embed.set_author(name="TRADERS UNION TERMINAL", icon_url=logo)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        if guild.banner:
            embed.set_image(url=guild.banner.url)

        mainframe_block = (
            "```ansi\n"
            f"\u001b[1;36mGUILD OWNER   :\u001b[0m \u001b[0;37m{owner} ({owner.id})\u001b[0m\n"
            f"\u001b[1;36mSECTOR ID     :\u001b[0m \u001b[0;37m{guild.id}\u001b[0m\n"
            f"\u001b[1;36mCREATED ON    :\u001b[0m \u001b[0;37m{created_at} ({server_age} days ago)\u001b[0m\n"
            f"\u001b[1;36mVERIFICATION  :\u001b[0m \u001b[0;37m{verif_level}\u001b[0m\n"
            "```"
        )
        embed.add_field(name="🏢 MAINFRAME SIGNATURE", value=mainframe_block, inline=False)

        population_block = (
            "```ansi\n"
            f"\u001b[1;32mTOTAL ENTITIES :\u001b[0m \u001b[0;37m{total_members}\u001b[0m\n"
            f"\u001b[1;32mHUMAN SIGNALS  :\u001b[0m \u001b[0;37m{humans}\u001b[0m\n"
            f"\u001b[1;32mBOT SIGNALS    :\u001b[0m \u001b[0;37m{bots}\u001b[0m\n"
            f"\u001b[1;32mACTIVE RADAR   :\u001b[0m \u001b[0;37mONL: {online} | IDL: {idle} | DND: {dnd}\u001b[0m\n"
            "```"
        )
        embed.add_field(name="👥 POPULATION DENSITY", value=population_block, inline=False)

        architecture_block = (
            "```ansi\n"
            f"\u001b[1;34mTOTAL CHANNELS :\u001b[0m \u001b[0;37m{total_channels}\u001b[0m\n"
            f"\u001b[1;34mTEXT / VOICE   :\u001b[0m \u001b[0;37m{text_channels} / {voice_channels}\u001b[0m\n"
            f"\u001b[1;34mCATEGORIES     :\u001b[0m \u001b[0;37m{categories}\u001b[0m\n"
            f"\u001b[1;34mSTAGE / FORUM  :\u001b[0m \u001b[0;37m{stage_channels} / {forum_channels}\u001b[0m\n"
            "```"
        )
        embed.add_field(name="🛰️ SECTOR ARCHITECTURE", value=architecture_block, inline=False)

        asset_block = (
            "```ansi\n"
            f"\u001b[1;35mTOTAL ROLES    :\u001b[0m \u001b[0;37m{roles}\u001b[0m\n"
            f"\u001b[1;35mEMOJIS / STICK :\u001b[0m \u001b[0;37m{emojis} / {stickers}\u001b[0m\n"
            f"\u001b[1;35mBOOST LEVEL    :\u001b[0m \u001b[0;37mTier {boost_level} ({boost_count} Boosts)\u001b[0m\n"
            f"\u001b[1;35mVANITY URL     :\u001b[0m \u001b[0;37m{guild.vanity_url or 'None'}\u001b[0m\n"
            "```"
        )
        embed.add_field(name="💎 GUILD ASSETS", value=asset_block, inline=False)

        if guild.features:
            features = ", ".join(f"`{f.replace('_', ' ').lower()}`" for f in guild.features[:15])
            embed.add_field(name="🛠️ ENHANCED PROTOCOLS", value=features, inline=False)

        embed.set_footer(text=f"Deep Scan Complete • Traders Union Intelligence • {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        
        await load_msg.delete()
        await ctx.send(embed=embed)

    @commands.command(name="stealsticker")
    @is_owner_check()
    @commands.guild_only()
    async def steal_sticker(self, ctx, *, name: str = None):
        if not ctx.message.reference:
            return await ctx.send("❌ You need to reply to a message containing a sticker.")

        replied_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        if not replied_msg.stickers:
            return await ctx.send("❌ The replied message has no sticker.")

        sticker = replied_msg.stickers[0]
        if not ctx.guild.me.guild_permissions.manage_expressions:
            return await ctx.send("❌ I don't have permission to manage stickers in this server.")
        
        sticker_name = name or re.sub(r'[^a-zA-Z0-9_-]', '_', sticker.name or "stolen_sticker")
        emoji_tag = getattr(sticker, "tags", "😄")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(sticker.url) as resp:
                    if resp.status != 200:
                        return await ctx.send("❌ Failed to download the sticker.")
                    sticker_bytes = await resp.read()

            ext = "png" if sticker.format == discord.StickerFormatType.png else "gif" if sticker.format == discord.StickerFormatType.apng else "webp"
            file = discord.File(io.BytesIO(sticker_bytes), filename=f"{sticker_name}.{ext}")

            await ctx.guild.create_sticker(
                name=sticker_name,
                description=f"Sticker stolen by {ctx.author}",
                emoji=emoji_tag,
                file=file,
                reason=f"Sticker stolen by {ctx.author}"
            )
            await ctx.send(f"✅ Sticker `{sticker_name}` added successfully.")
        except Exception as e:
            await ctx.send(f"❌ Unexpected error: {e}")

    @commands.command(name="rolehumans")
    @is_owner_check()
    @commands.has_permissions(manage_roles=True)
    async def giveroleall(self, ctx, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.send("⚠️ I don't have permission to assign that role.")

        count = 0
        failed = 0
        await ctx.send("⏳ Giving role, this might take a while...")

        for member in ctx.guild.members:
            if not member.bot and role not in member.roles:
                try:
                    await member.add_roles(role, reason=f"Mass role added by {ctx.author}")
                    count += 1
                except:
                    failed += 1

        await ctx.send(f"✅ Done! Role given to {count} members. ❌ Failed: {failed}")

    @commands.command(name="stealemoji", aliases=["steal"])
    @is_owner_check()
    @commands.guild_only()
    async def stealemoji(self, ctx, *, new_name: str = None):
        if not ctx.message.reference:
            return await ctx.send("❌ You must reply to a message containing a custom emoji.")

        replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        tokens = replied_message.clean_content.split()

        for token in tokens:
            match = re.match(r"<(a?):(\w+):(\d+)>", token)
            if match:
                animated = bool(match.group(1))
                original_name = match.group(2)
                emoji_id = match.group(3)
                ext = "gif" if animated else "png"
                url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"
                emoji_name = new_name if new_name else original_name

                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                emoji_bytes = await resp.read()
                                await ctx.guild.create_custom_emoji(name=emoji_name, image=emoji_bytes)
                                embed = discord.Embed(
                                    title="🟢 Emoji Stolen!",
                                    description=f"Emoji `{emoji_name}` added successfully!",
                                    color=discord.Color.green()
                                )
                                embed.set_thumbnail(url=url)
                                return await ctx.send(embed=embed)
                            else:
                                return await ctx.send("❌ Couldn't fetch the emoji.")
                except Exception as e:
                    return await ctx.send(f"❌ Error: `{e}`")

        await ctx.send("❌ No custom emoji found.")

    @commands.command()
    async def banner(self, ctx, user: discord.User = None):
        user = user or ctx.author
        user = await self.bot.fetch_user(user.id)
        if user.banner:
            embed = discord.Embed(title=f"{user}'s Banner", color=discord.Color.purple())
            embed.set_image(url=user.banner.url)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ {user.mention} does not have a banner.")

    @commands.command(aliases=['av'])
    async def avatar(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(title=f"| VISUAL INTEL | {member.name.upper()}", color=member.color)
        embed.set_image(url=member.display_avatar.url)
        embed.set_footer(text=f"Traders Union Visual Records • {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="social")
    async def social(self, ctx):
        """Deep link to Traders Union official social networks"""
        load_msg = await ctx.send("🌐 `ESTABLISHING DIGITAL HANDSHAKE...`")
        await asyncio.sleep(0.4)
        await load_msg.edit(content="🛰️ `LOCATING CRYPTO-SOCIAL NODES...`")
        await asyncio.sleep(0.4)
        await load_msg.edit(content="💎 `DECRYPTING BRAND ASSETS...`")
        await asyncio.sleep(0.4)
        await load_msg.edit(content="⚡ `SYNCHRONIZING GLOBAL FEEDS...`")
        
        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        grid = (
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃        TRADERS UNION GLOBAL FEED        ┃\n"
            "┣━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┫\n"
            "┃ \u001b[1;36mDISCORD\u001b[0m          ┃ \u001b[0;37m/tradersunionglobal\u001b[0m ┃\n"
            "┣━━━━━━━━━━━━━━━━━━╋━━━━━━━━━━━━━━━━━━━━━━┫\n"
            "┃ \u001b[1;35mINSTAGRAM\u001b[0m        ┃ \u001b[0;37m@tradersunionglobal\u001b[0m  ┃\n"
            "┣━━━━━━━━━━━━━━━━━━╋━━━━━━━━━━━━━━━━━━━━━━┫\n"
            "┃ \u001b[1;34mTWITTER / X\u001b[0m      ┃ \u001b[0;37m@tradersunion_ \u001b[0m      ┃\n"
            "┗━━━━━━━━━━━━━━━━━━┻━━━━━━━━━━━━━━━━━━━━━━┛"
        )
        embed = discord.Embed(title="💎 TRADERS UNION | CONNECTIVITY INTERFACE", description=f"```ansi\n{grid}\n```\n📡 **ACCESS AUTHORIZED**\nJoin our elite circle for real-time market pulse.\n\n🔗 **DIRECT GATEWAY LINKS:**\n• [» Official Discord](https://discord.gg/tradersunionglobal)\n• [» Instagram Feed](https://www.instagram.com/tradersunionglobal/)\n• [» Twitter/X Pulse](https://x.com/tradersunion_)", color=0x2b2d31)
        embed.set_author(name="TRADERS UNION GLOBAL", icon_url=logo)
        embed.set_thumbnail(url=logo)
        embed.set_footer(text="Institutional Connectivity Protocol v4.0 • Level 5 Encryption", icon_url=logo)
        await load_msg.delete()
        await ctx.send(embed=embed)

    @commands.command()
    async def lotsize(self, ctx, account_balance: float, risk_percent: float, stop_loss_pips: float, instrument: str):
        """Quantum Lot Size Calculator"""
        try:
            instrument = instrument.lower()
            logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
            if instrument in ["gold", "xauusd"]: pip_value = 10
            else: return await ctx.send("❌ `INSTRUMENT UNKNOWN. CURRENTLY GOLD ONLY.`")
            risk_amount = account_balance * (risk_percent / 100)
            lot_size = round(risk_amount / (stop_loss_pips * pip_value), 2)
            embed = discord.Embed(title="📊 QUANTUM LOT CALCULATOR", color=0x2b2d31)
            embed.set_author(name="TRADERS UNION ANALYTICS", icon_url=logo)
            stats = ("```ansi\n"f"\u001b[1;36mBALANCE  :\u001b[0m \u001b[0;37m${account_balance}\u001b[0m\n"f"\u001b[1;36mRISK AMT :\u001b[0m \u001b[0;37m${risk_amount} ({risk_percent}%)\u001b[0m\n"f"\u001b[1;36mSTOPLOSS :\u001b[0m \u001b[0;37m{stop_loss_pips} Pips\u001b[0m\n"f"---------------------------\n"f"\u001b[1;32mREC. LOT :\u001b[0m \u001b[1;37m{lot_size} LOTS\u001b[0m\n""```")
            embed.description = stats
            embed.set_footer(text="TRADERS UNION • Institutional Risk Management")
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ `CALCULATION ERROR: {e}`")

async def setup(bot):
    await bot.add_cog(Utility(bot))
