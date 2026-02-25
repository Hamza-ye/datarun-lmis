import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { InboxPayload, AdapterInboxItem, DeadLetterQueueItem, MappingContract } from '../models/adapter.dto';

@Injectable({
    providedIn: 'root'
})
export class AdapterService {
    private http = inject(HttpClient);

    // --- Ingestion ---
    submitToInbox(payload: InboxPayload): Observable<any> {
        return this.http.post('/api/adapter/inbox', payload);
    }

    getInboxStatus(): Observable<AdapterInboxItem[]> {
        // Ideally paginated or filtered
        return this.http.get<AdapterInboxItem[]>('/api/adapter/inbox');
    }

    // --- Admin / Hardening ---
    getDeadLetterQueue(): Observable<DeadLetterQueueItem[]> {
        return this.http.get<DeadLetterQueueItem[]>('/api/adapter/admin/dlq');
    }

    replayDlq(id: string): Observable<any> {
        return this.http.post(`/api/adapter/admin/dlq/${id}/retry`, {});
    }

    getContracts(): Observable<MappingContract[]> {
        return this.http.get<MappingContract[]>('/api/adapter/admin/contracts');
    }

    activateContract(contractId: string, version: string): Observable<any> {
        return this.http.post(`/api/adapter/admin/contracts/${contractId}/versions/${version}/activate`, {});
    }

    getCrosswalks(namespace?: string): Observable<any[]> {
        const params: Record<string, string> = {};
        if (namespace) params['namespace'] = namespace;
        return this.http.get<any[]>('/api/adapter/admin/crosswalks', { params });
    }

    createCrosswalk(payload: { namespace: string, source_value: string, internal_id: string }): Observable<any> {
        return this.http.post('/api/adapter/admin/crosswalks', payload);
    }
}
