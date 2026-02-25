import { Component, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LedgerService } from '../../services/ledger.service';
import { InTransitTransferResponse } from '../../models/ledger.dto';
import { NodeNamePipe } from '../../../../shared/pipes/node-name.pipe';

@Component({
    selector: 'app-transfers-list',
    standalone: true,
    imports: [CommonModule, FormsModule, NodeNamePipe],
    templateUrl: './transfers-list.html',
    styleUrls: ['./transfers-list.scss']
})
export class TransfersList implements OnInit {
    private ledgerService = inject(LedgerService);

    public transfers = signal<InTransitTransferResponse[]>([]);
    public isLoading = signal<boolean>(true);

    // For the inline receive form
    public selectedTransfer = signal<InTransitTransferResponse | null>(null);
    public qtyReceived = signal<number>(0);

    ngOnInit() {
        this.refreshTransfers();
    }

    refreshTransfers() {
        this.isLoading.set(true);
        this.ledgerService.getTransfers().subscribe({
            next: (data) => {
                this.transfers.set(data);
                this.selectedTransfer.set(null);
                this.isLoading.set(false);
            },
            error: (err) => {
                console.error('Failed to load transfers', err);
                this.isLoading.set(false);
            }
        });
    }

    selectTransfer(transfer: InTransitTransferResponse) {
        this.selectedTransfer.set(transfer);
        // Suggest the remaining quantity to receive
        this.qtyReceived.set(transfer.qty_shipped - transfer.qty_received);
    }

    receiveStock() {
        const transfer = this.selectedTransfer();
        if (!transfer) return;

        this.ledgerService.receiveTransfer(transfer.transfer_id, {
            qty_received: this.qtyReceived(),
            node_id: transfer.dest_node_id,
            occurred_at: new Date().toISOString(),
            source_event_id: `ui-rcpt-${Date.now()}` // Mocking an idempotency UI key
        }).subscribe({
            next: () => {
                this.refreshTransfers();
            },
            error: (err) => console.error('Failed to receive transfer', err)
        });
    }
}
