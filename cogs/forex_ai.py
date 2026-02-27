import discord
from discord.ext import commands
import aiohttp
import db
import re
import asyncio
import requests
import json
import base64
import io
from datetime import datetime

# Groq (OpenAI-compatible) API Configuration
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_DB_KEY = "secrets.groq_api_key"
GROQ_MODEL = "llama-3.1-8b-instant"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL = "moonshotai/kimi-k2.5"
NVIDIA_IMAGE_MODEL = "black-forest-labs/flux.1-schnell"
NVIDIA_API_KEY = "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"
NVIDIA_IMAGE_API_KEY = "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"
NVIDIA_FAST_MAX_TOKENS = 512
NVIDIA_FAST_MAX_CHARS = 2200
NVIDIA_IMAGE_SIZE = "512x512"

# Forex trading related keywords
FOREX_KEYWORDS = [
    "forex", "trading", "pip", "spread", "leverage", "margin", "lot", "position",
    "buy", "sell", "long", "short", "stop loss", "take profit", "risk", "trade",
    "chart", "candlestick", "support", "resistance", "trend", "indicator", "ema",
    "sma", "rsi", "macd", "fibonacci", "gold", "xauusd", "eurusd", "gbpusd",
    "pair", "currency", "broker", "mt4", "mt5", "analysis", "technical", 
    "fundamental", "price action", "scalping", "swing", "day trading", "strategy",
    "entry", "exit", "signal", "profit", "loss", "drawdown", "equity", "balance",
    "pending order", "market order", "limit order", "bullish", "bearish", "breakout"
]

def is_forex_related(text: str) -> bool:
    """Check if the question is related to forex trading"""
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in FOREX_KEYWORDS)

OFFTOPIC_KEYWORDS = [
    # Common non-forex topics users try to ask.
    "movie", "song", "lyrics", "anime", "game", "valorant", "pubg", "freefire",
    "politics", "election", "president", "religion", "dua", "hadith",
    "school", "assignment", "homework", "math", "chemistry", "physics",
    "girlfriend", "boyfriend", "relationship",
    "hack", "crack", "steal", "carding", "ddos",
]

def is_offtopic(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in OFFTOPIC_KEYWORDS)

CODE_REQUEST_RE = re.compile(
    r"\b(code|snippet|script|pinescript|pine|python|mt4|mt5|mql4|mql5|ea|indicator|bot)\b",
    re.IGNORECASE,
)

def wants_code(text: str) -> bool:
    return bool(CODE_REQUEST_RE.search(text or ""))

def strip_code_blocks(text: str) -> str:
    # Remove any triple-backtick blocks from model output if user didn't ask for code.
    return re.sub(r"```.*?```", "", text or "", flags=re.DOTALL).strip()

def _pip_size(symbol: str) -> float:
    s = (symbol or "").upper()
    if "XAU" in s or "GOLD" in s:
        return 0.1
    if s.endswith("JPY"):
        return 0.01
    return 0.0001

def _pip_value_per_lot_estimate(symbol: str, entry_price: float) -> float | None:
    s = (symbol or "").upper()
    if entry_price <= 0:
        return None

    # Standard lot assumptions (100,000 units for FX, 100 oz for XAUUSD).
    if "XAU" in s or "GOLD" in s:
        return 10.0
    if s.endswith("USD"):
        return 10.0
    if s.endswith("JPY"):
        # Approx for JPY quote pairs at current entry.
        return (100000 * 0.01) / entry_price
    return None

def _default_forex_code_snippet(question: str) -> tuple[str, str]:
    """Fallback code snippet (language, code)."""
    q = (question or "").lower()
    if "rsi" in q or "indicator" in q:
        return (
            "pinescript",
            "//@version=5\nindicator(\"RSI (Simple)\", overlay=false)\nlen = input.int(14, \"Length\")\nsrc = input.source(close, \"Source\")\nr = ta.rsi(src, len)\nplot(r, \"RSI\", color=color.new(color.aqua, 0))\nhline(70, \"Overbought\")\nhline(30, \"Oversold\")\n",
        )
    # Generic position size / risk calculator.
    return (
        "python",
        "def position_size(account_balance, risk_pct, stop_loss_pips, pip_value_per_lot):\n"
        "    \"\"\"Return lots for a trade given risk and stop-loss.\"\"\"\n"
        "    risk_amount = account_balance * (risk_pct / 100.0)\n"
        "    if stop_loss_pips <= 0 or pip_value_per_lot <= 0:\n"
        "        return 0\n"
        "    lots = risk_amount / (stop_loss_pips * pip_value_per_lot)\n"
        "    return round(lots, 2)\n\n"
        "# Example:\n"
        "# lots = position_size(1000, 1, 25, 10)  # balance, risk%, SL pips, $/pip per 1 lot\n"
        "# print(lots)\n",
    )

