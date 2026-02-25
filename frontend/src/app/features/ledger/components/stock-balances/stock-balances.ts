import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { LedgerService } from '../../services/ledger.service';
import { StockBalanceResponse } from '../../models/ledger.dto';
import { NodeNamePipe } from '../../../../shared/pipes/node-name.pipe';

@Component({
  selector: 'app-stock-balances',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    NodeNamePipe
  ],
  templateUrl: './stock-balances.html',
  styleUrls: ['./stock-balances.scss']
})
export class StockBalances implements OnInit {
  private ledgerService = inject(LedgerService);

  public balances = signal<StockBalanceResponse[]>([]);
  public isLoading = signal<boolean>(true);
  public searchTerm = signal<string>('');

  // Computed signal to instantly filter the table in memory
  public filteredBalances = computed(() => {
    const term = this.searchTerm().toLowerCase();
    const all = this.balances();
    if (!term) return all;

    return all.filter(b =>
      b.item_id.toLowerCase().includes(term) ||
      b.node_id.toLowerCase().includes(term)
    );
  });

  ngOnInit() {
    this.refreshData();
  }

  refreshData() {
    this.isLoading.set(true);
    this.ledgerService.getBalances().subscribe({
      next: (data) => {
        this.balances.set(data);
        this.isLoading.set(false);
      },
      error: (err) => {
        console.error('Failed to fetch stock balances', err);
        this.balances.set([]);
        this.isLoading.set(false);
      }
    });
  }
}
