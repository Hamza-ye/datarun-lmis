import { Component, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AdapterService } from '../../services/adapter.service';
import { DeadLetterQueueItem } from '../../models/adapter.dto';

@Component({
    selector: 'app-dlq-dashboard',
    standalone: true,
    imports: [CommonModule],
    templateUrl: './dlq-dashboard.html',
    styleUrls: ['./dlq-dashboard.scss']
})
export class DlqDashboard implements OnInit {
    private adapterService = inject(AdapterService);

    public items = signal<DeadLetterQueueItem[]>([]);
    public isLoading = signal<boolean>(true);

    ngOnInit() {
        this.refreshQueue();
    }

    refreshQueue() {
        this.isLoading.set(true);
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

    retryItem(id: string) {
        this.adapterService.replayDlq(id).subscribe({
            next: () => {
                this.refreshQueue(); // Refresh to securely drop the item from the queue
            },
            error: (err) => console.error('Retry failed', err)
        });
    }
}
