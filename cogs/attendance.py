import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, time
import pytz
from typing import Optional
import db

ATTENDANCE_FILE = "attendance_data.json"
ATTENDANCE_CONFIG_FILE = "attendance_config.json"
ATTENDANCE_BATCHES_FILE = "attendance_batches.json"
ATTENDANCE_DATA_LOCK = asyncio.Lock()

def load_attendance_data(guild_id: str):
    rows = db.execute(
        "SELECT role_id, date_key, user_id, status, time_label, username FROM attendance_records WHERE guild_id = %s",
        (int(guild_id),),
        fetchall=True
    ) or []
    data = {}
    for r in rows:
        role_id = str(r["role_id"])
        date_key = r["date_key"]
        user_id = str(r["user_id"])
        data.setdefault(role_id, {}).setdefault(date_key, {})[user_id] = {
            "status": r["status"],
            "time": r["time_label"],
            "username": r["username"]
        }
    return data

def save_attendance_data(guild_id: str, data: dict):
    gid = int(guild_id)
    db.execute("DELETE FROM attendance_records WHERE guild_id = %s", (gid,))
    for role_id, dates in (data or {}).items():
        for date_key, users in (dates or {}).items():
            for user_id, record in (users or {}).items():
                db.execute(
                    """
                    INSERT INTO attendance_records
                    (guild_id, role_id, date_key, user_id, status, time_label, username)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        gid, int(role_id), str(date_key), int(user_id),
                        str(record.get("status", "present")),
                        record.get("time"),
                        record.get("username")
                    )
                )

def load_attendance_config(guild_id: str):
    row = db.execute(
        "SELECT channel_id, log_channel_id, attendance_message_id, reminder_channel_id, last_report_date FROM attendance_config WHERE guild_id = %s",
        (int(guild_id),),
        fetchone=True
    )
    if not row:
        return {}
    return {
        "channel": str(row["channel_id"]) if row["channel_id"] else None,
        "log_channel": str(row["log_channel_id"]) if row["log_channel_id"] else None,
        "attendance_message": str(row["attendance_message_id"]) if row["attendance_message_id"] else None,
        "reminder_channel": str(row["reminder_channel_id"]) if row.get("reminder_channel_id") else None,
        "last_report_date": row.get("last_report_date")
    }

def save_attendance_config(guild_id: str, data: dict):
    db.execute(
        """
        INSERT INTO attendance_config (guild_id, channel_id, log_channel_id, attendance_message_id, reminder_channel_id, last_report_date)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (guild_id) DO UPDATE SET
          channel_id = EXCLUDED.channel_id,
          log_channel_id = EXCLUDED.log_channel_id,
          attendance_message_id = EXCLUDED.attendance_message_id,
          reminder_channel_id = EXCLUDED.reminder_channel_id,
          last_report_date = EXCLUDED.last_report_date
        """,
        (
            int(guild_id),
            int(data["channel"]) if data.get("channel") else None,
            int(data["log_channel"]) if data.get("log_channel") else None,
            int(data["attendance_message"]) if data.get("attendance_message") else None,
            int(data["reminder_channel"]) if data.get("reminder_channel") else None,
            str(data["last_report_date"]) if data.get("last_report_date") else None
        )
    )

def load_attendance_batches(guild_id: str):
    rows = db.execute(
        "SELECT role_id, batch_name FROM attendance_batches WHERE guild_id = %s",
        (int(guild_id),),
        fetchall=True
    ) or []
    batches = [str(r["role_id"]) for r in rows]
    batch_names = {str(r["role_id"]): r["batch_name"] for r in rows}
    return {"batches": batches, "batch_names": batch_names}

def save_attendance_batches(guild_id: str, data: dict):
    gid = int(guild_id)
    db.execute("DELETE FROM attendance_batches WHERE guild_id = %s", (gid,))
    for role_id in (data.get("batches") or []):
        name = (data.get("batch_names") or {}).get(role_id, "Unknown Batch")
        db.execute(
            "INSERT INTO attendance_batches (guild_id, role_id, batch_name) VALUES (%s, %s, %s)",
            (gid, int(role_id), str(name))
        )


def get_user_day_status(day_data: dict, user_id: str):
    """Return normalized status/time for a user from attendance day data."""
    record = day_data.get(user_id)
    if not record:
        return "absent", None

    # Backward compatibility: older records may not have status.
    if not isinstance(record, dict):
        return "present", None

    status = str(record.get("status", "present")).lower()
    if status not in {"present", "absent"}:
        status = "present"
    return status, record.get("time")


class AttendanceButton(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="✅ Mark Attendance", style=discord.ButtonStyle.green, custom_id="mark_attendance_universal")
    async def mark_attendance(self, interaction: discord.Interaction, button: discord.ui.Button):
        tz = pytz.timezone("Asia/Karachi")
        now = datetime.now(tz)
        guild_id = str(interaction.guild.id)
        
        # Check if it's weekend (Saturday=5, Sunday=6)
        if now.weekday() in [5, 6]:
            day_name = "Saturday" if now.weekday() == 5 else "Sunday"
            embed = discord.Embed(
                title="📅 NO SESSION TODAY",
                description=(
                    "```ansi\n"
                    f"\u001b[1;31mERROR :\u001b[0m \u001b[0;37mNo sessions on {day_name}\u001b[0m\n"
                    "\u001b[1;33mINFO  :\u001b[0m \u001b[0;37mAttendance opens Monday-Friday\u001b[0m\n"
                    "```"
                ),
                color=0xe74c3c
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Check time (4PM - 9PM)
        if not (16 <= now.hour < 21):  # 4PM (16:00) to 9PM (21:00)
            embed = discord.Embed(
                title="⏰ ATTENDANCE CLOSED",
                description=(
                    "```ansi\n"
                    "\u001b[1;31mERROR :\u001b[0m \u001b[0;37mOutside attendance hours\u001b[0m\n"
                    "\u001b[1;33mWINDOW:\u001b[0m \u001b[0;37m4:00 PM - 9:00 PM\u001b[0m\n"
                    "```"
                ),
                color=0xe74c3c
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Get config and find user's batch
        config = load_attendance_config(guild_id)
        batches_data = load_attendance_batches(guild_id)
        batches = batches_data.get("batches", [])
        batch_names = batches_data.get("batch_names", {})
        
        # Find which batch role the user has
        user_batch_role_id = None
        user_batch_name = None
        user_roles_ids = [str(r.id) for r in interaction.user.roles]
        
        for role_id in batches:
            if role_id in user_roles_ids:
                user_batch_role_id = role_id
                user_batch_name = batch_names.get(role_id, "Unknown Batch")
                break
        
        if not user_batch_role_id:
            embed = discord.Embed(
                title="❌ ACCESS DENIED",
                description=(
                    "```ansi\n"
                    "\u001b[1;31mERROR :\u001b[0m \u001b[0;37mYou are not part of any batch\u001b[0m\n"
                    "```"
                ),
                color=0xe74c3c
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        today = now.strftime("%d/%m/%y")
        user_id = str(interaction.user.id)
        async with ATTENDANCE_DATA_LOCK:
            attendance_data = load_attendance_data(guild_id)
            if not isinstance(attendance_data, dict):
                attendance_data = {}
            if user_batch_role_id not in attendance_data:
                attendance_data[user_batch_role_id] = {}
            if today not in attendance_data[user_batch_role_id]:
                attendance_data[user_batch_role_id][today] = {}

            day_data = attendance_data[user_batch_role_id][today]
            current_status, current_time = get_user_day_status(day_data, user_id)

            # Students can mark only once per day (cannot switch present/absent later).
            if user_id in day_data:
                status_label = "PRESENT" if current_status == "present" else "ABSENT"
                emoji = "✅" if current_status == "present" else "❌"
                embed = discord.Embed(
                    title="📋 ALREADY MARKED",
                    description=(
                        "```ansi\n"
                        "\u001b[1;33mINFO  :\u001b[0m \u001b[0;37mYou already marked attendance today\u001b[0m\n"
                        f"\u001b[1;33mBATCH :\u001b[0m \u001b[0;37m{user_batch_name}\u001b[0m\n"
                        f"\u001b[1;33mDATE  :\u001b[0m \u001b[0;37m{today}\u001b[0m\n"
                        f"\u001b[1;33mSTATUS:\u001b[0m \u001b[0;37m{emoji} {status_label}\u001b[0m\n"
                        f"\u001b[1;33mTIME  :\u001b[0m \u001b[0;37m{current_time or 'N/A'}\u001b[0m\n"
                        "\u001b[1;31mNOTE  :\u001b[0m \u001b[0;37mStatus cannot be changed by students\u001b[0m\n"
                        "```"
                    ),
                    color=0xf39c12
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            # Save attendance status
            attendance_data[user_batch_role_id][today][user_id] = {
                "status": "present",
                "time": now.strftime("%I:%M %p"),
                "username": interaction.user.name
            }
            save_attendance_data(guild_id, attendance_data)
        
        # Send log to attendance log channel
        log_channel_id = config.get("log_channel")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(int(log_channel_id))
            if log_channel:
                log_embed = discord.Embed(
                    title="📋 ATTENDANCE LOG",
                    description=(
                        f"**User:** {interaction.user.name} (`{interaction.user.id}`)\n"
                        f"**Batch:** {user_batch_name}\n"
                        f"**Status:** ✅ PRESENT\n"
                        f"**Date:** {today}\n"
                        f"**Time:** {now.strftime('%I:%M %p')}"
                    ),
                    color=0x2ecc71
                )
                log_embed.set_thumbnail(url=interaction.user.display_avatar.url)
                log_embed.set_footer(text="Trader Union Globale • Attendance Log")
                log_embed.timestamp = now
                await log_channel.send(embed=log_embed)

        embed = discord.Embed(
            title="✅ ATTENDANCE MARKED",
            description=(
                "```ansi\n"
                "\u001b[1;32mSTATUS :\u001b[0m \u001b[0;37mPRESENT\u001b[0m\n"
                f"\u001b[1;32mDATE   :\u001b[0m \u001b[0;37m{today}\u001b[0m\n"
                f"\u001b[1;32mTIME   :\u001b[0m \u001b[0;37m{now.strftime('%I:%M %p')}\u001b[0m\n"
                f"\u001b[1;32mBATCH  :\u001b[0m \u001b[0;37m{user_batch_name}\u001b[0m\n"
                "```"
            ),
            color=0x2ecc71
        )
        embed.set_footer(text="Trader Union Globale • Attendance System")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class EditAttendanceView(discord.ui.View):
    def __init__(self, bot, guild_id: str, batches: list, date: str, page: int = 0):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.batches = batches
        self.date = date
        self.page = page
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        
        # Previous button
        prev_btn = discord.ui.Button(label="◀️ Previous", style=discord.ButtonStyle.secondary, disabled=self.page == 0)
        prev_btn.callback = self.prev_page
        self.add_item(prev_btn)
        
        # Next button
        next_btn = discord.ui.Button(label="Next ▶️", style=discord.ButtonStyle.secondary, disabled=self.page >= len(self.batches) - 1)
        next_btn.callback = self.next_page
        self.add_item(next_btn)

    async def prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=await self.get_embed(interaction.guild), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=await self.get_embed(interaction.guild), view=self)

    async def get_embed(self, guild):
        if not self.batches:
            return discord.Embed(title="❌ No Batches Found", color=0xe74c3c)
        
        batch_role_id = self.batches[self.page]
        role = guild.get_role(int(batch_role_id))
        
        # Get batch name from config
        batches_data = load_attendance_batches(self.guild_id)
        batch_name = batches_data.get("batch_names", {}).get(batch_role_id, "Unknown Batch")
        
        attendance_data = load_attendance_data(self.guild_id)
        batch_data = attendance_data.get(batch_role_id, {}).get(self.date, {})
        
        # Get all members with this role
        members_list = []
        if role:
            for member in role.members:
                user_id = str(member.id)
                status_value, time_marked = get_user_day_status(batch_data, user_id)
                if status_value == "present":
                    status = "✅ Present"
                    time_marked = time_marked or "N/A"
                else:
                    status = "❌ Absent"
                    time_marked = time_marked or "—"
                members_list.append(f"{member.name} | {status} | {time_marked}")
        
        embed = discord.Embed(
            title=f"📝 EDIT ATTENDANCE - {self.date}",
            description=(
                f"**Batch:** {batch_name}\n"
                f"**Page:** {self.page + 1}/{len(self.batches)}\n\n"
                "```\nUse -editattendance @user DD/MM/YY (batch name)\n```\n"
                + ("\n".join(members_list) if members_list else "No members found")
            ),
            color=0x3498db
        )
        embed.set_footer(text="Trader Union Globale • Attendance Editor")
        return embed


class Attendance(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.attendance_list_task.start()

    def cog_unload(self):
        self.attendance_list_task.cancel()

    # ═══════════════════════════════════════════════════════════════
    #                    AUTO ATTENDANCE LIST AT 9PM
    # ═══════════════════════════════════════════════════════════════
    
    @tasks.loop(minutes=1)
    async def attendance_list_task(self):
        """Post attendance list at 9PM"""
        tz = pytz.timezone("Asia/Karachi")
        now = datetime.now(tz)

        # Run in a safe window at 9 PM PKT to avoid exact-time misses on restart/jitter.
        if now.hour != 21 or now.minute > 5:
            return

        # Skip weekends.
        if now.weekday() in [5, 6]:
            return

        report_date = now.strftime("%Y-%m-%d")
        today = now.strftime("%d/%m/%y")

        for guild in self.bot.guilds:
            guild_id = str(guild.id)
            try:
                guild_config = load_attendance_config(guild_id)
                if not guild_config:
                    continue
                if guild_config.get("last_report_date") == report_date:
                    continue

                batches_data = load_attendance_batches(guild_id)
                attendance_data = load_attendance_data(guild_id)
                if not isinstance(attendance_data, dict):
                    attendance_data = {}

                reminder_channel_id = guild_config.get("reminder_channel")
                channel_id = guild_config.get("channel")
                log_channel_id = guild_config.get("log_channel")

                report_channel = (
                    guild.get_channel(int(reminder_channel_id)) if reminder_channel_id
                    else guild.get_channel(int(channel_id)) if channel_id
                    else None
                )
                log_channel = guild.get_channel(int(log_channel_id)) if log_channel_id else None

                if not report_channel and not log_channel:
                    continue

                batches = batches_data.get("batches", [])

                # Collect all attendance data for summary.
                all_present = []
                all_absent = []

                for batch_role_id in batches:
                    role = guild.get_role(int(batch_role_id))
                    if not role:
                        continue

                    batch_name = batches_data.get("batch_names", {}).get(str(batch_role_id), "Unknown Batch")
                    batch_data = attendance_data.get(str(batch_role_id), {}).get(today, {})

                    present_list = []
                    absent_list = []

                    for member in role.members:
                        user_id = str(member.id)
                        status_value, time_marked = get_user_day_status(batch_data, user_id)
                        if status_value == "present":
                            present_list.append(f"{member.name} ({time_marked or 'N/A'})")
                            all_present.append(f"{member.name} - {batch_name}")
                        else:
                            absent_list.append(member.name)
                            all_absent.append(f"{member.name} - {batch_name}")

                    if report_channel:
                        embed = discord.Embed(
                            title=f"📋 ATTENDANCE LIST - {today}",
                            color=0x2b2d31
                        )
                        embed.set_author(name=f"✦ {batch_name} ✦")

                        description = "```ansi\n\u001b[1;36m═══════ DAILY REPORT ═══════\u001b[0m\n```\n"
                        if present_list:
                            description += "**✅ PRESENT:**\n" + "\n".join(present_list) + "\n\n"
                        if absent_list:
                            description += "**❌ ABSENT:**\n" + "\n".join(absent_list)
                        description += f"\n\n```fix\nTotal: {len(role.members)} | Present: {len(present_list)} | Absent: {len(absent_list)}\n```"

                        embed.description = description
                        embed.set_footer(text="Trader Union Globale • Attendance System")
                        embed.timestamp = now
                        await report_channel.send(embed=embed)

                if log_channel:
                    log_embed = discord.Embed(
                        title=f"📊 DAILY ATTENDANCE SUMMARY - {today}",
                        color=0x3498db
                    )
                    log_embed.set_author(name="✦ TRADER UNION GLOBALE ✦", icon_url=guild.icon.url if guild.icon else None)

                    present_text = "\n".join(all_present[:25]) if all_present else "No one present"
                    if len(all_present) > 25:
                        present_text += f"\n... and {len(all_present) - 25} more"

                    absent_text = "\n".join(all_absent[:25]) if all_absent else "No one absent"
                    if len(all_absent) > 25:
                        absent_text += f"\n... and {len(all_absent) - 25} more"

                    log_embed.add_field(
                        name=f"✅ PRESENT ({len(all_present)})",
                        value=f"```\n{present_text}\n```",
                        inline=False
                    )
                    log_embed.add_field(
                        name=f"❌ ABSENT ({len(all_absent)})",
                        value=f"```\n{absent_text}\n```",
                        inline=False
                    )

                    total = len(all_present) + len(all_absent)
                    rate = (len(all_present) / total * 100) if total > 0 else 0
                    log_embed.add_field(
                        name="📊 STATISTICS",
                        value=(
                            f"**Total Members:** {total}\n"
                            f"**Present:** {len(all_present)}\n"
                            f"**Absent:** {len(all_absent)}\n"
                            f"**Attendance Rate:** {rate:.1f}%"
                        ),
                        inline=False
                    )
                    log_embed.set_footer(text="Trader Union Globale • End of Day Report")
                    log_embed.timestamp = now
                    await log_channel.send(embed=log_embed)

                guild_config["last_report_date"] = report_date
                save_attendance_config(guild_id, guild_config)
            except Exception:
                continue

    @attendance_list_task.before_loop
    async def before_attendance_list(self):
        await self.bot.wait_until_ready()

    # ═══════════════════════════════════════════════════════════════
    #                    PREFIX COMMANDS
    # ═══════════════════════════════════════════════════════════════

    @commands.command(name="setattendancechannel", aliases=["sac"])
    @commands.has_permissions(administrator=True)
    async def set_attendance_channel(self, ctx, channel: discord.TextChannel):
        """Set the attendance channel"""
        guild_id = str(ctx.guild.id)
        config = load_attendance_config(guild_id)
        
        config["channel"] = str(channel.id)
        save_attendance_config(guild_id, config)
        
        embed = discord.Embed(
            title="⚙️ ATTENDANCE CHANNEL SET",
            description=(
                "```ansi\n"
                "\u001b[1;32mSTATUS  :\u001b[0m \u001b[0;37mCONFIGURED\u001b[0m\n"
                f"\u001b[1;32mCHANNEL :\u001b[0m \u001b[0;37m#{channel.name}\u001b[0m\n"
                "```\n"
                f"Attendance embeds will be sent to {channel.mention}"
            ),
            color=0x2ecc71
        )
        embed.set_footer(text="Trader Union Globale • Attendance System")
        await ctx.send(embed=embed)

    @commands.command(name="setattendancelog", aliases=["sal"])
    @commands.has_permissions(administrator=True)
    async def set_attendance_log(self, ctx, channel: discord.TextChannel):
        """Set the attendance log channel"""
        guild_id = str(ctx.guild.id)
        config = load_attendance_config(guild_id)
        
        config["log_channel"] = str(channel.id)
        save_attendance_config(guild_id, config)
        
        embed = discord.Embed(
            title="⚙️ ATTENDANCE LOG CHANNEL SET",
            description=(
                "```ansi\n"
                "\u001b[1;32mSTATUS  :\u001b[0m \u001b[0;37mCONFIGURED\u001b[0m\n"
                f"\u001b[1;32mCHANNEL :\u001b[0m \u001b[0;37m#{channel.name}\u001b[0m\n"
                "```\n"
                f"Attendance logs will be sent to {channel.mention}"
            ),
            color=0x2ecc71
        )
        embed.set_footer(text="Trader Union Globale • Attendance System")
        await ctx.send(embed=embed)

    @commands.command(name="attendancereminder", aliases=["attendance_reminder", "ar"])
    @commands.has_permissions(administrator=True)
    async def attendance_reminder(self, ctx, channel: Optional[discord.TextChannel] = None):
        """Set reminder/report channel for daily 9PM attendance post."""
        guild_id = str(ctx.guild.id)
        config = load_attendance_config(guild_id)

        if channel is None:
            current_id = config.get("reminder_channel")
            current_channel = ctx.guild.get_channel(int(current_id)) if current_id else None
            return await ctx.send(
                f"📌 Current attendance reminder channel: {current_channel.mention if current_channel else 'Not set'}\n"
                "Use: `-attendancereminder #channel`"
            )

        config["reminder_channel"] = str(channel.id)
        save_attendance_config(guild_id, config)

        embed = discord.Embed(
            title="⏰ ATTENDANCE REMINDER CHANNEL SET",
            description=f"Daily 9:00 PM attendance report will be sent in {channel.mention}.",
            color=0x2ecc71
        )
        embed.set_footer(text="Trader Union Globale • Attendance System")
        await ctx.send(embed=embed)

    @commands.command(name="setupattendance", aliases=["sa"])
    @commands.has_permissions(administrator=True)
    async def setup_attendance(self, ctx, channel: discord.TextChannel = None):
        """Setup the attendance embed with button (run once)\nUsage: -setupattendance #channel"""
        guild_id = str(ctx.guild.id)
        
        config = load_attendance_config(guild_id)
        if not config:
            config = {}

        if channel is not None:
            config["channel"] = str(channel.id)
            save_attendance_config(guild_id, config)

        if "channel" not in config:
            embed = discord.Embed(
                title="❌ ERROR",
                description="Please provide a channel: `-setupattendance #channel`",
                color=0xe74c3c
            )
            return await ctx.send(embed=embed)
        
        # Create the attendance embed
        tz = pytz.timezone("Asia/Karachi")
        now = datetime.now(tz)
        
        # Get batch list for display
        batches_data = load_attendance_batches(guild_id)
        batch_names = batches_data.get("batch_names", {})
        batch_list = "\n".join([f"• {name}" for name in batch_names.values()]) if batch_names else "No batches added yet"
        
        embed = discord.Embed(
            title="📋 DAILY ATTENDANCE",
            color=0x2b2d31
        )
        embed.set_author(
            name="✦ TRADER UNION GLOBALE ✦",
            icon_url=ctx.guild.icon.url if ctx.guild.icon else None
        )
        embed.description = (
            "╔══════════════════════════════════════╗\n"
            "║                                      ║\n"
            "║   📍 **MARK YOUR ATTENDANCE** 📍    ║\n"
            "║                                      ║\n"
            "╚══════════════════════════════════════╝\n\n"
            "```ansi\n"
            "\u001b[1;36m◈ WINDOW    :\u001b[0m \u001b[0;37m4:00 PM - 9:00 PM\u001b[0m\n"
            "\u001b[1;36m◈ STATUS    :\u001b[0m \u001b[1;32mOPEN\u001b[0m\n"
            "```\n\n"
            ">>> Click the button below to mark your attendance\n"
            "*Bot will automatically detect your batch*"
        )
        embed.set_image(url="https://i.pinimg.com/originals/17/d4/28/17d4284ce3ca7a29d116ac50e5e22818.gif")
        embed.set_footer(text="Trader Union Globale • Attendance System")
        embed.timestamp = now
        
        # Send to attendance channel
        target_channel = ctx.guild.get_channel(int(config["channel"]))
        if not target_channel:
            return await ctx.send("❌ Attendance channel not found. Use `-setupattendance #channel`.")

        view = AttendanceButton(self.bot)
        msg = await target_channel.send(embed=embed, view=view)
        
        config["attendance_message"] = str(msg.id)
        save_attendance_config(guild_id, config)
        
        response_embed = discord.Embed(
            title="✅ ATTENDANCE SETUP COMPLETE",
            description=(
                "```ansi\n"
                f"\u001b[1;32mCHANNEL :\u001b[0m \u001b[0;37m#{target_channel.name}\u001b[0m\n"
                "\u001b[1;32mSTATUS  :\u001b[0m \u001b[0;37mACTIVE\u001b[0m\n"
                "```\n"
                "Now add batches using `-addbatch @role Batch Name`"
            ),
            color=0x2ecc71
        )
        await ctx.send(embed=response_embed)

    @commands.command(name="addbatch", aliases=["ab", "createbatch"])
    @commands.has_permissions(administrator=True)
    async def add_batch(self, ctx, role: discord.Role, *, batch_name: str):
        """Add a batch to attendance system\nUsage: -addbatch @role Batch Name"""
        guild_id = str(ctx.guild.id)
        config = load_attendance_config(guild_id)
        if not config:
            config = {}
        batches_data = load_attendance_batches(guild_id)
        
        role_id = str(role.id)
        if role_id not in batches_data["batches"]:
            batches_data["batches"].append(role_id)
        
        # Store batch name
        batches_data["batch_names"][role_id] = batch_name
        
        save_attendance_batches(guild_id, batches_data)
        
        embed = discord.Embed(
            title="✅ BATCH ADDED",
            description=(
                "```ansi\n"
                f"\u001b[1;32mBATCH  :\u001b[0m \u001b[0;37m{batch_name}\u001b[0m\n"
                f"\u001b[1;32mROLE   :\u001b[0m \u001b[0;37m{role.name}\u001b[0m\n"
                "\u001b[1;32mSTATUS :\u001b[0m \u001b[0;37mACTIVE\u001b[0m\n"
                "```"
            ),
            color=0x2ecc71
        )
        embed.set_footer(text="Trader Union Globale • Attendance System")
        await ctx.send(embed=embed)

    @commands.command(name="attendancefor", aliases=["af", "viewattendance"])
    @commands.has_permissions(manage_messages=True)
    async def attendance_for(self, ctx, date: str, *, batch_name: str = None):
        """View attendance for a specific date (format: DD/MM/YY)"""
        guild_id = str(ctx.guild.id)
        attendance_data = load_attendance_data(guild_id)
        config = load_attendance_config(guild_id)
        batches_data = load_attendance_batches(guild_id)
        
        batches = batches_data.get("batches", [])
        batch_names = batches_data.get("batch_names", {})
        
        # Filter by batch name if provided
        if batch_name:
            batches = [rid for rid, bname in batch_names.items() if bname.lower() == batch_name.lower()]
        
        if not batches:
            embed = discord.Embed(
                title="❌ NO BATCHES FOUND",
                description="No attendance batches configured or batch name not found.",
                color=0xe74c3c
            )
            return await ctx.send(embed=embed)
        
        embeds = []
        for batch_role_id in batches:
            batch_role = ctx.guild.get_role(int(batch_role_id))
            if not batch_role:
                continue
            
            # Get batch name
            b_name = batch_names.get(batch_role_id, "Unknown Batch")
            
            batch_data = attendance_data.get(batch_role_id, {}).get(date, {})
            
            present_list = []
            absent_list = []
            
            for member in batch_role.members:
                user_id = str(member.id)
                status_value, time_marked = get_user_day_status(batch_data, user_id)
                if status_value == "present":
                    present_list.append(f"{member.name} ✅ Present ({time_marked or 'N/A'})")
                else:
                    absent_list.append(f"{member.name} ❌ Absent")
            
            embed = discord.Embed(
                title=f"📋 ATTENDANCE LIST - {date}",
                color=0x2b2d31
            )
            embed.set_author(name=f"✦ {b_name} ✦")
            
            description = ""
            if present_list:
                description += "**✅ PRESENT:**\n" + "\n".join(present_list) + "\n\n"
            if absent_list:
                description += "**❌ ABSENT:**\n" + "\n".join(absent_list)
            
            if not description:
                description = "No attendance records found for this date."
            
            description += f"\n\n```fix\nTotal: {len(batch_role.members)} | Present: {len(present_list)} | Absent: {len(absent_list)}\n```"
            
            embed.description = description
            embed.set_footer(text="Trader Union Globale • Attendance System")
            embeds.append(embed)
        
        if embeds:
            for emb in embeds[:10]:
                await ctx.send(embed=emb)
        else:
            await ctx.send("No attendance data found.")

    @commands.command(name="editattendancefor", aliases=["eaf"])
    @commands.has_permissions(administrator=True)
    async def edit_attendance_for(self, ctx, date: str):
        """Edit attendance for a specific date with pagination"""
        guild_id = str(ctx.guild.id)
        config = load_attendance_config(guild_id)
        batches_data = load_attendance_batches(guild_id)
        
        batches = batches_data.get("batches", [])
        
        if not batches:
            embed = discord.Embed(
                title="❌ NO BATCHES FOUND",
                description="No attendance batches configured.",
                color=0xe74c3c
            )
            return await ctx.send(embed=embed)
        
        view = EditAttendanceView(self.bot, guild_id, batches, date)
        embed = await view.get_embed(ctx.guild)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="editattendance", aliases=["ea", "toggleattendance"])
    @commands.has_permissions(administrator=True)
    async def edit_attendance(self, ctx, user: discord.Member, date: str, *, batch_name: str):
        """Edit attendance status for a user\nUsage: -editattendance @user DD/MM/YY Batch Name"""
        guild_id = str(ctx.guild.id)
        config = load_attendance_config(guild_id)
        batches_data = load_attendance_batches(guild_id)
        batch_names = batches_data.get("batch_names", {})
        
        # Find role_id by batch name
        role_id = None
        for rid, bname in batch_names.items():
            if bname.lower() == batch_name.lower():
                role_id = rid
                break
        
        if not role_id:
            embed = discord.Embed(
                title="❌ BATCH NOT FOUND",
                description=f"No batch found with name: {batch_name}",
                color=0xe74c3c
            )
            return await ctx.send(embed=embed)
        
        user_id = str(user.id)
        tz = pytz.timezone("Asia/Karachi")
        now = datetime.now(tz)

        async with ATTENDANCE_DATA_LOCK:
            attendance_data = load_attendance_data(guild_id)

            if not isinstance(attendance_data, dict):
                attendance_data = {}
            if role_id not in attendance_data:
                attendance_data[role_id] = {}
            if date not in attendance_data[role_id]:
                attendance_data[role_id][date] = {}

            current_status, _ = get_user_day_status(attendance_data[role_id][date], user_id)
            next_status = "absent" if current_status == "present" else "present"
            attendance_data[role_id][date][user_id] = {
                "status": next_status,
                "time": now.strftime("%I:%M %p") + " (Manual)",
                "username": user.name
            }
            save_attendance_data(guild_id, attendance_data)

        status = next_status.upper()
        color = 0x2ecc71 if next_status == "present" else 0xe74c3c
        
        embed = discord.Embed(
            title="📝 ATTENDANCE UPDATED",
            description=(
                "```ansi\n"
                f"\u001b[1;36mUSER   :\u001b[0m \u001b[0;37m{user.name}\u001b[0m\n"
                f"\u001b[1;36mDATE   :\u001b[0m \u001b[0;37m{date}\u001b[0m\n"
                f"\u001b[1;36mBATCH  :\u001b[0m \u001b[0;37m{batch_name}\u001b[0m\n"
                f"\u001b[1;36mSTATUS :\u001b[0m \u001b[0;37m{status}\u001b[0m\n"
                "```"
            ),
            color=color
        )
        embed.set_footer(text="Trader Union Globale • Attendance System")
        await ctx.send(embed=embed)

    @commands.command(name="removebatch", aliases=["rb", "delbatch"])
    @commands.has_permissions(administrator=True)
    async def remove_batch(self, ctx, *, batch_name: str):
        """Remove a batch from attendance tracking"""
        guild_id = str(ctx.guild.id)
        config = load_attendance_config(guild_id)
        batches_data = load_attendance_batches(guild_id)
        batch_names = batches_data.get("batch_names", {})
        
        # Find role_id by batch name
        role_id = None
        for rid, bname in batch_names.items():
            if bname.lower() == batch_name.lower():
                role_id = rid
                break
        
        if role_id:
            if role_id in batches_data.get("batches", []):
                batches_data["batches"].remove(role_id)
                if role_id in batches_data.get("batch_names", {}):
                    del batches_data["batch_names"][role_id]
                save_attendance_batches(guild_id, batches_data)
                
                embed = discord.Embed(
                    title="✅ BATCH REMOVED",
                    description=f"```ansi\n\u001b[1;32mREMOVED:\u001b[0m \u001b[0;37m{batch_name}\u001b[0m\n```",
                    color=0x2ecc71
                )
            else:
                embed = discord.Embed(
                    title="❌ NOT FOUND",
                    description="This batch is not in the attendance system.",
                    color=0xe74c3c
                )
        else:
            embed = discord.Embed(
                title="❌ NOT FOUND",
                description=f"No batch found with name: {batch_name}",
                color=0xe74c3c
            )
        
        await ctx.send(embed=embed)

    @commands.command(name="listbatches", aliases=["lb", "batches"])
    async def list_batches(self, ctx):
        """List all configured attendance batches"""
        guild_id = str(ctx.guild.id)
        config = load_attendance_config(guild_id)
        batches_data = load_attendance_batches(guild_id)
        
        batches = batches_data.get("batches", [])
        batch_names = batches_data.get("batch_names", {})
        channel_id = config.get("channel")
        log_channel_id = config.get("log_channel")
        reminder_channel_id = config.get("reminder_channel")
        
        if not batches:
            embed = discord.Embed(
                title="📋 NO BATCHES CONFIGURED",
                description="Use `-addbatch @role Batch Name` to add batches.",
                color=0xf39c12
            )
            return await ctx.send(embed=embed)
        
        batch_list = []
        for role_id in batches:
            role = ctx.guild.get_role(int(role_id))
            b_name = batch_names.get(role_id, "Unknown")
            if role:
                batch_list.append(f"• **{b_name}** ({len(role.members)} members)")
        
        channel = ctx.guild.get_channel(int(channel_id)) if channel_id else None
        log_channel = ctx.guild.get_channel(int(log_channel_id)) if log_channel_id else None
        reminder_channel = ctx.guild.get_channel(int(reminder_channel_id)) if reminder_channel_id else None
        
        embed = discord.Embed(
            title="📋 ATTENDANCE BATCHES",
            description=(
                f"**Channel:** {channel.mention if channel else 'Not set'}\n"
                f"**Reminder Channel:** {reminder_channel.mention if reminder_channel else 'Not set'}\n"
                f"**Log Channel:** {log_channel.mention if log_channel else 'Not set'}\n"
                f"**Time Window:** 4:00 PM - 9:00 PM (Mon-Fri)\n\n"
                "**Batches:**\n" + "\n".join(batch_list)
            ),
            color=0x3498db
        )
        embed.set_footer(text="Trader Union Globale • Attendance System")
        await ctx.send(embed=embed)

    # ═══════════════════════════════════════════════════════════════
    #                    USER ATTENDANCE COMMANDS
    # ═══════════════════════════════════════════════════════════════

    @commands.command(name="showuserattendance", aliases=["sua", "userattendance"])
    @commands.has_permissions(manage_messages=True)
    async def show_user_attendance(self, ctx, user: discord.Member):
        """Show attendance history of a user"""
        guild_id = str(ctx.guild.id)
        attendance_data = load_attendance_data(guild_id)
        config = load_attendance_config(guild_id)
        batches_data = load_attendance_batches(guild_id)
        user_id = str(user.id)
        
        batches = batches_data.get("batches", [])
        batch_names = batches_data.get("batch_names", {})
        
        # Find user's batch
        user_batch_role_id = None
        user_batch_name = None
        user_roles_ids = [str(r.id) for r in user.roles]
        
        for role_id in batches:
            if role_id in user_roles_ids:
                user_batch_role_id = role_id
                user_batch_name = batch_names.get(role_id, "Unknown Batch")
                break
        
        if not user_batch_role_id:
            embed = discord.Embed(
                title="❌ USER NOT IN ANY BATCH",
                description=f"{user.name} is not part of any attendance batch.",
                color=0xe74c3c
            )
            return await ctx.send(embed=embed)
        
        # Get attendance records
        user_attendance = attendance_data.get(user_batch_role_id, {})
        
        # Count present days
        present_count = 0
        total_days = 0
        recent_records = []
        
        for date, records in sorted(user_attendance.items(), reverse=True)[:30]:  # Last 30 days
            total_days += 1
            status_value, time_marked = get_user_day_status(records, user_id)
            if status_value == "present":
                present_count += 1
                recent_records.append(f"✅ {date} - {time_marked or 'N/A'}")
            else:
                recent_records.append(f"❌ {date} - Absent")
        
        embed = discord.Embed(
            title=f"📊 ATTENDANCE REPORT - {user.name}",
            color=0x3498db
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(
            name="🎫 Batch",
            value=user_batch_name,
            inline=True
        )
        embed.add_field(
            name="📈 Attendance Rate",
            value=f"{present_count}/{total_days} ({(present_count/total_days*100) if total_days > 0 else 0:.1f}%)",
            inline=True
        )
        embed.add_field(
            name="📅 Recent Records",
            value="\n".join(recent_records[:10]) if recent_records else "No records found",
            inline=False
        )
        embed.set_footer(text="Trader Union Globale • Attendance System")
        await ctx.send(embed=embed)

    @commands.command(name="attendancefordate", aliases=["afd"])
    @commands.has_permissions(manage_messages=True)
    async def attendance_for_date(self, ctx, date: str, *, batch_name: str = None):
        """View attendance for a specific date\nUsage: -attendancefordate DD/MM/YY [Batch Name]"""
        guild_id = str(ctx.guild.id)
        attendance_data = load_attendance_data(guild_id)
        config = load_attendance_config(guild_id)
        batches_data = load_attendance_batches(guild_id)
        
        batches = batches_data.get("batches", [])
        batch_names_config = batches_data.get("batch_names", {})
        
        # Filter by batch name if provided
        if batch_name:
            batches = [rid for rid, bname in batch_names_config.items() if bname.lower() == batch_name.lower()]
        
        if not batches:
            embed = discord.Embed(
                title="❌ NO BATCHES FOUND",
                description="No attendance batches configured or batch name not found.",
                color=0xe74c3c
            )
            return await ctx.send(embed=embed)
        
        for batch_role_id in batches:
            batch_role = ctx.guild.get_role(int(batch_role_id))
            if not batch_role:
                continue
            
            b_name = batch_names_config.get(batch_role_id, "Unknown Batch")
            batch_data = attendance_data.get(batch_role_id, {}).get(date, {})
            
            present_list = []
            absent_list = []
            
            for member in batch_role.members:
                user_id = str(member.id)
                status_value, time_marked = get_user_day_status(batch_data, user_id)
                if status_value == "present":
                    present_list.append(f"{member.name} ({time_marked or 'N/A'})")
                else:
                    absent_list.append(member.name)
            
            embed = discord.Embed(
                title=f"📋 ATTENDANCE - {date}",
                color=0x2b2d31
            )
            embed.set_author(name=f"✦ {b_name} ✦")
            
            embed.add_field(
                name=f"✅ Present ({len(present_list)})",
                value="\n".join(present_list) if present_list else "None",
                inline=True
            )
            embed.add_field(
                name=f"❌ Absent ({len(absent_list)})",
                value="\n".join(absent_list) if absent_list else "None",
                inline=True
            )
            embed.set_footer(text=f"Total: {len(batch_role.members)} | Present: {len(present_list)} | Absent: {len(absent_list)}")
            await ctx.send(embed=embed)

    @commands.command(name="edituserattendance", aliases=["eua"])
    @commands.has_permissions(administrator=True)
    async def edit_user_attendance(self, ctx, user: discord.Member, date: str, status: str):
        """Edit user attendance for a date\nUsage: -edituserattendance @user DD/MM/YY present/absent"""
        guild_id = str(ctx.guild.id)
        config = load_attendance_config(guild_id)
        batches_data = load_attendance_batches(guild_id)
        user_id = str(user.id)
        
        batches = batches_data.get("batches", [])
        batch_names = batches_data.get("batch_names", {})
        
        # Find user's batch
        user_batch_role_id = None
        user_batch_name = None
        user_roles_ids = [str(r.id) for r in user.roles]
        
        for role_id in batches:
            if role_id in user_roles_ids:
                user_batch_role_id = role_id
                user_batch_name = batch_names.get(role_id, "Unknown Batch")
                break
        
        if not user_batch_role_id:
            embed = discord.Embed(
                title="❌ USER NOT IN ANY BATCH",
                description=f"{user.name} is not part of any attendance batch.",
                color=0xe74c3c
            )
            return await ctx.send(embed=embed)
        
        tz = pytz.timezone("Asia/Karachi")
        now = datetime.now(tz)

        if status.lower() not in {"present", "absent"}:
            embed = discord.Embed(
                title="❌ INVALID STATUS",
                description="Status must be `present` or `absent`",
                color=0xe74c3c
            )
            return await ctx.send(embed=embed)

        async with ATTENDANCE_DATA_LOCK:
            attendance_data = load_attendance_data(guild_id)

            if not isinstance(attendance_data, dict):
                attendance_data = {}
            if user_batch_role_id not in attendance_data:
                attendance_data[user_batch_role_id] = {}
            if date not in attendance_data[user_batch_role_id]:
                attendance_data[user_batch_role_id][date] = {}

            attendance_data[user_batch_role_id][date][user_id] = {
                "status": status.lower(),
                "time": now.strftime("%I:%M %p") + " (Manual)",
                "username": user.name
            }
            save_attendance_data(guild_id, attendance_data)

        color = 0x2ecc71 if status.lower() == "present" else 0xe74c3c
        
        embed = discord.Embed(
            title="📝 ATTENDANCE UPDATED",
            description=(
                "```ansi\n"
                f"\u001b[1;36mUSER   :\u001b[0m \u001b[0;37m{user.name}\u001b[0m\n"
                f"\u001b[1;36mDATE   :\u001b[0m \u001b[0;37m{date}\u001b[0m\n"
                f"\u001b[1;36mBATCH  :\u001b[0m \u001b[0;37m{user_batch_name}\u001b[0m\n"
                f"\u001b[1;36mSTATUS :\u001b[0m \u001b[0;37m{status.upper()}\u001b[0m\n"
                "```"
            ),
            color=color
        )
        embed.set_footer(text="Trader Union Globale • Attendance System")
        await ctx.send(embed=embed)

    @commands.command(name="editattendancefordate", aliases=["eafd"])
    @commands.has_permissions(administrator=True)
    async def edit_attendance_for_date(self, ctx, date: str):
        """Edit attendance for a specific date with pagination"""
        guild_id = str(ctx.guild.id)
        config = load_attendance_config(guild_id)
        batches_data = load_attendance_batches(guild_id)
        
        batches = batches_data.get("batches", [])
        
        if not batches:
            embed = discord.Embed(
                title="❌ NO BATCHES FOUND",
                description="No attendance batches configured.",
                color=0xe74c3c
            )
            return await ctx.send(embed=embed)
        
        view = EditAttendanceView(self.bot, guild_id, batches, date)
        embed = await view.get_embed(ctx.guild)
        await ctx.send(embed=embed, view=view)

    # Persistent button handler
    @commands.Cog.listener()
    async def on_ready(self):
        """Re-register persistent views on bot restart"""
        view = AttendanceButton(self.bot)
        self.bot.add_view(view)


async def setup(bot):
    await bot.add_cog(Attendance(bot))
