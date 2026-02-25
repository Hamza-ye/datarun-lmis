export interface InboxPayload {
    mapping_profile: string;   // e.g. "hf_receipt_902"
    dry_run?: boolean;         // true for preview, false for mutation
    source_system?: string;    // "dhis2_api"
    source_event_id?: string;  // Explicit idempotency key
    payload: any;
}

export interface AdapterInboxItem {
    id: string;
    mapping_id: string;
    mapping_version: string;
    status: 'RECEIVED' | 'MAPPED' | 'FORWARDED' | 'DLQ' | 'RETRY';
    received_at: string;
}

export interface DeadLetterQueueItem {
    id: string;
    inbox_id: string;
    error_reason: string;
    status: 'UNRESOLVED' | 'REPROCESSED';
    raw_payload_snapshot: any;
    created_at: string;
}
