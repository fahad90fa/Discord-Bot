import discord
from discord.ext import commands
import aiohttp
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Gemini API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

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

    async def ask_ai(self, question: str) -> str:
        """Send question to Gemini API and get response"""
        if not GEMINI_API_KEY:
            return "❌ API key not configured. Please contact the bot owner."
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {
            "Content-Type": "application/json"
        }
        
        # System prompt to keep AI focused on forex
        system_prompt = """You are a professional forex trading expert and analyst. 
You provide clear, accurate, and educational information about forex trading.
Keep your responses concise (under 300 words), practical, and focused on forex trading only.
If asked about non-forex topics, politely decline and redirect to forex topics.
Use professional trading terminology and provide actionable insights when relevant.
Always include risk disclaimers when discussing trading strategies."""
        
        data = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{system_prompt}\n\nUser question: {question}"}
                    ]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": 500
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result["candidates"][0]["content"]["parts"][0]["text"]
                    else:
                        error_text = await response.text()
                        print(f"Gemini API Error: {response.status} - {error_text}")
                        return "❌ Failed to get response from AI. Please try again later."
        except Exception as e:
            print(f"Error calling Gemini API: {e}")
            return "❌ An error occurred while processing your request."

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
