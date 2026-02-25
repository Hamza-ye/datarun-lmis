import { Component, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LedgerService } from '../../services/ledger.service';
import { StagedCommandResponse } from '../../models/ledger.dto';
import { NodeNamePipe } from '../../../../shared/pipes/node-name.pipe';

@Component({
    selector: 'app-staged-inbox',
    standalone: true,
    imports: [CommonModule, FormsModule, NodeNamePipe],
    templateUrl: './staged-inbox.html',
    styleUrls: ['./staged-inbox.scss']
})
export class StagedInbox implements OnInit {
    private ledgerService = inject(LedgerService);

    public items = signal<StagedCommandResponse[]>([]);
    public isLoading = signal<boolean>(true);

    // For the inline approval form
    public selectedItem = signal<StagedCommandResponse | null>(null);
    public approvalComment = signal<string>('');

    ngOnInit() {
        this.refreshInbox();
    }

    refreshInbox() {
        this.isLoading.set(true);
        this.ledgerService.getPendingApprovals().subscribe({
            next: (data) => {
                this.items.set(data);
                this.selectedItem.set(null);
                this.isLoading.set(false);
            },
            error: (err) => {
                console.error('Failed to load pending approvals', err);
                this.isLoading.set(false);
            }
        });
    }

    selectItem(item: StagedCommandResponse) {
        this.selectedItem.set(item);
        this.approvalComment.set('');
    }

    resolveItem(action: 'APPROVE' | 'REJECT') {
        const item = this.selectedItem();
        if (!item) return;

        this.ledgerService.resolveApproval(item.id, {
            action: action,
            comment: this.approvalComment()
        }).subscribe({
            next: () => {
                this.refreshInbox();
            },
            error: (err) => console.error(`Failed to ${action} item`, err)
        });
    }
}
