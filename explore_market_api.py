import asyncio
import aiohttp
import json

DNSE_API_KEY = "eyJvcmciOiJkbnNlIiwiaWQiOiJiZGEzNWQxYzA5YTg0ZmRlODljNTlhNmQ1YjcyNzljNCIsImgiOiJtdXJtdXIxMjgifQ=="
BASE_URL = "https://api.dnse.com.vn/market-api"

async def test_endpoint(session, endpoint, params=None):
    url = f"{BASE_URL}{endpoint}"
    headers = {"Authorization": f"Bearer {DNSE_API_KEY}"}
    async with session.get(url, headers=headers, params=params) as resp:
        text = await resp.text()
        print(f"\n{'='*60}")
        print(f"ENDPOINT: {endpoint}")
        print(f"PARAMS: {params}")
        print(f"STATUS: {resp.status}")
        # Handle unicode for Windows console
        safe_text = text.encode('ascii', 'replace').decode('ascii')
        print(f"RESPONSE: {safe_text[:5000]}")
        try:
            data = json.loads(text)
            safe_parsed = json.dumps(data, indent=2, ensure_ascii=True)[:3000]
            print(f"PARSED: {safe_parsed}")
        except:
            pass

async def main():
    async with aiohttp.ClientSession() as session:
        # Test tickers endpoint - this worked before
        await test_endpoint(session, "/tickers")
        
        # Try different endpoints for market data
        endpoints = [
            "/v1/stocks",
            "/v1/symbols",
            "/v1/history/daily",
            "/history/daily",
            "/price/history",
            "/chart/history",
            "/quotes",
            "/v1/quotes",
            "/market/stocks",
            "/v1/market/tickers",
            "/securities",
            "/v1/securities",
        ]
        
        for ep in endpoints:
            await test_endpoint(session, ep)
            
            # Also try with params
            if 'history' in ep or 'price' in ep or 'chart' in ep or 'quote' in ep:
                await test_endpoint(session, ep, {"symbol": "VNM", "from": "2024-01-01", "to": "2024-01-31"})
                await test_endpoint(session, ep, {"ticker": "VNM", "from": "2024-01-01", "to": "2024-01-31"})

if __name__ == "__main__":
    asyncio.run(main())