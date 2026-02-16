import discord
from discord.ext import commands
import json
from datetime import datetime
import pytz
import asyncio
from .utils import is_owner_check
import db

# File paths
POINTS_FILE = "union_points.json"
LOGS_FILE = "union_logs.json"
MANAGERS_FILE = "union_managers.json"
LB_CONFIG_FILE = "leaderboard_config.json"
LOG_CHANNEL_FILE = "log_channel.json"

def get_points(guild_id):
    """Load points data"""
    return db.get_setting(POINTS_FILE, int(guild_id), {})

def save_points(guild_id, data):
    """Save points data"""
    db.set_setting(POINTS_FILE, int(guild_id), data)

def get_logs(guild_id):
    """Load logs data"""
    return db.get_setting(LOGS_FILE, int(guild_id), [])

def save_logs(guild_id, data):
    """Save logs data"""
    db.set_setting(LOGS_FILE, int(guild_id), data)

def get_managers(guild_id):
    """Load manager list"""
    return db.get_setting(MANAGERS_FILE, int(guild_id), [])

def save_managers(guild_id, data):
    """Save manager list"""
    db.set_setting(MANAGERS_FILE, int(guild_id), data)

def get_lb_config(guild_id):
    """Load leaderboard config"""
    return db.get_setting(LB_CONFIG_FILE, int(guild_id), {})

def save_lb_config(guild_id, data):
    """Save leaderboard config"""
    db.set_setting(LB_CONFIG_FILE, int(guild_id), data)

def get_log_channel(guild_id):
    """Get log channel ID"""
    config = db.get_setting(LOG_CHANNEL_FILE, int(guild_id), {})
    return config.get("channel_id")

def set_log_channel(guild_id, channel_id):
    """Set log channel ID"""
    db.set_setting(LOG_CHANNEL_FILE, int(guild_id), {"channel_id": channel_id})

def log_action(guild_id, manager_id, manager_name, action, target_id, target_name, points, reason):
    """Log manager action"""
    logs = get_logs(guild_id)
    pkt_time = datetime.now(pytz.timezone('Asia/Karachi'))
    
    log_entry = {
        "timestamp": pkt_time.isoformat(),
        "manager_id": manager_id,
        "manager_name": manager_name,
        "action": action,
        "target_id": target_id,
        "target_name": target_name,
        "points": points,
        "reason": reason
    }
    
    logs.append(log_entry)
    save_logs(guild_id, logs)
    return log_entry

async def send_log_to_channel(bot, guild_id, log_entry):
    """Send log entry to configured channel"""
    log_channel_id = get_log_channel(guild_id)
    
    if not log_channel_id:
        return
    
    try:
        channel = bot.get_channel(int(log_channel_id))
        if not channel:
            return
        
        action = log_entry["action"]
        timestamp = datetime.fromisoformat(log_entry["timestamp"])
        
        # Action colors and emojis
        action_data = {
            "ADD": {"color": 0x2ecc71, "emoji": "✅", "title": "POINTS ADDED"},
            "REMOVE": {"color": 0xe74c3c, "emoji": "❌", "title": "POINTS REMOVED"},
            "RESET": {"color": 0x9b59b6, "emoji": "🔄", "title": "POINTS RESET"}
        }
        
        action_info = action_data.get(action, {"color": 0x3498db, "emoji": "•", "title": action})
        
        embed = discord.Embed(
            title=f"{action_info['emoji']} UNION LOG | {action_info['title']}",
            color=action_info["color"],
            timestamp=timestamp
        )
        
        embed.add_field(name="👤 Manager", value=f"`{log_entry['manager_name']}`", inline=True)
        embed.add_field(name="🎯 Target", value=f"`{log_entry['target_name']}`", inline=True)
        embed.add_field(name="📊 Points", value=f"`{log_entry['points']}`", inline=True)
        embed.add_field(name="📋 Reason", value=log_entry['reason'], inline=False)
        
        embed.set_footer(text=f"Action logged at {timestamp.strftime('%I:%M %p PKT')}")
        
        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        embed.set_thumbnail(url=logo)
        
        await channel.send(embed=embed)
    except Exception as e:
        print(f"Error sending log to channel: {e}")

def is_manager_or_owner():
    """Check if user is manager or owner"""
    async def predicate(ctx):
        managers = get_managers(ctx.guild.id)
        return ctx.author.id in managers or await ctx.bot.is_owner(ctx.author)
    return commands.check(predicate)

