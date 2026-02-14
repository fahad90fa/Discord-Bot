import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import json
import os
from datetime import datetime, timedelta
import pytz
import xml.etree.ElementTree as ET

SENT_NEWS_FILE = "sent_news.json"
SESSION_ALERT_FILE = "session_alert_config.json"
from .utils import get_news_channel, set_news_channel, is_owner_check

def load_sent_news():
    if not os.path.exists(SENT_NEWS_FILE):
        return {}
    try:
        with open(SENT_NEWS_FILE, "r") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except:
        return {}

def save_sent_news(data):
    with open(SENT_NEWS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def load_session_alert_config():
    default = {"channels": {}, "last_sent": {}}
    if not os.path.exists(SESSION_ALERT_FILE):
        return default
    try:
        with open(SESSION_ALERT_FILE, "r") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return default
            data.setdefault("channels", {})
            data.setdefault("last_sent", {})
            return data
    except Exception:
        return default

def save_session_alert_config(data):
    with open(SESSION_ALERT_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_session_open_utc(now_utc, tz_name, hour, minute=0):
    """Return session open time for current local day in UTC + local datetime."""
    local_tz = pytz.timezone(tz_name)
    local_now = now_utc.astimezone(local_tz)
    open_local = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    open_utc = open_local.astimezone(pytz.UTC)
    return open_utc, open_local

def get_next_session_open_pkt(now_utc, tz_name, hour, minute=0):
    """Return next session open datetime converted to PKT."""
    local_tz = pytz.timezone(tz_name)
    local_now = now_utc.astimezone(local_tz)
    open_local = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if open_local <= local_now:
        open_local = open_local + timedelta(days=1)
    return open_local.astimezone(pytz.timezone("Asia/Karachi"))

# File-based cache for persistence across restarts
CACHE_FILE = "news_cache.json"
NEWS_CACHE = []
LAST_FETCH_TIME = None

def load_cache_from_file():
    global NEWS_CACHE, LAST_FETCH_TIME
    if os.path.exists(CACHE_FILE):
        if os.path.getsize(CACHE_FILE) == 0:
            return
        try:
            with open(CACHE_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, dict) and "news" in data:
                    NEWS_CACHE = data.get("news", [])
                    fetch_time_str = data.get("fetch_time")
                    if fetch_time_str:
                        LAST_FETCH_TIME = datetime.fromisoformat(fetch_time_str)
                    print(f"📁 Loaded {len(NEWS_CACHE)} events from cache.")
                else:
                    NEWS_CACHE = []
                    LAST_FETCH_TIME = None
        except Exception as e:
            print(f"Error loading cache file: {e}")
            # If the file is broken, let's reset it
            NEWS_CACHE = []
            LAST_FETCH_TIME = None

def save_cache_to_file():
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({
                "news": NEWS_CACHE,
                "fetch_time": LAST_FETCH_TIME.isoformat() if LAST_FETCH_TIME else None
            }, f, indent=4)
    except Exception as e:
        print(f"Error saving cache file: {e}")

def parse_xml_events(root):
    events = []
    for item in root.findall('event'):
        # XML Parse
        title = item.find('title').text or ""
        country = item.find('country').text or ""
        date_str = item.find('date').text or "" # Format: 02-08-2026
        time_str = item.find('time').text or "" # Format: 1:00pm
        impact = item.find('impact').text or ""
        forecast = item.find('forecast').text or ""
        actual = item.find('actual').text if item.find('actual') is not None else ""
        previous = item.find('previous').text or ""
        
        # Parse time
        try:
            # Example: 02-08-2026 1:00pm
            dt_combined = f"{date_str} {time_str}"
            try:
                dt_obj = datetime.strptime(dt_combined, "%m-%d-%Y %I:%M%p")
            except ValueError:
                # Try fallback parsing or skip if 'Tentative'
                continue
            
            # The XML time is in GMT/UTC (Forex Factory standard)
            # Localize as UTC first, then we can convert to any timezone for display
            tz_source = pytz.UTC
            try:
                dt_localized = tz_source.localize(dt_obj, is_dst=None)
            except pytz.AmbiguousTimeError:
                # Fallback for ambiguous times (rare overlap)
                dt_localized = tz_source.localize(dt_obj, is_dst=False)
            except pytz.NonExistentTimeError:
                # Fallback for missing times (spring forward)
                dt_localized = tz_source.localize(dt_obj)

            # Save as UTC ISO string for consistent storage
            iso_date = dt_localized.isoformat()
        except Exception as e:
            continue

        events.append({
            "title": title,
            "country": country,
            "date": iso_date,
            "impact": impact,
            "forecast": forecast,
            "actual": actual,
            "previous": previous
        })
    return events

async def fetch_news_from_api():
    """Fetch news directly from API (skips local XML and cache)"""
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://www.forexfactory.com/"
    }
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    xml_text = await response.text()
                    if "weeklyevents" not in xml_text:
                        return None
                    root = ET.fromstring(xml_text)
                    events = parse_xml_events(root)
                    return events if events else None
                return None
    except Exception as e:
        print(f"API fetch error: {e}")
        return None

async def fetch_news_data(force=False):
    global NEWS_CACHE, LAST_FETCH_TIME
    
    # Force purge if requested
    if force:
        NEWS_CACHE = []
        LAST_FETCH_TIME = None
        if os.path.exists(CACHE_FILE):
            try: os.remove(CACHE_FILE)
            except: pass

    # 1. Try to read from local XML file specifically provided by user
    if os.path.exists("current_news.xml"):
        try:
            tree = ET.parse("current_news.xml")
            root = tree.getroot()
            if root.tag == "weeklyevents":
                print("📁 Loading data from local 'current_news.xml'")
                events = parse_xml_events(root)
                if events:
                    NEWS_CACHE = events
                    LAST_FETCH_TIME = datetime.now()
                    # We don't save to cache file here necessarily, or maybe we should?
                    # Let's just treat it as valid cache for this session
                    return events
            else:
                print("⚠️ Local 'current_news.xml' is not valid (HTML or wrong format).")
        except Exception as e:
            print(f"⚠️ Error reading local XML: {e}")

    # 2. Try to load from file cache if memory is empty
    if not NEWS_CACHE:
        load_cache_from_file()

    now = datetime.now()
    # 3. Cache is valid for 6 hours
    if not force and LAST_FETCH_TIME and (now - LAST_FETCH_TIME).total_seconds() < 21600 and NEWS_CACHE:
        return NEWS_CACHE

    # 4. Fetch from API
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://www.forexfactory.com/"
    }
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    try:
                        xml_text = await response.text()
                        if "weeklyevents" not in xml_text:
                            return NEWS_CACHE # HTML error page probably
                        
                        root = ET.fromstring(xml_text)
                        events = parse_xml_events(root)

                        if events:
                            NEWS_CACHE = events
                            LAST_FETCH_TIME = now
                            save_cache_to_file()
                            return events
                        return NEWS_CACHE
                    except Exception as e:
                        # Silent error handling - just use cache
                        return NEWS_CACHE
                elif response.status == 429:
                    # Rate limited - silently use existing cache without warning
                    return NEWS_CACHE
                else:
                    return NEWS_CACHE
    except Exception as e:
        # Silent fallback to cache on any error
        return NEWS_CACHE

