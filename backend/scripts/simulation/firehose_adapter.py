import argparse
import asyncio
import datetime
import random
import uuid

import httpx

API_URL = "http://localhost:8001"
# In MVP auth, the router expects the static string token. We ensure we pass the right mocked token if using that system,
# or we use real JWTs if we've switched. For now, testing endpoints usually expect mocked strings or no-ops depending on setup.
# test_routers mapped external to "mock_external_system_token". So we'll use that.
HEADERS = {"Authorization": "Bearer mock_external_system_token"}

def generate_random_event(event_type: str = None) -> dict:
    """Generates a messy, unstructured JSON payload representing a mobile device submission."""
    
    types = ["RECEIPT", "ISSUE", "STOCK_COUNT"]
    selected_type = event_type if event_type else random.choice(types)
    
    clinics = ["CLINIC_A", "CLINIC_B", "DIST_N", "HQ"]
    items = ["AMOX_250", "PARA_500"]
    
    # Generate random date in past 7 days
    days_ago = random.randint(0, 7)
    occurred_at = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)).isoformat()
    
    # Simulate DHIS2/CommCare pushing a nested structure
    return {
        "source_system": "FIREHOSE_SIM",
        "mapping_profile": "FIREHOSE_V1",
        "source_event_id": f"SIM_{uuid.uuid4().hex[:8]}",
        "payload": {
            "metadata": {
                "device_id": "Android_123",
                "app_version": "v1.4.2"
            },
            "data": {
                "clinic_code": random.choice(clinics),
                "timestamp": occurred_at,
                "entries": [
                    {
                        "transaction_type": selected_type,
                        "item_code": random.choice(items),
                        "quantity": str(random.randint(10, 500)), # E.g., coming in as string from mobile
                        "pack_size": random.choice([1, 10, 100]), # The pipeline will multiply this
                        "event_uuid": str(uuid.uuid4())
                    },
                    {
                        "transaction_type": selected_type,
                        "item_code": random.choice(items),
                        "quantity": str(random.randint(5, 50)),
                        "pack_size": 1,
                        "event_uuid": str(uuid.uuid4())
                    }
                ]
            }
        }
    }

async def trigger_firehose(count: int, event_type: str):
    print(f"Starting Firehose: Shooting {count} {event_type or 'MIXED'} events against {API_URL}/api/adapter/inbox...")
    
    success = 0
    failed = 0
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(count):
            payload = generate_random_event(event_type)
            
            try:
                # 1. Post to Adapter Inbox (Expected 202 Accepted)
                req_inbox = await client.post(f"{API_URL}/api/adapter/inbox", json=payload, headers=HEADERS)
                req_inbox.raise_for_status()
                inbox_id = req_inbox.json().get("inbox_id")
                
                print(f"[{i+1}/{count}] ✅ Successfully submitted event {payload['source_event_id']} to API.")
                success += 1
                
            except httpx.HTTPError as e:
                print(f"[{i+1}/{count}] ❌ Failed HTTP Request: {e}")
                if hasattr(e, 'response') and e.response is not None:
                     print(f"    Response text: {e.response.text}")
                failed += 1
            except Exception as e:
                print(f"[{i+1}/{count}] ❌ Unhandled Exception: {e}")
                failed += 1
                
    print(f"\nFirehose Complete! Success: {success}, Failed: {failed}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate external system pushing events into the LMIS Adapter.")
    parser.add_argument("--count", type=int, default=10, help="Number of payload bundles to send.")
    parser.add_argument("--type", type=str, choices=["RECEIPT", "ISSUE", "STOCK_COUNT", "ADJUSTMENT"], help="Force specific transaction type.")
    
    args = parser.parse_args()
    asyncio.run(trigger_firehose(args.count, args.type))
