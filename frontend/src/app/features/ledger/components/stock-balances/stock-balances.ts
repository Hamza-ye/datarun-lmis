import { Component, OnInit, ViewChild, inject } from '@angular/core';
import { CommonModule } from '@angular/common';

import { MatTableDataSource, MatTableModule } from '@angular/material/table';
import { MatPaginator, MatPaginatorModule } from '@angular/material/paginator';
import { MatSort, MatSortModule } from '@angular/material/sort';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';

import { LedgerService } from '../../services/ledger.service';
import { StockBalanceResponse } from '../../models/ledger.dto';

@Component({
  selector: 'app-stock-balances',
  standalone: true,
  imports: [
    CommonModule,
    MatTableModule,
    MatPaginatorModule,
    MatSortModule,
    MatInputModule,
    MatFormFieldModule,
    MatIconModule,
    MatButtonModule
  ],
  templateUrl: './stock-balances.html',
  styleUrls: ['./stock-balances.scss']
})
export class StockBalances implements OnInit {
  private ledgerService = inject(LedgerService);

  displayedColumns: string[] = ['node_id', 'item_id', 'quantity', 'last_updated'];
  dataSource: MatTableDataSource<StockBalanceResponse>;

  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;

  constructor() {
    // Initial empty source
    this.dataSource = new MatTableDataSource<StockBalanceResponse>([]);
  }

  ngOnInit() {
    this.refreshData();
  }

  refreshData() {
    this.ledgerService.getBalances().subscribe({
      next: (data) => {
        this.dataSource = new MatTableDataSource(data);
        this.dataSource.paginator = this.paginator;
        this.dataSource.sort = this.sort;
      },
      error: (err) => {
        console.error('Failed to fetch stock balances', err);
      }
    });
  }

  applyFilter(event: Event) {
    const filterValue = (event.target as HTMLInputElement).value;
    this.dataSource.filter = filterValue.trim().toLowerCase();

    if (this.dataSource.paginator) {
      this.dataSource.paginator.firstPage();
    }
  }
}
