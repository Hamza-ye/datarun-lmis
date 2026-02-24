import { Component, OnInit, ViewChild, inject } from '@angular/core';
import { CommonModule } from '@angular/common';

import { MatTableDataSource, MatTableModule } from '@angular/material/table';
import { MatPaginator, MatPaginatorModule } from '@angular/material/paginator';
import { MatSort, MatSortModule } from '@angular/material/sort';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';

import { KernelService } from '../../services/kernel.service';
import { CommodityRegistry } from '../../models/kernel.dto';

@Component({
  selector: 'app-commodity-dictionary',
  standalone: true,
  imports: [
    CommonModule,
    MatTableModule,
    MatPaginatorModule,
    MatSortModule,
    MatInputModule,
    MatFormFieldModule,
    MatIconModule
  ],
  templateUrl: './commodity-dictionary.html',
  styleUrls: ['./commodity-dictionary.scss']
})
export class CommodityDictionary implements OnInit {
  private kernelService = inject(KernelService);

  displayedColumns: string[] = ['item_id', 'name', 'base_unit', 'status'];
  dataSource: MatTableDataSource<CommodityRegistry>;

  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;

  constructor() {
    this.dataSource = new MatTableDataSource<CommodityRegistry>([]);
  }

  ngOnInit() {
    this.refreshData();
  }

  refreshData() {
    this.kernelService.getCommodities().subscribe({
      next: (data) => {
        this.dataSource = new MatTableDataSource(data);
        this.dataSource.paginator = this.paginator;
        this.dataSource.sort = this.sort;
      },
      error: (err) => {
        console.error('Failed to fetch commodities', err);
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
