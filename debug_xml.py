import aiohttp
import asyncio
import xml.etree.ElementTree as ET

async def main():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://www.forexfactory.com/"
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as response:
            text = await response.text()
            root = ET.fromstring(text)
            for event in root.findall('event')[:10]:
                print(f"Title: {event.find('title').text}")
                print(f"Date: {event.find('date').text}")
                print(f"Time: {event.find('time').text}")
                print("-" * 20)

if __name__ == "__main__":
    asyncio.run(main())
