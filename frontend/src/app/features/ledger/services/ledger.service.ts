import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { LedgerCommand, StockBalanceResponse, LedgerHistoryResponse, ApprovalActionRequest, StagedCommandResponse, InTransitTransferResponse, ReceiveTransferRequest } from '../models/ledger.dto';

@Injectable({
    providedIn: 'root'
})
export class LedgerService {
    private http = inject(HttpClient);

    // --- Area C: Write ---
    submitCommand(command: LedgerCommand): Observable<any> {
        return this.http.post('/api/ledger/commands', command);
    }

    // --- Read Models (Phase 9) ---
    getBalances(nodeId?: string): Observable<StockBalanceResponse[]> {
        const params: Record<string, string> = {};
        if (nodeId) params['node_id'] = nodeId;
        return this.http.get<StockBalanceResponse[]>('/api/ledger/balances', { params });
    }

    getHistory(nodeId: string, itemId: string): Observable<LedgerHistoryResponse[]> {
        return this.http.get<LedgerHistoryResponse[]>(`/api/ledger/history/${nodeId}/${itemId}`);
    }

    // --- Area E: Gatekeeper ---
    getPendingApprovals(nodeId?: string): Observable<StagedCommandResponse[]> {
        const params: Record<string, string> = {};
        if (nodeId) params['node_id'] = nodeId;
        return this.http.get<StagedCommandResponse[]>('/api/ledger/gatekeeper/staged', { params });
    }

    resolveApproval(id: string, payload: ApprovalActionRequest): Observable<any> {
        return this.http.post(`/api/ledger/gatekeeper/${id}/resolve`, payload);
    }

    // --- Area D: In-Transit ---
    getTransfers(nodeId?: string): Observable<InTransitTransferResponse[]> {
        const params: Record<string, string> = {};
        if (nodeId) params['node_id'] = nodeId;
        return this.http.get<InTransitTransferResponse[]>('/api/ledger/transfers', { params });
    }

    receiveTransfer(transferId: string, payload: ReceiveTransferRequest): Observable<any> {
        return this.http.post(`/api/ledger/transfers/${transferId}/receive`, payload);
    }
}