class ForexAI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_groq_key(self) -> str | None:
        try:
            row = db.execute(
                "SELECT value FROM ai_keys WHERE key_name = %s",
                (GROQ_DB_KEY,),
                fetchone=True
            )
            return row["value"] if row else None
        except Exception:
            return None

    def _get_nvidia_key(self) -> str | None:
        return NVIDIA_API_KEY

    def _get_nvidia_image_key(self) -> str | None:
        return NVIDIA_IMAGE_API_KEY

    def _nvidia_completion_sync(self, prompt: str) -> str:
        api_key = self._get_nvidia_key()
        if not api_key:
            return "❌ NVIDIA API key missing."
        invoke_url = f"{NVIDIA_BASE_URL}/chat/completions"
        stream = True

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "text/event-stream" if stream else "application/json",
            "Content-Type": "application/json",
        }
        payload = {
            "model": NVIDIA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": NVIDIA_FAST_MAX_TOKENS,
            "temperature": 0.70,
            "top_p": 1.00,
            "stream": stream,
            "chat_template_kwargs": {"thinking": False},
        }

        response = requests.post(invoke_url, headers=headers, json=payload, stream=stream, timeout=90)
        if response.status_code != 200:
            return f"❌ AI request failed: `{response.status_code} {response.text[:300]}`"

        if not stream:
            try:
                j = response.json()
                return j["choices"][0]["message"]["content"]
            except Exception:
                return "❌ Invalid AI response payload."

        chunks: list[str] = []
        char_count = 0
        for line in response.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8", errors="ignore").strip()
            if not decoded.startswith("data:"):
                continue
            data = decoded[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = ((obj.get("choices") or [{}])[0].get("delta") or {})
            content = delta.get("content")
            if content:
                chunks.append(content)
                char_count += len(content)
                # Early-stop for quick responses.
                if char_count >= NVIDIA_FAST_MAX_CHARS:
                    break
        try:
            response.close()
        except Exception:
            pass

        text = "".join(chunks).strip()
        return text or "No response generated."

    def _nvidia_image_sync(self, prompt: str) -> tuple[bytes | None, str | None]:
        api_key = self._get_nvidia_image_key()
        if not api_key:
            return None, "❌ NVIDIA API key missing."

        invoke_url = f"{NVIDIA_BASE_URL}/images/generations"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {
            "model": NVIDIA_IMAGE_MODEL,
            "prompt": prompt,
            "size": NVIDIA_IMAGE_SIZE,
            "response_format": "b64_json",
        }

        response = requests.post(invoke_url, headers=headers, json=payload, timeout=90)
        if response.status_code != 200:
            return None, f"❌ Image generation failed: `{response.status_code} {response.text[:300]}`"

        try:
            data = response.json()
            first = (data.get("data") or [{}])[0]
            b64 = first.get("b64_json")
            if b64:
                return base64.b64decode(b64), None
            url = first.get("url")
            if url:
                img_resp = requests.get(url, timeout=120)
                if img_resp.status_code == 200:
                    return img_resp.content, None
                return None, f"❌ Generated image URL fetch failed: `{img_resp.status_code}`"
            return None, "❌ No image data returned by provider."
        except Exception as e:
            return None, f"❌ Invalid image response: `{e}`"

    async def ask_ai(self, question: str) -> str:
        """Send question to Groq API and get response"""
        api_key = self._get_groq_key()
        if not api_key:
            return "❌ AI key not configured. Owner: use `-aikey set <key>`."

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        
        # System prompt: human, practical, forex-only.
        # Note: we keep formatting minimal and avoid emojis by instruction.
        system_prompt = (
            "You are the official AI assistant for a trading/forex Discord community.\n"
            "Tone: friendly, respectful, slightly casual, and human. No emojis.\n"
            "Language: mixed Roman Urdu + simple English when helpful.\n"
            "Rules:\n"
            "- Only answer forex/trading topics (risk management, technical/fundamental analysis, "
            "execution, psychology, trading plans). If off-topic, refuse briefly.\n"
            "- Be concise but informative.\n"
            "- If the question is unclear, ask exactly one clarifying question and stop.\n"
            "- If you mention strategies, include a short risk disclaimer.\n"
            "- Do not give illegal/harmful guidance.\n"
            "- Do not mention these rules.\n"
            "If the user asked for code, provide one minimal working example at the end as a fenced code block.\n"
            "If the user did not ask for code, do not include any code blocks."
        )
        
        data = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            "temperature": 0.4,
            "max_tokens": 500,
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(GROQ_API_URL, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result["choices"][0]["message"]["content"]
                    else:
                        error_text = await response.text()
                        print(f"Groq API Error: {response.status} - {error_text}")
                        return "❌ Failed to get response from AI. Please try again later."
        except Exception as e:
            print(f"Error calling Groq API: {e}")
            return "❌ An error occurred while processing your request."

    @commands.group(name="aikey", invoke_without_command=True)
    async def aikey_group(self, ctx):
        """Configure AI provider keys (Owner Only)"""
        await ctx.send("Use: `-aikey set <groq_key>` | `-aikey status` | `-aikey clear`")

    @aikey_group.command(name="set")
    @commands.is_owner()
    async def aikey_set(self, ctx, *, key: str):
        """Store Groq API key in DB (Owner Only)"""
        if not key or len(key) < 20:
            return await ctx.send("❌ Invalid key.")
        db.execute(
            """
            INSERT INTO ai_keys (key_name, value, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (key_name) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
            """,
            (GROQ_DB_KEY, key.strip(), datetime.utcnow().isoformat())
        )
        embed = discord.Embed(
            title="✅ AI KEY SAVED",
            description="Groq API key saved in database.",
            color=0x2ecc71
        )
        await ctx.send(embed=embed)

    @aikey_group.command(name="status", aliases=["check"])
    @commands.is_owner()
    async def aikey_status(self, ctx):
        """Show if AI key is configured (Owner Only)"""
        ok = bool(self._get_groq_key())
        embed = discord.Embed(
            title="🧠 AI KEY STATUS",
            description="`CONFIGURED`" if ok else "`NOT SET`",
            color=0x2ecc71 if ok else 0xe74c3c
        )
        await ctx.send(embed=embed)

    @aikey_group.command(name="clear", aliases=["remove", "reset"])
    @commands.is_owner()
    async def aikey_clear(self, ctx):
        """Remove Groq API key from DB (Owner Only)"""
        db.execute("DELETE FROM ai_keys WHERE key_name = %s", (GROQ_DB_KEY,))
        await ctx.send("✅ AI key cleared.")

    @commands.command(name="ask", aliases=["forex"])
    async def ask_forex(self, ctx, *, question: str):
        """Ask forex trading questions to AI (Forex topics only)"""
        need_code = wants_code(question)
        
        # Check if question is forex-related
        if (not is_forex_related(question)) or is_offtopic(question):
            embed = discord.Embed(
                title="Non-Forex Question",
                description=(
                    "I can only help with forex and trading questions.\n\n"
                    "Example topics:\n"
                    "1. Strategy and analysis\n"
                    "2. Indicators (RSI, MACD, etc.)\n"
                    "3. Risk management and position sizing\n"
                    "4. Pairs (XAUUSD, EURUSD, etc.)\n"
                    "5. Price action and chart structure\n"
                ),
                color=0xe74c3c
            )
            embed.set_footer(text="Traders Union AI")
            return await ctx.send(embed=embed)
        
        # Send typing indicator
        async with ctx.typing():
            raw = await self.ask_ai(question)

        answer_text = (raw or "").strip()
        code_language = None
        code_text = None

        if not need_code:
            answer_text = strip_code_blocks(answer_text)
        else:
            # If model didn't include a code block, add a fallback minimal snippet.
            if "```" not in answer_text:
                code_language, code_text = _default_forex_code_snippet(question)
                answer_text = (answer_text + "\n\n" + f"```{code_language}\n{code_text}\n```").strip()

        if not answer_text:
            answer_text = "I couldn't generate a good answer right now. Try again in a minute."
        
        # Create response embed
        embed = discord.Embed(
            title="Traders Union AI | Forex",
            description=f"Question:\n{question}",
            color=0x2b2d31
        )

        # Keep output natural. If code is included, it will be in a single fenced block at the end.
        if len(answer_text) > 3500:
            answer_text = answer_text[:3490] + "..."
        embed.add_field(name="Answer", value=answer_text, inline=False)
        
        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        embed.set_thumbnail(url=logo)
        embed.set_footer(text="Educational only. Trading involves risk.")
        
        await ctx.send(embed=embed)

    @commands.command(name="say")
    async def say_message(self, ctx, *, message: str):
        """Repeat a message as bot, delete user command, block ping abuse."""
        lowered = (message or "").lower()

        has_everyone_or_here = ("@everyone" in lowered) or ("@here" in lowered)
        has_role_ping = bool(ctx.message.role_mentions) or bool(re.search(r"<@&\d+>", message or ""))

        if has_everyone_or_here or has_role_ping:
            return await ctx.send("❌ `@everyone`, `@here`, and role pings are not allowed in `say`.")

        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        await ctx.send(
            message,
            allowed_mentions=discord.AllowedMentions.none()
        )

    @commands.command(name="addroleicon", aliases=["roleicon"])
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def add_role_icon(self, ctx, role_id: int, emoji: str):
        """Set role icon. Usage: -addroleicon <role_id> <emoji>"""
        role = ctx.guild.get_role(role_id)
        if not role:
            return await ctx.send(embed=discord.Embed(description="❌ Role not found. Check role ID.", color=0xe74c3c))

        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send(embed=discord.Embed(description="❌ You can only edit roles below your top role.", color=0xe74c3c))
        if role >= ctx.guild.me.top_role:
            return await ctx.send(embed=discord.Embed(description="❌ I can only edit roles below my top role.", color=0xe74c3c))

        icon_payload = None
        emoji = (emoji or "").strip()

        # Custom emoji support: <:name:id> or <a:name:id>
        m = re.fullmatch(r"<a?:\w+:(\d+)>", emoji)
        if m:
            emoji_id = int(m.group(1))
            custom_emoji = ctx.bot.get_emoji(emoji_id)
            if not custom_emoji:
                return await ctx.send(embed=discord.Embed(description="❌ Custom emoji not found.", color=0xe74c3c))
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(str(custom_emoji.url)) as resp:
                        if resp.status != 200:
                            return await ctx.send(embed=discord.Embed(description="❌ Failed to download custom emoji.", color=0xe74c3c))
                        icon_payload = await resp.read()
            except Exception:
                return await ctx.send(embed=discord.Embed(description="❌ Failed to process custom emoji.", color=0xe74c3c))
        else:
            # Unicode emoji (example: 😀)
            icon_payload = emoji

        try:
            await role.edit(display_icon=icon_payload, reason=f"Role icon set by {ctx.author} ({ctx.author.id})")
            await ctx.send(
                embed=discord.Embed(
                    title="✅ ROLE ICON UPDATED",
                    description=f"Role: `{role.name}` (`{role.id}`)",
                    color=0x2ecc71
                )
            )
        except discord.Forbidden:
            await ctx.send(embed=discord.Embed(description="❌ Missing permission to edit this role.", color=0xe74c3c))
        except discord.HTTPException as e:
            await ctx.send(embed=discord.Embed(description=f"❌ Failed to set role icon: `{e}`", color=0xe74c3c))

    @commands.command(name="pips", aliases=["pipcalc", "tradecalc"])
    async def pips_calculator(
        self,
        ctx,
        entry_price: float,
        exit_price: float,
        lot_size: float,
        symbol: str = "EURUSD",
        pip_value_per_lot: float = None
    ):
        """
        Calculate pip move and estimated P/L.
        Usage: -pips <entry> <exit> <lot_size> [symbol] [pip_value_per_lot]
        Example: -pips 1.08450 1.08700 0.50 EURUSD
        """
        if entry_price <= 0 or exit_price <= 0:
            return await ctx.send("❌ Entry and exit price must be greater than 0.")
        if lot_size <= 0:
            return await ctx.send("❌ Lot size must be greater than 0.")

        pair = symbol.upper().strip()
        pip_size = _pip_size(pair)
        signed_pips = (exit_price - entry_price) / pip_size
        moved_pips = abs(signed_pips)

        est_pip_value = pip_value_per_lot if pip_value_per_lot and pip_value_per_lot > 0 else _pip_value_per_lot_estimate(pair, entry_price)
        if not est_pip_value:
            est_pip_value = 10.0
            estimation_note = "Default $10/pip per 1.00 lot used (estimate)."
        elif pip_value_per_lot and pip_value_per_lot > 0:
            estimation_note = "Custom pip value per lot used."
        else:
            estimation_note = "Auto-estimated pip value per lot used."

        buy_pnl = signed_pips * est_pip_value * lot_size
        sell_pnl = -buy_pnl

        embed = discord.Embed(
            title="📈 PIP & PROFIT CALCULATOR",
            color=0x2b2d31
        )
        embed.add_field(
            name="Trade Input",
            value=(
                f"**Pair:** `{pair}`\n"
                f"**Entry:** `{entry_price}`\n"
                f"**Exit:** `{exit_price}`\n"
                f"**Lot Size:** `{lot_size}`"
            ),
            inline=False
        )
        embed.add_field(
            name="Pip Move",
            value=(
                f"**Moved:** `{moved_pips:.2f} pips`\n"
                f"**Direction:** `{'UP' if signed_pips > 0 else 'DOWN' if signed_pips < 0 else 'FLAT'}`"
            ),
            inline=False
        )
        embed.add_field(
            name="Estimated P/L",
            value=(
                f"**If BUY:** `${buy_pnl:,.2f}`\n"
                f"**If SELL:** `${sell_pnl:,.2f}`\n"
                f"**Pip Value/Lot:** `${est_pip_value:,.2f}`"
            ),
            inline=False
        )
        embed.set_footer(text=f"{estimation_note} Educational estimate only.")
        await ctx.send(embed=embed)

    @commands.group(name="ai", invoke_without_command=True)
    async def ai_group(self, ctx):
        """General AI commands"""
        await ctx.send("Use: `-ai ask <question>` or `-ai ask image: <prompt>`")

    @ai_group.command(name="ask")
    async def ai_ask(self, ctx, *, question: str):
        """Ask anything from AI (NVIDIA endpoint)"""
        is_image_mode = question.lower().startswith(("image:", "img:", "pic:"))
        image_prompt = question.split(":", 1)[1].strip() if is_image_mode and ":" in question else question.strip()

        if is_image_mode and not image_prompt:
            return await ctx.send("❌ Use: `-ai ask image: <prompt>`")

        status_text = "⚡ Generating image..." if is_image_mode else "⚡ Thinking..."
        status_msg = await ctx.send(status_text)

        async with ctx.typing():
            try:
                if is_image_mode:
                    image_bytes, img_err = await asyncio.to_thread(self._nvidia_image_sync, image_prompt)
                    if img_err:
                        return await status_msg.edit(content=img_err)
                    if not image_bytes:
                        return await status_msg.edit(content="❌ No image generated.")

                    file = discord.File(io.BytesIO(image_bytes), filename="ai-image.png")
                    embed = discord.Embed(
                        title="🖼️ AI IMAGE",
                        description=f"```text\n{image_prompt[:1000]}\n```",
                        color=0x2b2d31
                    )
                    embed.set_image(url="attachment://ai-image.png")
                    embed.set_footer(text=f"NVIDIA AI • Model: {NVIDIA_IMAGE_MODEL} • {NVIDIA_IMAGE_SIZE}")
                    try:
                        await status_msg.delete()
                    except Exception:
                        pass
                    return await ctx.send(embed=embed, file=file)

                answer = await asyncio.to_thread(self._nvidia_completion_sync, question)
            except Exception as e:
                answer = f"❌ AI request failed: `{e}`"

        if len(question) > 1000:
            question = question[:1000] + "..."
        if len(answer) > 3800:
            answer = answer[:3800] + "..."
        safe_question = question.replace("```", "'''" )
        safe_answer = answer.replace("```", "'''")

        embed = discord.Embed(
            title="🤖 AI ASK",
            color=0x2b2d31
        )
        q_block = f"```text\n{safe_question}\n```"
        if len(q_block) > 1024:
            clipped_q = safe_question[:1008] + "..."
            q_block = f"```text\n{clipped_q}\n```"
        embed.add_field(name="Question", value=q_block, inline=False)

        # Discord embed field value limit is 1024 chars.
        answer_chunks = [safe_answer[i:i + 980] for i in range(0, len(safe_answer), 980)] or ["No response generated."]
        for idx, chunk in enumerate(answer_chunks[:4], start=1):
            title = "Answer" if idx == 1 else f"Answer (Part {idx})"
            embed.add_field(name=title, value=f"```text\n{chunk}\n```", inline=False)
        if len(answer_chunks) > 4:
            embed.add_field(name="Answer (More)", value="Response truncated to fit Discord embed limits.", inline=False)

        embed.set_footer(text=f"NVIDIA AI • Model: {NVIDIA_MODEL} • Fast Mode")
        await status_msg.edit(content=None, embed=embed)

async def setup(bot):
    await bot.add_cog(ForexAI(bot))
