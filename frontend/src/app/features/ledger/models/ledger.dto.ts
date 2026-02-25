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

export interface StagedCommandResponse {
    id: string;
    source_event_id: string;
    command_type: string;
    stage_reason: string;
    status: 'AWAITING' | 'APPROVED' | 'REJECTED';
    node_id: string;
    payload: any;
    created_at: string;
}

export interface ApprovalActionRequest {
    action: 'APPROVE' | 'REJECT';
    comment?: string;
}

export interface InTransitTransferResponse {
    transfer_id: string;
    source_node_id: string;
    dest_node_id: string;
    item_id: string;
    qty_shipped: number;
    qty_received: number;
    status: 'OPEN' | 'PARTIAL' | 'COMPLETED' | 'STALE_AUTO_CLOSED' | 'FAILED_AUTO_CLOSE' | 'LOST';
    dispatched_at: string;
    auto_close_after?: string;
    created_at: string;
    updated_at: string;
}

export interface ReceiveTransferRequest {
    qty_received: number;
    node_id: string;
    occurred_at: string;
    source_event_id: string;
}
