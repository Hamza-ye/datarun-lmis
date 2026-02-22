# backend/app/adapter/worker.py
# This is the background task that reads from the INBOX and forwards out via HTTP.

def process_inbox():
    """
    1. Query adapter_inbox for status='RECEIVED'
    2. Extract and Cleanse via mapping_contracts
    3. Emit payload via HTTP POST to the configured destination
    4. Log the result in adapter_logs
    """
    pass
