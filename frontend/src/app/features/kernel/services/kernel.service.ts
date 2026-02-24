import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { NodeRegistry, CommodityRegistry, NodeTopologyCorrection } from '../models/kernel.dto';

@Injectable({
    providedIn: 'root'
})
export class KernelService {
    private http = inject(HttpClient);

    // --- Nodes ---
    getNodes(): Observable<NodeRegistry[]> {
        return this.http.get<NodeRegistry[]>('/api/kernel/nodes');
    }

    applyTopologyCorrection(nodeId: string, correction: NodeTopologyCorrection): Observable<{ message: string }> {
        return this.http.post<{ message: string }>(`/api/kernel/nodes/${nodeId}/topology-correction`, correction);
    }

    // --- Commodities ---
    getCommodities(): Observable<CommodityRegistry[]> {
        return this.http.get<CommodityRegistry[]>('/api/kernel/commodities');
    }

    // --- Policies ---
    getPolicies(): Observable<any[]> {
        return this.http.get<any[]>('/api/kernel/policies');
    }
}
