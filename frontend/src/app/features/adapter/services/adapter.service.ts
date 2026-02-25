import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { InboxPayload, AdapterInboxItem, DeadLetterQueueItem } from '../models/adapter.dto';

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
}
