import asyncio

import httpx


async def run():
    async with httpx.AsyncClient() as client:
        r = await client.get('http://localhost:8000/api/ledger/balances', headers={'Authorization': 'Bearer mock_supervisor_token'})
        print('BALANCES:', r.status_code, r.text)
        r2 = await client.get('http://localhost:8000/api/ledger/history/CLINIC_1/AL_6x3', headers={'Authorization': 'Bearer mock_supervisor_token'})
        print('HISTORY:', r2.status_code, r2.text)

if __name__ == "__main__":
    asyncio.run(run())
