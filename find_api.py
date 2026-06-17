import aiohttp
import asyncio
import re

async def find_api_in_html():
    async with aiohttp.ClientSession() as session:
        async with session.get('https://dnse.com.vn', timeout=aiohttp.ClientTimeout(total=10)) as resp:
            text = await resp.text()
            # Look for API URLs in the HTML
            patterns = [
                r'https?://[^\"\'<>]*(?:api|graphql|query)[^\"\'<>]*',
                r'api\.[^\"\'<>]+',
                r'\"api[^\"\'<>]*',
                r'\"baseUrl[^\"\'<>]*',
            ]
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    print(f'Pattern {pattern}: {matches[:10]}')
            
            # Also look for script tags with src
            script_pattern = r'<script[^>]*src=["\']([^"\']+)["\']'
            scripts = re.findall(script_pattern, text, re.IGNORECASE)
            print(f'Scripts: {scripts[:20]}')

asyncio.run(find_api_in_html())