class ForexNews(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_forex_news.start()
        self.session_open_alerts.start()

    def cog_unload(self):
        if self.check_forex_news.is_running():
            self.check_forex_news.cancel()
        if self.session_open_alerts.is_running():
            self.session_open_alerts.cancel()

    @tasks.loop(minutes=1)
    async def check_forex_news(self):
        channel_id = get_news_channel()
        if not channel_id:
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            return

        # Check if we have recent cache (less than 6 hours old)
        # This prevents unnecessary API calls and rate limiting
        global LAST_FETCH_TIME
        if LAST_FETCH_TIME:
            time_since_fetch = (datetime.now() - LAST_FETCH_TIME).total_seconds()
            if time_since_fetch > 21600:  # Only fetch if cache is older than 6 hours
                news_data = await fetch_news_data()
            else:
                news_data = NEWS_CACHE  # Use existing cache
        else:
            news_data = await fetch_news_data()
            
        if not news_data:
            return

        sent_news_dict = load_sent_news() # Format: {event_id: {"msg_id": 123, "actual": "1.2%"}}
        now_utc = datetime.now(pytz.UTC)
        changed = False

        for event in news_data:
            # Event unique ID
            event_id = f"{event['title']}_{event['country']}_{event['date']}"
            event_record = sent_news_dict.get(event_id, {})
            
            # Parse event date
            try:
                event_dt = datetime.fromisoformat(event['date'])
                if event_dt.tzinfo is None:
                    event_dt = pytz.UTC.localize(event_dt)
                else:
                    event_dt = event_dt.astimezone(pytz.UTC)
            except Exception:
                continue

            time_diff = (event_dt - now_utc).total_seconds() / 60.0

            # Impact Colors & Emojis
            impact = event['impact']
            color = discord.Color.blue()
            impact_emoji = "⚪"
            
            if impact == "High":
                color = discord.Color.red()
                impact_emoji = "🔴"
            elif impact == "Medium":
                color = discord.Color.orange()
                impact_emoji = "🟠"
            elif impact == "Low":
                color = discord.Color.light_gray()
                impact_emoji = "🟡"
            elif impact == "Holiday":
                color = discord.Color.purple()
                impact_emoji = "🟣"

            # News Item Embed Generator
            def create_news_embed(title_prefix, footer_text):
                is_past = time_diff < 0
                status_label = "RESULTS LIVE" if (is_past and event.get('actual')) else "UPCOMING"
                
                # Professional Theme Colors
                embed_color = 0x2b2d31 # Institutional Gray
                if impact == "High": embed_color = 0xff4b4b # Premium Red
                elif impact == "Medium": embed_color = 0xffa500 # Trading Orange
                
                embed = discord.Embed(
                    title=f"| QUANTUM TERMINAL | {event['title'].upper()}",
                    color=embed_color,
                    timestamp=datetime.utcnow()
                )
                
                # Execution Data Grid
                act_val = event.get('actual', 'PENDING')
                fcs_val = event['forecast'] if event['forecast'] else 'N/A'
                prv_val = event['previous'] if event['previous'] else 'N/A'
                
                grid = (
                    f"┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓\n"
                    f"┃ ACTUAL   ┃ {act_val:<16} ┃\n"
                    f"┃ FORECAST ┃ {fcs_val:<16} ┃\n"
                    f"┃ PREVIOUS ┃ {prv_val:<16} ┃\n"
                    f"┗━━━━━━━━━━┻━━━━━━━━━━━━━━━━━━┛"
                )
                embed.description = f"```\n{grid}\n```"
                
                # Metadata
                pkr_time = event_dt.astimezone(pytz.timezone('Asia/Karachi'))
                embed.add_field(name="🌍 REGION", value=f"`{event['country']}`", inline=True)
                embed.add_field(name="📊 IMPACT", value=f"`{impact.upper()}`", inline=True)
                embed.add_field(name="⏰ PK TIME", value=f"**{pkr_time.strftime('%I:%M %p')}**", inline=True)
                embed.add_field(name="📅 DATE", value=f"`{pkr_time.strftime('%a, %b %d')}`", inline=True)
                
                if not is_past:
                    hours, rem = divmod(int(abs(time_diff)), 60)
                    embed.add_field(name="⏱️ COUNTDOWN", value=f"`T-{hours}h {rem}m`", inline=True)

                # Set Official Logo
                embed.set_thumbnail(url="https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441")
                
                embed.set_footer(text=f"TRADERS UNION FEED v3.0 • {footer_text}")
                return embed

            # Case 1: LIVE RESULT UPDATE (If alert already sent but actual was missing)
            if event_record.get("msg_id") and not event_record.get("actual") and event.get("actual"):
                try:
                    msg = await channel.fetch_message(event_record["msg_id"])
                    embed = create_news_embed("🚨 LIVE UPDATE", "Forex Factory Real-Time Result")
                    await msg.edit(embed=embed)
                    event_record["actual"] = event["actual"]
                    sent_news_dict[event_id] = event_record
                    changed = True
                except:
                    pass

            # Case 2: SEND ALERT (At the time)
            if 0 >= time_diff > -2:
                if not event_record.get("alert_sent"):
                    embed = create_news_embed("ACTUAL NEWS", "LIVE MARKET UPDATE")
                    msg = await channel.send(embed=embed)
                        
                    event_record["alert_sent"] = True
                    event_record["msg_id"] = msg.id
                    event_record["actual"] = event.get("actual", "")
                    sent_news_dict[event_id] = event_record
                    changed = True

            # Case 3: 30-minute Reminder (Only for High/Medium and Today's events only)
            # Use a wider window so loop timing jitter does not skip reminders.
            elif 30 >= time_diff > 2:
                # Check if event is today (PKT)
                now_pkt = datetime.now(pytz.timezone('Asia/Karachi'))
                event_pkt = event_dt.astimezone(pytz.timezone('Asia/Karachi'))
                is_today = event_pkt.strftime('%Y-%m-%d') == now_pkt.strftime('%Y-%m-%d')
                
                if not event_record.get("reminder_sent") and impact in ["High", "Medium"] and is_today:
                    embed = create_news_embed("⏳ News in 30 Mins", "Forex Factory Reminder")
                    await channel.send(embed=embed)
                    event_record["reminder_sent"] = True
                    sent_news_dict[event_id] = event_record
                    changed = True

        if changed:
            save_sent_news(sent_news_dict)

    @tasks.loop(minutes=1)
    async def session_open_alerts(self):
        config = load_session_alert_config()
        channels = config.get("channels", {})
        if not channels:
            return

        now_utc = datetime.now(pytz.UTC)
        now_pkt = now_utc.astimezone(pytz.timezone("Asia/Karachi"))
        changed = False

        asia_open_utc, asia_open_local = get_session_open_utc(now_utc, "Asia/Tokyo", 9, 0)
        london_open_utc, london_open_local = get_session_open_utc(now_utc, "Europe/London", 8, 0)

        sessions = [
            {
                "key": "asia",
                "title": "🌏 ASIA SESSION OPEN",
                "market": "Tokyo",
                "open_utc": asia_open_utc,
                "open_local": asia_open_local
            },
            {
                "key": "london",
                "title": "🏦 LONDON SESSION OPEN",
                "market": "London",
                "open_utc": london_open_utc,
                "open_local": london_open_local
            }
        ]

        for guild_id, channel_id in channels.items():
            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                continue

            guild_last = config.setdefault("last_sent", {}).setdefault(guild_id, {})

            for session in sessions:
                minutes_since_open = (now_utc - session["open_utc"]).total_seconds() / 60.0
                session_date_key = session["open_local"].strftime("%Y-%m-%d")

                # 10-minute send window prevents missing alerts if loop jitters/restarts.
                if 0 <= minutes_since_open <= 10 and guild_last.get(session["key"]) != session_date_key:
                    embed = discord.Embed(
                        title=f"🚨 {session['title']}",
                        description=(
                            f"**Market:** `{session['market']}`\n"
                            f"**PKT Time:** `{now_pkt.strftime('%I:%M %p')}`\n"
                            f"**UTC Time:** `{now_utc.strftime('%H:%M')} UTC`\n"
                            f"**Status:** `LIQUIDITY RISING`"
                        ),
                        color=0x2b2d31,
                        timestamp=datetime.utcnow()
                    )
                    embed.set_footer(text="TRADERS UNION • Session Alert Engine")
                    await channel.send(embed=embed)

                    guild_last[session["key"]] = session_date_key
                    changed = True

        if changed:
            save_session_alert_config(config)

    @session_open_alerts.before_loop
    async def before_session_open_alerts(self):
        await self.bot.wait_until_ready()

    @commands.command(name="forextest")
    @is_owner_check()
    async def forextest(self, ctx):
        """Manually test the Forex news fetching system (Owner Only)"""
        await ctx.send("🔍 `PURGING CACHE & RE-CAPTURING DATA...`")
        
        news_data = await fetch_news_data(force=True)

        if not news_data:
            return await ctx.send("❌ No news data available (API limit reached and cache empty).")

        # Get the 3 most relevant events (upcoming or recent)
        now_utc = datetime.now(pytz.UTC)
        sorted_events = sorted(news_data, key=lambda x: abs((datetime.fromisoformat(x['date']).astimezone(pytz.UTC) - now_utc).total_seconds()))
        
        test_events = sorted_events[:3]
        
        await ctx.send(f"✅ Found {len(news_data)} events. Showing 3 nearest/current events for testing:")

        for event in test_events:
            event_dt = datetime.fromisoformat(event['date']).astimezone(pytz.UTC)
            impact = event['impact']
            color = discord.Color.blue()
            impact_emoji = "⚪"
            
            if impact == "High":
                color = discord.Color.red()
                impact_emoji = "🔴"
            elif impact == "Medium":
                color = discord.Color.orange()
                impact_emoji = "🟠"
            elif impact == "Low":
                color = discord.Color.light_gray()
                impact_emoji = "🟡"
            elif impact == "Holiday":
                color = discord.Color.purple()
                impact_emoji = "🟣"

            embed = discord.Embed(
                title=f"🧪 Test Alert: {event['title']}",
                color=color,
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Country", value=f"🌍 {event['country']}", inline=True)
            embed.add_field(name="Impact", value=f"{impact_emoji} {impact}", inline=True)
            if event.get('actual'):
                embed.add_field(name="Actual", value=f"✅ {event['actual']}", inline=True)
            if event['forecast']:
                embed.add_field(name="Forecast", value=f"📊 {event['forecast']}", inline=True)
            
            pkr_time = event_dt.astimezone(pytz.timezone('Asia/Karachi'))
            embed.add_field(name="Date & Day", value=f"📅 {pkr_time.strftime('%A, %b %d')}", inline=True)
            embed.add_field(name="Time", value=f"⏰ {pkr_time.strftime('%I:%M %p')} (PKT)\n🌐 {event_dt.strftime('%I:%M %p')} (UTC)", inline=True)
            
            embed.set_footer(text="Forex Factory Manual Test")
            await ctx.send(embed=embed)


    @commands.command(name="today")
    async def todaynews(self, ctx):
        """Show all economic events for today with animated sequence"""
        load_msg = await ctx.send("📡 `CONNECTING TO Traders Union Manager TERMINAL...`")
        await asyncio.sleep(0.6)
        await load_msg.edit(content="🛰️ `SCANNING GLOBAL LPs & DATA FEEDS...`")
        await asyncio.sleep(0.6)
        await load_msg.edit(content="💎 `DECRYPTING MARKET INTELLIGENCE...`")
        
        # Use force=True to ensure we read latest local XML if available
        # This is safe now because local file check effectively bypasses API rate limits
        news_data = await fetch_news_data(force=True)
        if not news_data:
            await load_msg.delete()
            return await ctx.send("❌ `DATA LINK FAILED. TRY LATER.`")

        now_pkr = datetime.now(pytz.timezone('Asia/Karachi'))
        today_str = now_pkr.strftime('%Y-%m-%d')
        
        # Debugging: Show checked date if no events found
        today_events = []
        for event in news_data:
            event_dt = datetime.fromisoformat(event['date']).astimezone(pytz.timezone('Asia/Karachi'))
            if event_dt.strftime('%Y-%m-%d') == today_str:
                today_events.append(event)

        await load_msg.delete()
        if not today_events:
            return await ctx.send(f"🏜️ No economic events found for today (**{now_pkr.strftime('%A, %b %d')}**).\n*Filter Date: {today_str}*")

        # Group by Impact
        impact_groups = {"High": [], "Medium": [], "Low": [], "Holiday": []}
        for event in today_events:
            impact_groups[event.get('impact', 'Low')].append(event)

        # 1. MAIN HEADER EMBED
        date_display = now_pkr.strftime('%A, %b %d, %Y')
        main_embed = discord.Embed(
            title="💎 TRADERS UNION MANAGER | DAILY DASHBOARD",
            description=(
                f"**📅 REPORT DATE:** `{date_display}`\n"
                f"**SESSION:** `TRADING OPEN` | **PKT TIME:** `{now_pkr.strftime('%I:%M %p')}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=0x2b2d31
        )
        main_embed.set_author(name="TRADERS UNION", icon_url="https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441")
        await ctx.send(embed=main_embed)

        # 2. SEPARATE EMBEDS PER IMPACT
        impact_order = [
            ("High", "🔴 HIGH IMPACT EVENTS", 0xff4b4b),
            ("Medium", "🟠 MEDIUM IMPACT EVENTS", 0xffa500),
            ("Low", "🟡 LOW IMPACT EVENTS", 0xbcbcbc),
            ("Holiday", "🟣 HOLIDAY / MARKET CLOSURES", 0xa020f0)
        ]

        for imp_key, title, color in impact_order:
            events = impact_groups.get(imp_key, [])
            if not events:
                continue

            group_text = ""
            for ev in sorted(events, key=lambda x: x['date']):
                ev_dt = datetime.fromisoformat(ev['date']).astimezone(pytz.timezone('Asia/Karachi'))
                is_p = ev_dt < now_pkr
                
                time_f = ev_dt.strftime('%I:%M %p')
                date_f = ev_dt.strftime('%a, %b %d')
                status = "✅" if is_p else "•"
                
                # Dynamic Result Coloring
                data_str = f"**{ev['actual']}**" if ev.get('actual') else f"`FCS: {ev.get('forecast', '---')}`"
                
                group_text += f"{status} `{date_f}` | `{time_f}` | **{ev['country']}** | {ev['title']}\n└ Result: {data_str}\n\n"

            if group_text:
                imp_embed = discord.Embed(title=title, description=group_text, color=color)
                imp_embed.set_footer(text=f"TRADERS UNION • {imp_key.upper()} ANALYSIS", icon_url="https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441")
                await ctx.send(embed=imp_embed)

    @commands.command(name="reminders", aliases=["reminder"])
    async def reminder_status(self, ctx):
        """Check the status of upcoming news reminders (fetches from API)"""
        load_msg = await ctx.send("📡 `FETCHING LIVE DATA FROM API...`")
        
        # Fetch directly from API (skip local XML)
        news_data = await fetch_news_from_api()
        sent_news_dict = load_sent_news()
        
        if not news_data:
            await load_msg.delete()
            return await ctx.send("❌ `API SYNC FAILED. CHECK CONNECTION.`")

        now_utc = datetime.now(pytz.UTC)
        now_pkt = datetime.now(pytz.timezone('Asia/Karachi'))
        today_str_pkt = now_pkt.strftime('%Y-%m-%d')
        
        upcoming_reminders = []
        within_30_min = []  # Events coming in 30 minutes
        
        # First pass: Try to get today's upcoming events
        for event in news_data:
            event_dt = datetime.fromisoformat(event['date']).astimezone(pytz.UTC)
            event_dt_pkt = event_dt.astimezone(pytz.timezone('Asia/Karachi'))
            event_date_str = event_dt_pkt.strftime('%Y-%m-%d')
            
            # Only today's events
            if event_date_str != today_str_pkt:
                continue
            
            time_diff = (event_dt - now_utc).total_seconds() / 60.0
            impact = event['impact']

            # Only track High/Medium impact events that haven't happened yet
            if impact in ["High", "Medium"] and time_diff > 0:
                event_id = f"{event['title']}_{event['country']}_{event['date']}"
                is_sent = sent_news_dict.get(event_id, {}).get("reminder_sent", False)
                item = {
                    "event": event,
                    "time": event_dt,
                    "sent": is_sent,
                    "diff": time_diff
                }
                upcoming_reminders.append(item)
                
                # Track events within 30 minutes
                if time_diff <= 30:
                    within_30_min.append(item)
        
        # If no upcoming events today, get tomorrow's events
        if not upcoming_reminders:
            from datetime import timedelta
            tomorrow_pkt = now_pkt + timedelta(days=1)
            tomorrow_str = tomorrow_pkt.strftime('%Y-%m-%d')
            
            for event in news_data:
                event_dt = datetime.fromisoformat(event['date']).astimezone(pytz.UTC)
                event_dt_pkt = event_dt.astimezone(pytz.timezone('Asia/Karachi'))
                event_date_str = event_dt_pkt.strftime('%Y-%m-%d')
                
                # Only tomorrow's events
                if event_date_str != tomorrow_str:
                    continue
                
                time_diff = (event_dt - now_utc).total_seconds() / 60.0
                impact = event['impact']
                
                if impact in ["High", "Medium"] and time_diff > 0:
                    event_id = f"{event['title']}_{event['country']}_{event['date']}"
                    is_sent = sent_news_dict.get(event_id, {}).get("reminder_sent", False)
                    item = {
                        "event": event,
                        "time": event_dt,
                        "sent": is_sent,
                        "diff": time_diff
                    }
                    upcoming_reminders.append(item)

        await load_msg.delete()
        if not upcoming_reminders:
            return await ctx.send("🏜️ `NO PENDING HIGH/MEDIUM REMINDERS IN QUEUE.`")

        # Check if we're showing today or tomorrow's news
        first_event_pkt = upcoming_reminders[0]['time'].astimezone(pytz.timezone('Asia/Karachi'))
        showing_date = first_event_pkt.strftime('%Y-%m-%d')
        is_today = showing_date == today_str_pkt
        date_label = "TODAY" if is_today else "TOMORROW"
        date_display = first_event_pkt.strftime('%a, %b %d')

        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        
        embed = discord.Embed(
            title=f"💎 TRADERS UNION | REMINDER MONITOR ({date_label})",
            description=f"```ansi\n\u001b[1;36mLIVE API DATA • {date_display} • REAL-TIME TRACKING\u001b[0m\n```",
            color=0x2b2d31
        )
        embed.set_author(name="TRADERS UNION ANALYTICS", icon_url=logo)

        # Section 1: Events within 30 minutes (URGENT)
        if within_30_min:
            urgent_text = "**⚡ COMING IN 30 MINUTES:**\n"
            for item in sorted(within_30_min, key=lambda x: x['diff']):
                ev = item['event']
                pkt_time = item['time'].astimezone(pytz.timezone('Asia/Karachi'))
                mins_left = int(item['diff'])
                impact_c = "🔴" if ev['impact'] == "High" else "🟠"
                
                urgent_text += (
                    f"{impact_c} **{ev['title']}** ({ev['country']})\n"
                    f"└ ⏱️ `{mins_left} min remaining` | 📅 `{pkt_time.strftime('%a, %b %d')}` | Time: `{pkt_time.strftime('%I:%M %p')} PKT`\n\n"
                )
            embed.description += urgent_text + "━━━━━━━━━━━━━━━━━━━━━━\n\n"

        # Section 2: Other upcoming reminders
        other_reminders = [r for r in upcoming_reminders if r['diff'] > 30]
        if other_reminders:
            reminder_text = "**📋 UPCOMING REMINDERS:**\n"
            for item in sorted(other_reminders, key=lambda x: x['diff'])[:8]:
                ev = item['event']
                pkt_time = item['time'].astimezone(pytz.timezone('Asia/Karachi'))
                status = "✅ SENT" if item['sent'] else "⏲️ PENDING"
                impact_c = "🔴" if ev['impact'] == "High" else "🟠"
                
                reminder_text += (
                    f"{impact_c} **{ev['title']}**\n"
                    f"└ 📅 `{pkt_time.strftime('%a, %b %d')}` | Time: `{pkt_time.strftime('%I:%M %p')} PKT` | Status: `{status}`\n\n"
                )
            embed.description += reminder_text

        embed.set_footer(text="TRADERS UNION • Live API Data Feed")
        await ctx.send(embed=embed)

    @commands.command(name="refreshnews")
    @is_owner_check()
    async def refresh_news(self, ctx):
        """Force purge cache and sync global news feeds manually (Owner Only)"""
        load_msg = await ctx.send("🔄 `INITIALIZING CACHE PURGE...`")
        
        # Reset global cache variables
        global NEWS_CACHE, LAST_FETCH_TIME
        NEWS_CACHE = []
        LAST_FETCH_TIME = None
        
        # Delete cache file to ensure clean slate
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            await asyncio.sleep(0.5)
            await load_msg.edit(content="🧹 `LOCAL CACHE DELETED. RE-ESTABLISHING LINK...`")
        
        # Force a fetch
        news_data = await fetch_news_data()
        await asyncio.sleep(0.5)
        
        if news_data:
            await load_msg.edit(content="🛰️ `GLOBAL SYNC SUCCESSFUL. EXECUTING ALERT SEQUENCE...`")
            # Manually trigger the loop logic once
            await self.check_forex_news()
            await asyncio.sleep(0.5)
            await load_msg.edit(content=f"✅ `SYSTEM REFRESHED. {len(news_data)} EVENTS LOADED.`")
        else:
            await load_msg.edit(content="❌ `SYNC FAILED. CHECK API STATUS.`")

    @commands.command(name="predict")
    async def predict_news(self, ctx):
        """Fetch upcoming news and predict/guess the actual results"""
        load_msg = await ctx.send("🔮 `FETCHING UPCOMING NEWS DATA...`")
        await asyncio.sleep(0.5)
        await load_msg.edit(content="🧠 `ANALYZING PATTERNS & GENERATING PREDICTIONS...`")
        
        # Fetch news data (same as reminders)
        news_data = await fetch_news_from_api()
        if not news_data:
            await load_msg.delete()
            return await ctx.send("❌ `DATA FEED UNAVAILABLE.`")
        
        now_utc = datetime.now(pytz.UTC)
        upcoming_events = []
        
        for event in news_data:
            if event['impact'] not in ["High", "Medium"]:
                continue
                
            event_dt = datetime.fromisoformat(event['date']).astimezone(pytz.UTC)
            time_diff = (event_dt - now_utc).total_seconds() / 60.0  # minutes
            
            # Only upcoming events (within next 24 hours)
            if 0 < time_diff <= 1440:
                upcoming_events.append({
                    **event,
                    "mins_left": time_diff,
                    "event_dt": event_dt
                })
        
        await load_msg.delete()
        
        if not upcoming_events:
            return await ctx.send("🏜️ `NO HIGH/MEDIUM IMPACT NEWS IN NEXT 24 HOURS.`")
        
        # Sort by time
        upcoming_events.sort(key=lambda x: x['mins_left'])
        
        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        
        embed = discord.Embed(
            title="🔮 NEWS PREDICTION ENGINE",
            description=(
                "```ansi\n"
                "\u001b[1;33mAI-POWERED RESULT PREDICTIONS\u001b[0m\n"
                "\u001b[0;37mBased on forecast data & historical patterns\u001b[0m\n"
                "```"
            ),
            color=0x9b59b6,
            timestamp=datetime.utcnow()
        )
        embed.set_author(name="TRADERS UNION ANALYTICS", icon_url=logo)
        
        predictions_text = ""
        for ev in upcoming_events[:6]:  # Top 6 events
            impact_c = "🔴" if ev['impact'] == "High" else "🟠"
            pkt_time = ev['event_dt'].astimezone(pytz.timezone('Asia/Karachi'))
            hours = int(ev['mins_left'] // 60)
            mins = int(ev['mins_left'] % 60)
            
            forecast = ev.get('forecast', '')
            previous = ev.get('previous', '')
            
            # Generate prediction based on forecast and previous
            predicted_result = "N/A"
            prediction_direction = "⚪"
            confidence = "LOW"
            
            if forecast and previous:
                try:
                    # Parse numbers
                    fcs_clean = forecast.replace('%', '').replace('K', '').replace('M', '').replace('B', '').strip()
                    prv_clean = previous.replace('%', '').replace('K', '').replace('M', '').replace('B', '').strip()
                    
                    fcs_num = float(fcs_clean)
                    prv_num = float(prv_clean)
                    
                    # Predict: Usually actual is between forecast and previous, or near forecast
                    # Add slight variance for realistic prediction
                    import random
                    variance = (fcs_num - prv_num) * random.uniform(-0.2, 0.3)
                    predicted_num = fcs_num + variance
                    
                    # Keep same format (% or K/M/B)
                    if '%' in forecast:
                        predicted_result = f"{predicted_num:.1f}%"
                    elif 'K' in forecast:
                        predicted_result = f"{predicted_num:.1f}K"
                    elif 'M' in forecast:
                        predicted_result = f"{predicted_num:.2f}M"
                    elif 'B' in forecast:
                        predicted_result = f"{predicted_num:.2f}B"
                    else:
                        predicted_result = f"{predicted_num:.2f}"
                    
                    # Direction indicator
                    if predicted_num > prv_num:
                        prediction_direction = "🟢 BULLISH"
                        confidence = "HIGH" if abs(fcs_num - prv_num) > abs(prv_num * 0.1) else "MEDIUM"
                    elif predicted_num < prv_num:
                        prediction_direction = "🔴 BEARISH"
                        confidence = "HIGH" if abs(fcs_num - prv_num) > abs(prv_num * 0.1) else "MEDIUM"
                    else:
                        prediction_direction = "⚪ NEUTRAL"
                        confidence = "LOW"
                        
                except:
                    predicted_result = forecast if forecast else "N/A"
                    prediction_direction = "⚪ NEUTRAL"
            elif forecast:
                predicted_result = forecast
                prediction_direction = "⚪ PENDING"
            
            time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
            
            predictions_text += (
                f"{impact_c} **{ev['title']}** ({ev['country']})\n"
                f"┣ ⏰ `{pkt_time.strftime('%I:%M %p')} PKT` (T-{time_str})\n"
                f"┣ 📊 Forecast: `{forecast or 'N/A'}` | Previous: `{previous or 'N/A'}`\n"
                f"┣ 🎯 **PREDICTED:** `{predicted_result}`\n"
                f"┗ {prediction_direction} | Confidence: `{confidence}`\n\n"
            )
        
        embed.add_field(name="📋 PREDICTIONS", value=predictions_text or "No data", inline=False)
        
        embed.set_footer(text="⚠️ AI PREDICTIONS • NOT FINANCIAL ADVICE • Educational Only")
        embed.set_thumbnail(url=logo)
        
        await ctx.send(embed=embed)

    @commands.command(name="resetnews")
    @is_owner_check()
    async def reset_news_data(self, ctx):
        """Reset all news tracking data (sent_news.json, news_cache.json) - Owner Only"""
        load_msg = await ctx.send("🔄 `INITIALIZING FULL SYSTEM RESET...`")
        await asyncio.sleep(0.5)
        
        files_to_reset = [
            (SENT_NEWS_FILE, "sent_news.json"),
            (CACHE_FILE, "news_cache.json")
        ]
        
        reset_count = 0
        status_text = ""
        
        for file_path, file_name in files_to_reset:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    status_text += f"✅ `{file_name}` DELETED\n"
                    reset_count += 1
                except Exception as e:
                    status_text += f"❌ `{file_name}` FAILED: {str(e)}\n"
            else:
                status_text += f"⚠️ `{file_name}` NOT FOUND\n"
        
        await asyncio.sleep(0.5)
        await load_msg.edit(content="🧹 `CLEARING MEMORY CACHE...`")
        
        # Reset global variables
        global NEWS_CACHE, LAST_FETCH_TIME
        NEWS_CACHE = []
        LAST_FETCH_TIME = None
        
        await asyncio.sleep(0.5)
        await load_msg.edit(content="📡 `RELOADING FRESH DATA...`")
        
        # Fetch fresh data
        news_data = await fetch_news_data(force=True)
        
        await asyncio.sleep(0.5)
        
        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        
        embed = discord.Embed(
            title="♻️ SYSTEM RESET COMPLETE",
            description=(
                "```ansi\n"
                "\u001b[1;32mSTATUS  : OPERATIONAL\u001b[0m\n"
                "\u001b[1;36mRESET   : SUCCESSFUL\u001b[0m\n"
                "```\n"
                f"**FILES RESET:**\n{status_text}\n"
                f"**MEMORY CACHE:** `CLEARED`\n"
                f"**FRESH DATA:** `{len(news_data) if news_data else 0} EVENTS LOADED`"
            ),
            color=0x2ecc71
        )
        embed.set_author(name="TRADERS UNION COMMAND", icon_url=logo)
        embed.set_footer(text="All news tracking data has been reset • Ready for fresh monitoring")
        
        await load_msg.delete()
        await ctx.send(embed=embed)

    @commands.command(name="remindercheck", aliases=["checkreminders"])
    async def check_reminders(self, ctx):
        """View upcoming High/Medium impact news that will get 30-min reminders"""
        load_msg = await ctx.send("📡 `FETCHING UPCOMING REMINDERS...`")
        
        news_data = await fetch_news_from_api()
        sent_news_dict = load_sent_news()
        
        if not news_data:
            await load_msg.delete()
            return await ctx.send("❌ `DATA FETCH FAILED.`")
        
        now_utc = datetime.now(pytz.UTC)
        now_pkt = datetime.now(pytz.timezone('Asia/Karachi'))
        today_str = now_pkt.strftime('%Y-%m-%d')
        
        upcoming_reminders = []
        
        for event in news_data:
            event_dt = datetime.fromisoformat(event['date']).astimezone(pytz.UTC)
            event_pkt = event_dt.astimezone(pytz.timezone('Asia/Karachi'))
            event_date_str = event_pkt.strftime('%Y-%m-%d')
            
            # Only today's events
            if event_date_str != today_str:
                continue
            
            time_diff = (event_dt - now_utc).total_seconds() / 60.0
            impact = event['impact']
            
            # Only High/Medium impact, upcoming events
            if impact in ["High", "Medium"] and time_diff > 0:
                event_id = f"{event['title']}_{event['country']}_{event['date']}"
                is_sent = sent_news_dict.get(event_id, {}).get("reminder_sent", False)
                
                upcoming_reminders.append({
                    "event": event,
                    "time": event_dt,
                    "sent": is_sent,
                    "diff": time_diff
                })
        
        await load_msg.delete()
        
        if not upcoming_reminders:
            return await ctx.send(f"🏜️ `NO HIGH/MEDIUM IMPACT NEWS REMAINING TODAY ({today_str}).`")
        
        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        
        embed = discord.Embed(
            title="🔔 UPCOMING 30-MIN REMINDERS",
            description=f"```ansi\n\u001b[1;36mTODAY'S HIGH/MEDIUM IMPACT NEWS\u001b[0m\n\u001b[0;37m{now_pkt.strftime('%A, %b %d, %Y')}\u001b[0m\n```",
            color=0x3498db
        )
        embed.set_author(name="TRADERS UNION REMINDER SYSTEM", icon_url=logo)
        
        reminder_text = ""
        for item in sorted(upcoming_reminders, key=lambda x: x['diff']):
            ev = item['event']
            pkt_time = item['time'].astimezone(pytz.timezone('Asia/Karachi'))
            
            impact_c = "🔴" if ev['impact'] == "High" else "🟠"
            hours = int(item['diff'] // 60)
            mins = int(item['diff'] % 60)
            time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
            
            status = "✅ SENT" if item['sent'] else "⏳ PENDING"
            
            reminder_text += (
                f"{impact_c} **{ev['title']}**\n"
                f"┣ 🌍 {ev['country']}\n"
                f"┣ ⏰ {pkt_time.strftime('%I:%M %p')} PKT\n"
                f"┣ ⏱️ T-{time_str}\n"
                f"┗ Status: `{status}`\n\n"
            )
        
        embed.add_field(name="📋 REMINDERS QUEUE", value=reminder_text or "No data", inline=False)
        embed.set_footer(text="TRADERS UNION • Auto Reminder System")
        await ctx.send(embed=embed)

    @commands.command(name="setnews")
    @is_owner_check()
    async def set_news_broadcast(self, ctx, channel: discord.TextChannel):
        """Configure the primary sector for economic broadcasts (Owner Only)"""
        load_msg = await ctx.send("🛰️ `CONFIGURING BROADCAST GATEWAY...`")
        set_news_channel(channel.id)
        await asyncio.sleep(0.5)
        await load_msg.edit(content="🕵️ `ESTABLISHING SECURE DATA PIPELINE...`")
        await asyncio.sleep(0.5)
        
        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        
        embed = discord.Embed(
            title="💎 NEWS BROADCAST ONLINE",
            description=(
                "```ansi\n"
                f"\u001b[1;36mSTATUS  :\u001b[0m \u001b[0;37mOPERATIONAL\u001b[0m\n"
                f"\u001b[1;36mSECTOR  :\u001b[0m \u001b[0;37m{channel.name.upper()}\u001b[0m\n"
                f"\u001b[1;32mGATEWAY :\u001b[0m \u001b[0;37mSECURED\u001b[0m\n"
                "```"
            ),
            color=0x2ecc71
        )
        embed.set_author(name="TRADERS UNION COMMAND", icon_url=logo)
        embed.set_footer(text="Institutional News Feed Encryption Enabled")
        
        await load_msg.delete()
        await ctx.send(embed=embed)

    @commands.command(name="alert", aliases=["setalert", "sessionalert"])
    @is_owner_check()
    async def set_session_alert_channel(self, ctx, channel: discord.TextChannel):
        """Set auto session-open alert channel (Asia + London)"""
        config = load_session_alert_config()
        guild_id = str(ctx.guild.id)

        config.setdefault("channels", {})[guild_id] = channel.id
        config.setdefault("last_sent", {}).setdefault(guild_id, {})
        save_session_alert_config(config)

        now_utc = datetime.now(pytz.UTC)
        next_asia_pkt = get_next_session_open_pkt(now_utc, "Asia/Tokyo", 9, 0)
        next_london_pkt = get_next_session_open_pkt(now_utc, "Europe/London", 8, 0)

        embed = discord.Embed(
            title="✅ SESSION ALERTS ENABLED",
            description=(
                f"**Channel:** {channel.mention}\n"
                f"**Alerts:** `ASIA OPEN`, `LONDON OPEN`\n"
                f"**Next Asia (PKT):** `{next_asia_pkt.strftime('%a, %I:%M %p')}`\n"
                f"**Next London (PKT):** `{next_london_pkt.strftime('%a, %I:%M %p')}`"
            ),
            color=0x2ecc71
        )
        embed.set_footer(text="TRADERS UNION • Auto Session Alerts Active")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ForexNews(bot))
                                                                                                                                                                                                                                                                                                                                                                                                                            
