import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { tap, catchError, of } from 'rxjs';

/**
 * Represents the dictionary of Nodes loaded on startup.
 */
export interface NodeRegistryDto {
    node_id: string;
    node_name: string;
    type: string;
    parent_id?: string;
    status: string;
}

@Injectable({
    providedIn: 'root'
})
export class TopologyService {
    private http = inject(HttpClient);

    // Native Angular Signal holding the map of node_id -> NodeRegistryDto
    private nodesSignal = signal<Map<string, NodeRegistryDto>>(new Map());

    // Computed boolean indicator for whether the cache is loaded
    public isLoaded = computed(() => this.nodesSignal().size > 0);

    /**
     * Called on application bootstrap or lazily by the Pipe to populate the Signals.
     */
    loadTopology() {
        if (this.isLoaded()) {
            return of(true);
        }

        return this.http.get<NodeRegistryDto[]>('/api/kernel/nodes').pipe(
            tap(nodes => {
                const nodeMap = new Map<string, NodeRegistryDto>();
                nodes.forEach(node => nodeMap.set(node.node_id, node));
                this.nodesSignal.set(nodeMap);
            }),
            catchError(err => {
                console.error('Failed to load topology', err);
                return of(false);
            })
        );
    }

    /**
     * Resolves a node UUID string into a human-readable node_name string synchronously.
     * Guaranteed to use zero HTTP requests per call.
     */
    resolveName(nodeId: string): string {
        const nodeMap = this.nodesSignal();

        // If the map is empty, return "Loading..." or fallback to UUID until cache arrives.
        if (nodeMap.size === 0) {
            return nodeId;
        }

        const node = nodeMap.get(nodeId);
        return node ? node.node_name : `Unknown Node (${nodeId.substring(0, 8)}...)`;
    }
}
