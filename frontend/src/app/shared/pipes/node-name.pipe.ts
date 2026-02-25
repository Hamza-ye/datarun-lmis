import { Pipe, PipeTransform, inject } from '@angular/core';
import { TopologyService } from '../../core/services/topology.service';

/**
 * Pure Angular Pipe that takes a raw node_id UUID
 * and resolves it to a human-readable node name instantly from the Signal store cache.
 * 
 * Usage: 
 *   {{ transaction.source_node_id | nodeName }}
 */
@Pipe({
    name: 'nodeName',
    standalone: true,
    pure: false // Must be impure so it re-evaluates when the Signal cache resolves its HTTP call
})
export class NodeNamePipe implements PipeTransform {
    private topology = inject(TopologyService);

    transform(nodeId: string | null | undefined): string {
        if (!nodeId) return '';
        return this.topology.resolveName(nodeId);
    }
}
