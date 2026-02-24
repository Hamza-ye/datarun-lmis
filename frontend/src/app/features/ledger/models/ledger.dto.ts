export type TransactionType = 'RECEIPT' | 'ISSUE' | 'DISPATCH' | 'ADJUSTMENT' | 'STOCK_COUNT' | 'LOSS_IN_TRANSIT' | 'REVERSAL';

export interface LedgerCommand {
    source_system: string;
    source_event_id: string;
    transaction_type: TransactionType;
    node_id: string;
    item_id: string;
    quantity: number;
    occurred_at: string; // ISO 8601 date-time string
    target_node_id?: string | null;
    transfer_id?: string | null;
    version_timestamp?: number | null;
}

export interface StockBalanceResponse {
    node_id: string;
    item_id: string;
    quantity: number;
    last_updated: string;
}

export interface LedgerHistoryResponse {
    source_event_id: string;
    transaction_type: TransactionType;
    node_id: string;
    item_id: string;
    quantity: number;
    running_balance: number;
    occurred_at: string;
    created_at: string;
}
