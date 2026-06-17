import asyncio
import aiohttp
import json

DNSE_API_KEY = "eyJvcmciOiJkbnNlIiwiaWQiOiJiZGEzNWQxYzA5YTg0ZmRlODljNTlhNmQ1YjcyNzljNCIsImgiOiJtdXJtdXIxMjgifQ=="
BASE_URL = "https://api.dnse.com.vn/chart-api"

async def test_endpoint(session, endpoint, params=None):
    url = f"{BASE_URL}{endpoint}"
    headers = {"Authorization": f"Bearer {DNSE_API_KEY}"}
    async with session.get(url, headers=headers, params=params) as resp:
        text = await resp.text()
        print(f"\n{'='*60}")
        print(f"ENDPOINT: {endpoint}")
        print(f"PARAMS: {params}")
        print(f"STATUS: {resp.status}")
        print(f"HEADERS: {dict(resp.headers)}")
        print(f"RESPONSE: {text[:3000]}")
        try:
            data = json.loads(text)
            print(f"PARSED JSON: {json.dumps(data, indent=2)[:3000]}")
        except:
            pass

async def main():
    headers = {"Authorization": f"Bearer {DNSE_API_KEY}"}
    async with aiohttp.ClientSession() as session:
        # Test tickers endpoint
        await test_endpoint(session, "/tickers")
        await test_endpoint(session, "/v1/tickers")
        
        # Test history daily
        await test_endpoint(session, "/v1/history/daily", {"ticker": "VNM", "from": "2024-01-01", "to": "2024-01-31"})
        await test_endpoint(session, "/history/daily", {"ticker": "VNM", "from": "2024-01-01", "to": "2024-01-31"})
        
        # Test reference
        await test_endpoint(session, "/v1/reference/tickers")
        await test_endpoint(session, "/reference/tickers")
        
        # Try other potential endpoints
        await test_endpoint(session, "/v1/stocks")
        await test_endpoint(session, "/stocks")

if __name__ == "__main__":
    asyncio.run(main())