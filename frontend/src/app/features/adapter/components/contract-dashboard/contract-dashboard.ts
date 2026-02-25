import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AdapterService } from '../../services/adapter.service';
import { MappingContract } from '../../models/adapter.dto';

@Component({
    selector: 'app-contract-dashboard',
    standalone: true,
    imports: [CommonModule],
    templateUrl: './contract-dashboard.html',
    styleUrls: ['./contract-dashboard.scss']
})
export class ContractDashboard implements OnInit {
    private adapterService = inject(AdapterService);

    contracts = signal<MappingContract[]>([]);
    isLoading = signal<boolean>(true);

    ngOnInit() {
        this.loadContracts();
    }

    loadContracts() {
        this.isLoading.set(true);
        this.adapterService.getContracts().subscribe({
            next: (data) => {
                this.contracts.set(data);
                this.isLoading.set(false);
            },
            error: (err) => {
                console.error('Failed to load contracts', err);
                this.isLoading.set(false);
            }
        });
    }

    activateVersion(contractId: string, version: string) {
        this.adapterService.activateContract(contractId, version).subscribe({
            next: () => this.loadContracts(),
            error: (err) => console.error('Failed to activate contract version', err)
        });
    }
}
