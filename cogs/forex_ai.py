import discord
from discord.ext import commands
import aiohttp
import db

# Groq (OpenAI-compatible) API Configuration
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_DB_KEY = "secrets.groq_api_key"
GROQ_MODEL = "llama-3.1-8b-instant"

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

def _extract_json_obj(text: str) -> dict | None:
    """Best-effort extraction of a single JSON object from model output."""
    if not text:
        return None
    s = text.strip()
    # Try direct parse first.
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    # Try to find first {...} region.
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(s[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
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
            return db.get_raw(GROQ_DB_KEY)
        except Exception:
            return None

    async def ask_ai(self, question: str) -> str:
        """Send question to Groq API and get response"""
        api_key = self._get_groq_key()
        if not api_key:
            return "❌ AI key not configured. Owner: use `-aikey set <key>`."

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        
        # System prompt to keep AI focused on forex
        system_prompt = (
            "You are a professional forex trading expert and analyst.\n"
            "You ONLY answer questions about forex/trading: strategy, risk management, "
            "technical analysis, fundamentals, trading psychology, pairs (XAUUSD/EURUSD/etc), "
            "backtesting concepts, and execution.\n"
            "If the user asks anything outside forex/trading, refuse.\n\n"
            "Output MUST be a single JSON object with these keys:\n"
            "- answer: string (concise, practical, <= 300 words, include risk disclaimer if needed)\n"
            "- code_language: string (e.g. python, pinescript)\n"
            "- code: string (a small forex-useful snippet relevant to the question)\n"
            "No extra text outside JSON."
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
        db.set_raw(GROQ_DB_KEY, key.strip())
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
        db.delete_key(GROQ_DB_KEY)
        await ctx.send("✅ AI key cleared.")

    @commands.command(name="ask", aliases=["ai", "forex"])
    async def ask_forex(self, ctx, *, question: str):
        """Ask forex trading questions to AI (Forex topics only)"""
        
        # Check if question is forex-related
        if (not is_forex_related(question)) or is_offtopic(question):
            embed = discord.Embed(
                title="⚠️ NON-FOREX QUESTION DETECTED",
                description=(
                    "```ansi\n"
                    "\u001b[1;33mERROR  :\u001b[0m \u001b[0;37mOFF-TOPIC QUERY\u001b[0m\n"
                    "\u001b[1;36mALLOWED:\u001b[0m \u001b[0;37mFOREX TRADING ONLY\u001b[0m\n"
                    "```\n"
                    "This AI assistant only answers **forex trading** related questions.\n\n"
                    "**Valid topics:**\n"
                    "• Trading strategies & analysis\n"
                    "• Technical indicators (RSI, MACD, etc.)\n"
                    "• Risk management\n"
                    "• Currency pairs (EURUSD, XAUUSD, etc.)\n"
                    "• Chart patterns & price action\n"
                    "• Trading psychology\n"
                ),
                color=0xe74c3c
            )
            embed.set_footer(text="TRADERS UNION AI • Forex Expert System")
            return await ctx.send(embed=embed)
        
        # Send typing indicator
        async with ctx.typing():
            # Get response from Gemini AI
            raw = await self.ask_ai(question)

        parsed = _extract_json_obj(raw)
        if parsed:
            answer_text = str(parsed.get("answer", "")).strip()
            code_language = str(parsed.get("code_language", "text")).strip().lower() or "text"
            code_text = str(parsed.get("code", "")).strip()
        else:
            answer_text = str(raw or "").strip()
            code_language, code_text = _default_forex_code_snippet(question)

        if not code_text:
            code_language, code_text = _default_forex_code_snippet(question)
        if not answer_text:
            answer_text = "❌ Failed to generate an answer. Please try again."
        
        # Create response embed
        embed = discord.Embed(
            title="🤖 TRADERS UNION AI | FOREX EXPERT",
            description=f"**Your Question:**\n> {question}\n",
            color=0x2b2d31
        )

        # First codeblock: answer
        answer_block = f"```text\n{answer_text}\n```"
        if len(answer_block) > 1024:
            answer_block = f"```text\n{answer_text[:1000]}...\n```"
        embed.add_field(name="📊 Answer", value=answer_block, inline=False)

        # Second codeblock: forex code snippet
        code_block = f"```{code_language}\n{code_text}\n```"
        if len(code_block) > 1024:
            code_block = f"```{code_language}\n{code_text[:1000]}...\n```"
        embed.add_field(name="🧩 Forex Code", value=code_block, inline=False)
        
        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        embed.set_thumbnail(url=logo)
        embed.set_footer(text="⚠️ AI-Generated Response • Not Financial Advice • Educational Only")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ForexAI(bot))
