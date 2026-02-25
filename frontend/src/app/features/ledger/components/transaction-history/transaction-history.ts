import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { LedgerService } from '../../services/ledger.service';
import { LedgerHistoryResponse } from '../../models/ledger.dto';
import { NodeNamePipe } from '../../../../shared/pipes/node-name.pipe';

@Component({
  selector: 'app-transaction-history',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule
  ],
  templateUrl: './transaction-history.html',
  styleUrls: ['./transaction-history.scss']
})
export class TransactionHistory implements OnInit {
  private ledgerService = inject(LedgerService);

  public searchNodeId = signal<string>('');
  public searchItemId = signal<string>('');

  public history = signal<LedgerHistoryResponse[]>([]);
  public isLoading = signal<boolean>(false);
  public hasSearched = signal<boolean>(false);

  ngOnInit() {
    // Blank on load, requiring explicit user input unlike the previous hardcoded version
  }

  refreshHistory() {
    const node = this.searchNodeId().trim();
    const item = this.searchItemId().trim();

    if (!node || !item) {
      alert("Both Node UUID and Item ID are required to fetch an audit trail.");
      return;
    }

    this.isLoading.set(true);
    this.hasSearched.set(true);

    this.ledgerService.getHistory(node, item).subscribe({
      next: (data) => {
        this.history.set(data);
        this.isLoading.set(false);
      },
      error: (err) => {
        console.error('Failed to fetch transaction history', err);
        // Clear on 404/403
        this.history.set([]);
        this.isLoading.set(false);
      }
    });
  }
}
