import { Component, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AdapterService } from '../../services/adapter.service';
import { DeadLetterQueueItem } from '../../models/adapter.dto';

@Component({
    selector: 'app-dlq-dashboard',
    standalone: true,
    imports: [CommonModule, FormsModule],
    templateUrl: './dlq-dashboard.html',
    styleUrls: ['./dlq-dashboard.scss']
})
export class DlqDashboard implements OnInit {
    private adapterService = inject(AdapterService);

    public items = signal<DeadLetterQueueItem[]>([]);
    public isLoading = signal<boolean>(true);
    public editingItem = signal<DeadLetterQueueItem | null>(null);
    public payloadEdit = signal<string>('');

    ngOnInit() {
        this.refreshQueue();
    }

    refreshQueue() {
        this.isLoading.set(true);
        this.editingItem.set(null);
        this.adapterService.getDeadLetterQueue().subscribe({
            next: (data) => {
                this.items.set(data);
                this.isLoading.set(false);
            },
            error: (err) => {
                console.error('Failed to load DLQ', err);
                this.isLoading.set(false);
            }
        });
    }

    startEdit(item: DeadLetterQueueItem) {
        this.editingItem.set(item);
        this.payloadEdit.set(JSON.stringify(item.payload, null, 2));
    }

    cancelEdit() {
        this.editingItem.set(null);
        this.payloadEdit.set('');
    }

    submitRetry() {
        const item = this.editingItem();
        if (!item) return;

        let parsedPayload: any;
        try {
            parsedPayload = JSON.parse(this.payloadEdit());
        } catch (e) {
            alert("Invalid JSON format");
            return;
        }

        this.adapterService.replayDlq(item.id, parsedPayload).subscribe({
            next: () => {
                this.refreshQueue();
            },
            error: (err) => console.error('Retry failed', err)
        });
    }
}
