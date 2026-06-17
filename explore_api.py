import asyncio
import aiohttp
import json

DNSE_API_KEY = "eyJvcmciOiJkbnNlIiwiaWQiOiJiZGEzNWQxYzA5YTg0ZmRlODljNTlhNmQ1YjcyNzljNCIsImgiOiJtdXJtdXIxMjgifQ=="
DNSE_API_SECRET = "YTdYtfzdkVRkUoEHuyW_XtAOJtc7AwF5XgpFpHrp51qn3hiFmGpaAwb5pj5f9lTrTa30T0DawPNrgshhiyE6JQ"

BASE_URLS = [
    "https://api.dnse.com.vn/market-api",
    "https://api.dnse.com.vn/price-api",
    "https://api.dnse.com.vn/chart-api",
    "https://api.dnse.com.vn/financial-product",
    "https://api.dnse.com.vn/user-service",
]

ENDPOINTS = [
    "/v1/reference/tickers",
    "/v1/history/daily?ticker=VNM&from=2024-01-01&to=2024-01-31",
    "/reference/tickers",
    "/history/daily?ticker=VNM&from=2024-01-01&to=2024-01-31",
    "/stocks",
    "/tickers",
    "/symbols",
    "/v1/symbols",
    "/v1/tickers",
    "/v1/stocks",
]

async def test_all():
    headers = {
        "Authorization": f"Bearer {DNSE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    async with aiohttp.ClientSession() as session:
        for base in BASE_URLS:
            print(f"\n{'#'*60}")
            print(f"TESTING BASE: {base}")
            print(f"{'#'*60}")
            
            for endpoint in ENDPOINTS:
                url = f"{base}{endpoint}"
                try:
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        text = await resp.text()
                        print(f"  {endpoint}: STATUS {resp.status}")
                        if resp.status == 200:
                            try:
                                data = json.loads(text)
                                print(f"    SUCCESS! Sample: {json.dumps(data, indent=2)[:800]}")
                            except:
                                print(f"    Response: {text[:500]}")
                        elif resp.status not in [404, 401, 403]:
                            print(f"    Response: {text[:300]}")
                except asyncio.TimeoutError:
                    print(f"  {endpoint}: TIMEOUT")
                except Exception as e:
                    print(f"  {endpoint}: ERROR - {e}")

if __name__ == "__main__":
    asyncio.run(test_all())