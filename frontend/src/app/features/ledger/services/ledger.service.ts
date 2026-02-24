import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { LedgerCommand, StockBalanceResponse, LedgerHistoryResponse } from '../models/ledger.dto';

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
    getPendingApprovals(): Observable<any[]> {
        // In a full implementation, this could accept filters
        return this.http.get<any[]>('/api/ledger/gatekeeper/pending');
    }

    resolveApproval(id: string, action: 'APPROVE' | 'REJECT', comment: string): Observable<any> {
        return this.http.post(`/api/ledger/gatekeeper/${id}/resolve`, { action, comment });
    }
}
