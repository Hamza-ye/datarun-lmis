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
    correlation_id: string | null;
    source_system: string;
    error_message: string;
    payload: any;
    created_at: string;
}

export interface MappingContract {
    id: string;
    version: string;
    status: 'DRAFT' | 'ACTIVE' | 'DEPRECATED';
    created_at: string;
}
