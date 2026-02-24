import { Component, ViewChild, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { MatTableDataSource, MatTableModule } from '@angular/material/table';
import { MatPaginator, MatPaginatorModule } from '@angular/material/paginator';
import { MatSort, MatSortModule } from '@angular/material/sort';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';

import { LedgerService } from '../../services/ledger.service';
import { LedgerHistoryResponse } from '../../models/ledger.dto';

@Component({
  selector: 'app-transaction-history',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatTableModule,
    MatPaginatorModule,
    MatSortModule,
    MatInputModule,
    MatFormFieldModule,
    MatIconModule,
    MatButtonModule
  ],
  templateUrl: './transaction-history.html',
  styleUrls: ['./transaction-history.scss']
})
export class TransactionHistory {
  private ledgerService = inject(LedgerService);

  displayedColumns: string[] = ['source_event_id', 'transaction_type', 'quantity', 'running_balance', 'occurred_at', 'created_at'];
  dataSource = new MatTableDataSource<LedgerHistoryResponse>([]);

  searchNodeId: string = 'CLINIC_1'; // Seed with sample data
  searchItemId: string = 'AL_6x3';

  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;

  constructor() {
    this.refreshHistory(); // Optionally auto-fetch on load if seed data is provided
  }

  refreshHistory() {
    if (!this.searchNodeId || !this.searchItemId) return;

    this.ledgerService.getHistory(this.searchNodeId, this.searchItemId).subscribe({
      next: (data) => {
        // Results are typically descending from backend, but we ensure sorting is attached
        this.dataSource = new MatTableDataSource(data);
        setTimeout(() => {
          this.dataSource.paginator = this.paginator;
          this.dataSource.sort = this.sort;
        });
      },
      error: (err) => {
        console.error('Failed to fetch transaction history', err);
        this.dataSource.data = []; // Clear on error (e.g., 403 Forbidden)
      }
    });
  }
}
