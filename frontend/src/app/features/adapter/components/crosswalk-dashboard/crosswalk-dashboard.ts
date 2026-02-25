import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AdapterService } from '../../services/adapter.service';

@Component({
    selector: 'app-crosswalk-dashboard',
    standalone: true,
    imports: [CommonModule, FormsModule],
    templateUrl: './crosswalk-dashboard.html',
    styleUrls: ['./crosswalk-dashboard.scss']
})
export class CrosswalkDashboard implements OnInit {
    private adapterService = inject(AdapterService);

    crosswalks = signal<any[]>([]);
    isLoading = signal<boolean>(true);

    // Form State
    showForm = signal<boolean>(false);
    newNamespace = signal<string>('');
    newSourceValue = signal<string>('');
    newInternalId = signal<string>('');

    ngOnInit() {
        this.loadCrosswalks();
    }

    loadCrosswalks() {
        this.isLoading.set(true);
        this.adapterService.getCrosswalks().subscribe({
            next: (data) => {
                this.crosswalks.set(data);
                this.isLoading.set(false);
            },
            error: (err) => {
                console.error('Failed to load crosswalks', err);
                this.isLoading.set(false);
            }
        });
    }

    submitCrosswalk() {
        if (!this.newNamespace() || !this.newSourceValue() || !this.newInternalId()) return;

        this.adapterService.createCrosswalk({
            namespace: this.newNamespace(),
            source_value: this.newSourceValue(),
            internal_id: this.newInternalId()
        }).subscribe({
            next: () => {
                this.showForm.set(false);
                this.newNamespace.set('');
                this.newSourceValue.set('');
                this.newInternalId.set('');
                this.loadCrosswalks();
            },
            error: (err) => console.error('Failed to create crosswalk', err)
        });
    }
}