async def resolve_username(bot, guild, user_id, fallback_name="Unknown User"):
    """Resolve Discord username for leaderboard display."""
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        return fallback_name

    member = guild.get_member(user_id_int) if guild else None
    if member:
        return member.name

    user = bot.get_user(user_id_int)
    if user:
        return user.name

    try:
        user = await bot.fetch_user(user_id_int)
        return user.name
    except Exception:
        return fallback_name

async def update_leaderboard_message(bot, guild_id):
    """Update the pinned leaderboard message"""
    lb_config = get_lb_config(guild_id)
    
    if not lb_config.get("channel_id") or not lb_config.get("message_id"):
        return
    
    try:
        channel = bot.get_channel(int(lb_config["channel_id"]))
        if not channel:
            return
        
        message = await channel.fetch_message(int(lb_config["message_id"]))
        if not message:
            return
        
        # Create updated leaderboard embed
        points_data = get_points(guild_id)
        points_data = {
            user_id: data
            for user_id, data in points_data.items()
            if data.get("points", 0) > 0
        }
        
        if not points_data:
            embed = discord.Embed(
                title="💎 TRADERS UNION | LIVE LEADERBOARD",
                description="```ansi\n\u001b[1;33mNO DATA AVAILABLE\u001b[0m\n```",
                color=0x2b2d31
            )
        else:
            sorted_users = sorted(points_data.items(), key=lambda x: x[1]["points"], reverse=True)
            
            embed = discord.Embed(
                title="💎 TRADERS UNION | LIVE LEADERBOARD",
                description="```ansi\n\u001b[1;36m━━━━━━━━━━━━━━━━━━━━━━━━━━━━\u001b[0m\n```",
                color=0x2b2d31
            )
            
            logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
            embed.set_author(name="TRADERS UNION RANKINGS • REAL-TIME", icon_url=logo)
            
            # Top 10
            leaderboard_text = ""
            for idx, (user_id, data) in enumerate(sorted_users[:10], 1):
                medal = ""
                if idx == 1:
                    medal = "🥇"
                elif idx == 2:
                    medal = "🥈"
                elif idx == 3:
                    medal = "🥉"
                else:
                    medal = f"`#{idx}`"
                
                points = data["points"]
                fallback_name = data.get("username") or data.get("name", "Unknown User")
                name = await resolve_username(bot, channel.guild, user_id, fallback_name)
                
                leaderboard_text += f"{medal} **{name}**\n└ Points: `{points:,}`\n\n"
            
            embed.description += leaderboard_text
            
            # Last updated
            pkt_time = datetime.now(pytz.timezone('Asia/Karachi'))
            embed.set_footer(text=f"Last Updated: {pkt_time.strftime('%b %d, %I:%M %p PKT')} • Auto-Refresh")
            embed.set_thumbnail(url=logo)
        
        await message.edit(embed=embed)
    except Exception as e:
        print(f"Error updating leaderboard: {e}")

