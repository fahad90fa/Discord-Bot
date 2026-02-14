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
        system_prompt = """You are a professional forex trading expert and analyst. 
You provide clear, accurate, and educational information about forex trading.
Keep your responses concise (under 300 words), practical, and focused on forex trading only.
If asked about non-forex topics, politely decline and redirect to forex topics.
Use professional trading terminology and provide actionable insights when relevant.
Always include risk disclaimers when discussing trading strategies."""
        
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
        if not is_forex_related(question):
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
            response = await self.ask_ai(question)
        
        # Create response embed
        embed = discord.Embed(
            title="🤖 TRADERS UNION AI | FOREX EXPERT",
            description=f"**Your Question:**\n> {question}\n",
            color=0x2b2d31
        )
        
        # Split response if too long for single field
        if len(response) > 1024:
            # Split into chunks
            chunks = [response[i:i+1024] for i in range(0, len(response), 1024)]
            for i, chunk in enumerate(chunks[:3]):  # Max 3 chunks
                embed.add_field(
                    name=f"📊 Response (Part {i+1})" if len(chunks) > 1 else "📊 Response",
                    value=chunk,
                    inline=False
                )
        else:
            embed.add_field(name="📊 Response", value=response, inline=False)
        
        logo = "https://images-ext-1.discordapp.net/external/jzyE2BnHgBbYMApzoz6E48_5VB46NerYCJWkERJ6c-U/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1461756969231585470/51750d5207fa64a0a6f3f966013c8c9e.webp?format=webp&width=441&height=441"
        embed.set_thumbnail(url=logo)
        embed.set_footer(text="⚠️ AI-Generated Response • Not Financial Advice • Educational Only")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ForexAI(bot))