class UnionPoints(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="union", invoke_without_command=True)
    async def union(self, ctx):
        """Union points system"""
        return

    @union.command(name="add")
    @is_owner_check()
    async def add_points(self, ctx, member: discord.Member, points: int, *, reason: str):
        """Add points to a user (Manager/Owner only)"""
        if points <= 0:
            return await ctx.send("❌ Points must be positive!")
        
        # Load points
        points_data = get_points(ctx.guild.id)
        user_id = str(member.id)
        
        # Update points
        if user_id not in points_data:
            points_data[user_id] = {
                "name": member.name,
                "username": member.name,
                "points": 0,
                "last_updated": None
            }
        
        old_points = points_data[user_id]["points"]
        points_data[user_id]["points"] += points
        points_data[user_id]["name"] = member.name
        points_data[user_id]["username"] = member.name
        points_data[user_id]["last_updated"] = datetime.now(pytz.timezone('Asia/Karachi')).isoformat()
        
        save_points(ctx.guild.id, points_data)
        
        # Log action
        log_entry = log_action(
            ctx.guild.id,
            ctx.author.id,
            ctx.author.display_name,
            "ADD",
            member.id,
            member.display_name,
            points,
            reason
        )
        
        # Send log to channel
        await send_log_to_channel(self.bot, ctx.guild.id, log_entry)
        
        # Send confirmation
        embed = discord.Embed(
            title="✅ POINTS ADDED",
            description=f"**{member.mention}** received **+{points}** points",
            color=0x2ecc71
        )
        embed.add_field(name="📊 Previous", value=f"`{old_points}`", inline=True)
        embed.add_field(name="📈 New Total", value=f"`{points_data[user_id]['points']}`", inline=True)
        embed.add_field(name="📝 Reason", value=reason, inline=False)
        embed.set_footer(text=f"Action by {ctx.author.display_name} • {datetime.now(pytz.timezone('Asia/Karachi')).strftime('%I:%M %p PKT')}")
        
        await ctx.send(embed=embed)
        
        # Update live leaderboard
        await update_leaderboard_message(self.bot, ctx.guild.id)

    @union.command(name="remove")
    @is_owner_check()
    async def remove_points(self, ctx, member: discord.Member, points: int, *, reason: str):
        """Remove points from a user (Manager/Owner only)"""
        if points <= 0:
            return await ctx.send("❌ Points must be positive!")
        
        # Load points
        points_data = get_points(ctx.guild.id)
        user_id = str(member.id)
        
        if user_id not in points_data:
            return await ctx.send("❌ This user has no points!")
        
        old_points = points_data[user_id]["points"]
        points_data[user_id]["points"] = max(0, old_points - points)
        points_data[user_id]["name"] = member.name
        points_data[user_id]["username"] = member.name
        points_data[user_id]["last_updated"] = datetime.now(pytz.timezone('Asia/Karachi')).isoformat()
        
        save_points(ctx.guild.id, points_data)
        
        # Log action
        log_entry = log_action(
            ctx.guild.id,
            ctx.author.id,
            ctx.author.display_name,
            "REMOVE",
            member.id,
            member.display_name,
            points,
            reason
        )
        
        # Send log to channel
        await send_log_to_channel(self.bot, ctx.guild.id, log_entry)
        
        # Send confirmation
        embed = discord.Embed(
            title="⚠️ POINTS REMOVED",
            description=f"**{member.mention}** lost **-{points}** points",
            color=0xe74c3c
        )
        embed.add_field(name="📊 Previous", value=f"`{old_points}`", inline=True)
        embed.add_field(name="📉 New Total", value=f"`{points_data[user_id]['points']}`", inline=True)
        embed.add_field(name="📋 Reason", value=reason, inline=False)
        embed.set_footer(text=f"Action by {ctx.author.display_name} • {datetime.now(pytz.timezone('Asia/Karachi')).strftime('%I:%M %p PKT')}")
        
        await ctx.send(embed=embed)
        
        # Update live leaderboard
        await update_leaderboard_message(self.bot, ctx.guild.id)

    @union.group(name="reset", invoke_without_command=True)
    @is_owner_check()
    async def reset_points(self, ctx, member: discord.Member = None, *, reason: str = None):
        """Reset a user's points to 0. Use `union reset all <reason>` for everyone."""
        if member is None or reason is None:
            return await ctx.send("Usage: `union reset @member <reason>` or `union reset all <reason>`")

        points_data = get_points(ctx.guild.id)
        user_id = str(member.id)

        if user_id not in points_data:
            return await ctx.send("❌ This user has no points!")

        old_points = points_data[user_id]["points"]
        points_data[user_id]["points"] = 0
        points_data[user_id]["name"] = member.name
        points_data[user_id]["username"] = member.name
        points_data[user_id]["last_updated"] = datetime.now(pytz.timezone('Asia/Karachi')).isoformat()

        save_points(ctx.guild.id, points_data)

        log_entry = log_action(
            ctx.guild.id,
            ctx.author.id,
            ctx.author.display_name,
            "RESET",
            member.id,
            member.display_name,
            old_points,
            reason
        )

        await send_log_to_channel(self.bot, ctx.guild.id, log_entry)

        embed = discord.Embed(
            title="🔄 POINTS RESET",
            description=f"**{member.mention}**'s points have been reset",
            color=0x9b59b6
        )
        embed.add_field(name="📊 Previous", value=f"`{old_points}`", inline=True)
        embed.add_field(name="📉 New Total", value="`0`", inline=True)
        embed.add_field(name="📋 Reason", value=reason, inline=False)
        embed.set_footer(text=f"Action by {ctx.author.display_name} • {datetime.now(pytz.timezone('Asia/Karachi')).strftime('%I:%M %p PKT')}")

        await ctx.send(embed=embed)
        await update_leaderboard_message(self.bot, ctx.guild.id)

    @reset_points.command(name="all")
    @is_owner_check()
    async def reset_all_points(self, ctx, *, reason: str):
        """Reset all tracked users to 0 points"""
        points_data = get_points(ctx.guild.id)
        if not points_data:
            return await ctx.send("❌ No points data to reset.")

        now_iso = datetime.now(pytz.timezone('Asia/Karachi')).isoformat()
        reset_count = 0

        for user_id, user_data in points_data.items():
            old_points = user_data.get("points", 0)
            user_data["points"] = 0
            user_data["last_updated"] = now_iso
            reset_count += 1

            log_entry = log_action(
                ctx.guild.id,
                ctx.author.id,
                ctx.author.display_name,
                "RESET",
                int(user_id),
                user_data.get("name", f"User {user_id}"),
                old_points,
                reason
            )
            await send_log_to_channel(self.bot, ctx.guild.id, log_entry)

        save_points(ctx.guild.id, points_data)
        await update_leaderboard_message(self.bot, ctx.guild.id)

        embed = discord.Embed(
            title="🔄 ALL UNION POINTS RESET",
            description=f"Reset **{reset_count}** users to `0` points.",
            color=0x9b59b6
        )
        embed.add_field(name="📋 Reason", value=reason, inline=False)
        embed.set_footer(text=f"Action by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @union.command(name="leaderboard", aliases=["lb", "top"])
    @is_owner_check()
    async def leaderboard(self, ctx):
        """Show the Union Points leaderboard"""
        points_data = get_points(ctx.guild.id)
        points_data = {
            user_id: data
            for user_id, data in points_data.items()
            if data.get("points", 0) > 0
        }
        
        if not points_data:
            return await ctx.send("📊 No points data yet!")
        
        # Sort by points
        sorted_users = sorted(points_data.items(), key=lambda x: x[1]["points"], reverse=True)
        
        # Create leaderboard
        embed = discord.Embed(
            title="💎 TRADERS UNION | LEADERBOARD",
            description="```ansi\n\u001b[1;36m━━━━━━━━━━━━━━━━━━━━━━━━━━━━\u001b[0m\n```",
            color=0x2b2d31
        )
        
        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        embed.set_author(name="TRADERS UNION RANKINGS", icon_url=logo)
        
        # Top 10
        leaderboard_text = ""
        for idx, (user_id, data) in enumerate(sorted_users[:10], 1):
            # Medal emojis
            medal = ""
            if idx == 1:
                medal = "🥇"
            elif idx == 2:
                medal = "🥈"
            elif idx == 3:
                medal = "🥉"
            else:
                medal = f"`#{idx}`"
            
            points = data["points"]
            fallback_name = data.get("username") or data.get("name", "Unknown User")
            name = await resolve_username(self.bot, ctx.guild, user_id, fallback_name)
            
            leaderboard_text += f"{medal} **{name}**\n└ Points: `{points:,}`\n\n"
        
        embed.description += leaderboard_text
        
        embed.set_footer(text="TRADERS UNION • Real-time Rankings")
        embed.set_thumbnail(url=logo)
        
        await ctx.send(embed=embed)

    @union.command(name="logs")
    @is_owner_check()
    async def show_logs(self, ctx, limit: int = 10):
        """Show recent manager action logs (Manager/Owner only)"""
        logs = get_logs(ctx.guild.id)
        
        if not logs:
            return await ctx.send("📋 No logs available!")
        
        # Get recent logs
        recent_logs = logs[-limit:][::-1]  # Last N logs, reversed
        
        embed = discord.Embed(
            title="📋 UNION MANAGER LOGS",
            description="```ansi\n\u001b[1;36mRECENT ACTIONS • FULL AUDIT TRAIL\u001b[0m\n```",
            color=0x3498db
        )
        
        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        embed.set_author(name="AUDIT SYSTEM", icon_url=logo)
        
        logs_text = ""
        for log in recent_logs:
            action = log["action"]
            action_emoji = {
                "ADD": "✅",
                "REMOVE": "❌",
                "RESET": "🔄"
            }.get(action, "•")
            
            timestamp = datetime.fromisoformat(log["timestamp"])
            time_str = timestamp.strftime("%b %d, %I:%M %p")
            
            logs_text += (
                f"{action_emoji} **{action}** by `{log['manager_name']}`\n"
                f"└ Target: `{log['target_name']}` | Points: `{log['points']}` | {time_str}\n"
                f"└ Reason: {log['reason']}\n\n"
            )
        
        embed.description += logs_text
        embed.set_footer(text=f"Showing last {len(recent_logs)} actions • TRADERS UNION")
        
        await ctx.send(embed=embed)

    @union.command(name="addmanager", aliases=["am"])
    @is_owner_check()
    async def add_manager(self, ctx, member: discord.Member):
        """Add a union points manager (Owner only)"""
        managers = get_managers(ctx.guild.id)
        
        if member.id in managers:
            return await ctx.send(f"⚠️ **{member.display_name}** is already a manager!")
        
        managers.append(member.id)
        save_managers(ctx.guild.id, managers)
        
        embed = discord.Embed(
            title="✅ MANAGER ADDED",
            description=f"**{member.mention}** is now a Union Points Manager",
            color=0x2ecc71
        )
        embed.set_footer(text=f"Total Managers: {len(managers)}")
        
        await ctx.send(embed=embed)

    @union.command(name="removemanager", aliases=["rm"])
    @is_owner_check()
    async def remove_manager(self, ctx, member: discord.Member):
        """Remove a union points manager (Owner only)"""
        managers = get_managers(ctx.guild.id)
        
        if member.id not in managers:
            return await ctx.send(f"⚠️ **{member.display_name}** is not a manager!")
        
        managers.remove(member.id)
        save_managers(ctx.guild.id, managers)
        
        embed = discord.Embed(
            title="❌ MANAGER REMOVED",
            description=f"**{member.mention}** is no longer a Union Points Manager",
            color=0xe74c3c
        )
        embed.set_footer(text=f"Total Managers: {len(managers)}")
        
        await ctx.send(embed=embed)

    @union.command(name="managers")
    @is_owner_check()
    async def list_managers(self, ctx):
        """List all union points managers"""
        managers = get_managers(ctx.guild.id)
        
        if not managers:
            return await ctx.send("📋 No managers assigned yet!")
        
        embed = discord.Embed(
            title="👥 UNION MANAGERS",
            description="",
            color=0x9b59b6
        )
        
        manager_text = ""
        for manager_id in managers:
            member = ctx.guild.get_member(manager_id)
            if member:
                manager_text += f"• **{member.display_name}** (`{member.id}`)\n"
            else:
                manager_text += f"• Unknown User (`{manager_id}`)\n"
        
        embed.description = manager_text
        embed.set_footer(text=f"Total: {len(managers)} managers")
        
        await ctx.send(embed=embed)

    @union.command(name="setlog")
    @is_owner_check()
    async def set_log_channel_cmd(self, ctx, channel: discord.TextChannel):
        """Setup auto-logging channel (Owner only)"""
        set_log_channel(ctx.guild.id, channel.id)
        
        embed = discord.Embed(
            title="✅ LOG CHANNEL CONFIGURED",
            description=(
                "```ansi\n"
                "\u001b[1;32mSTATUS  : ACTIVE\u001b[0m\n"
                f"\u001b[1;36mCHANNEL : {channel.name.upper()}\u001b[0m\n"
                "\u001b[1;33mMODE    : AUTO-LOG ON ACTIONS\u001b[0m\n"
                "```\n"
                f"All union point actions will be logged to {channel.mention}.\n"
                f"Logs will be sent automatically for ADD, REMOVE, and RESET actions."
            ),
            color=0x2ecc71
        )
        embed.set_footer(text="TRADERS UNION • Audit System Active")
        
        await ctx.send(embed=embed)

    @union.command(name="setlb")
    @is_owner_check()
    async def set_leaderboard(self, ctx, channel: discord.TextChannel):
        """Setup auto-updating leaderboard in a channel (Owner only)"""
        load_msg = await ctx.send("🔄 `INITIALIZING LIVE LEADERBOARD SYSTEM...`")
        await asyncio.sleep(0.5)
        
        # Create initial leaderboard embed
        points_data = get_points(ctx.guild.id)
        points_data = {
            user_id: data
            for user_id, data in points_data.items()
            if data.get("points", 0) > 0
        }
        
        if not points_data:
            embed = discord.Embed(
                title="💎 TRADERS UNION | LIVE LEADERBOARD",
                description="```ansi\n\u001b[1;33mNO DATA AVAILABLE\u001b[0m\n```",
                color=0x2b2d31
            )
        else:
            sorted_users = sorted(points_data.items(), key=lambda x: x[1]["points"], reverse=True)
            
            embed = discord.Embed(
                title="💎 TRADERS UNION | LIVE LEADERBOARD",
                description="```ansi\n\u001b[1;36m━━━━━━━━━━━━━━━━━━━━━━━━━━━━\u001b[0m\n```",
                color=0x2b2d31
            )
            
            logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
            embed.set_author(name="TRADERS UNION RANKINGS • REAL-TIME", icon_url=logo)
            
            # Top 10
            leaderboard_text = ""
            for idx, (user_id, data) in enumerate(sorted_users[:10], 1):
                medal = ""
                if idx == 1:
                    medal = "🥇"
                elif idx == 2:
                    medal = "🥈"
                elif idx == 3:
                    medal = "🥉"
                else:
                    medal = f"`#{idx}`"
                
                points = data["points"]
                fallback_name = data.get("username") or data.get("name", "Unknown User")
                name = await resolve_username(self.bot, ctx.guild, user_id, fallback_name)
                
                leaderboard_text += f"{medal} **{name}**\n└ Points: `{points:,}`\n\n"
            
            embed.description += leaderboard_text
            
            # Last updated
            pkt_time = datetime.now(pytz.timezone('Asia/Karachi'))
            embed.set_footer(text=f"Last Updated: {pkt_time.strftime('%b %d, %I:%M %p PKT')} • Auto-Refresh")
            embed.set_thumbnail(url=logo)
        
        await load_msg.edit(content="📡 `DEPLOYING LEADERBOARD TO CHANNEL...`")
        await asyncio.sleep(0.5)
        
        # Send leaderboard message
        lb_message = await channel.send(embed=embed)
        
        # Pin it
        try:
            await lb_message.pin()
        except:
            pass
        
        # Save config
        lb_config = {
            "channel_id": channel.id,
            "message_id": lb_message.id
        }
        save_lb_config(ctx.guild.id, lb_config)
        
        await load_msg.edit(content="✅ `LIVE LEADERBOARD ACTIVATED!`")
        await asyncio.sleep(1)
        
        # Confirmation embed
        conf_embed = discord.Embed(
            title="✅ LEADERBOARD SYSTEM ONLINE",
            description=(
                "```ansi\n"
                "\u001b[1;32mSTATUS  : OPERATIONAL\u001b[0m\n"
                f"\u001b[1;36mCHANNEL : {channel.name.upper()}\u001b[0m\n"
                "\u001b[1;33mMODE    : REAL-TIME AUTO-UPDATE\u001b[0m\n"
                "```\n"
                f"Leaderboard will automatically update on every point change.\n"
                f"Message ID: `{lb_message.id}`"
            ),
            color=0x2ecc71
        )
        conf_embed.set_footer(text="TRADERS UNION • Live Ranking System")
        
        await load_msg.delete()
        await ctx.send(embed=conf_embed)

    @union.command(name="check", aliases=["points", "balance"])
    async def check_points(self, ctx, member: discord.Member = None):
        """Check your or someone else's points"""
        if member is None:
            member = ctx.author
        
        points_data = get_points(ctx.guild.id)
        user_id = str(member.id)
        
        if user_id not in points_data:
            return await ctx.send(f"📊 **{member.display_name}** has no points yet!")
        
        data = points_data[user_id]
        points = data["points"]
        
        # Get rank
        sorted_users = sorted(points_data.items(), key=lambda x: x[1]["points"], reverse=True)
        rank = next((idx for idx, (uid, _) in enumerate(sorted_users, 1) if uid == user_id), None)
        
        embed = discord.Embed(
            title=f"💰 {member.display_name}'s Points",
            color=0xf39c12
        )
        embed.add_field(name="Points", value=f"`{points:,}`", inline=True)
        embed.add_field(name="Rank", value=f"`#{rank}`", inline=True)
        
        if data.get("last_updated"):
            last_updated = datetime.fromisoformat(data["last_updated"])
            embed.set_footer(text=f"Last updated: {last_updated.strftime('%b %d, %I:%M %p PKT')}")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(UnionPoints(bot))
