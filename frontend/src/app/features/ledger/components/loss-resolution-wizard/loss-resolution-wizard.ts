import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

import { LedgerCommand } from '../../models/ledger.dto';

@Component({
  selector: 'app-loss-resolution-wizard',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatInputModule,
    MatFormFieldModule,
    MatButtonModule,
    MatIconModule
  ],
  templateUrl: './loss-resolution-wizard.html',
  styleUrls: ['./loss-resolution-wizard.scss'] // Re-using standard form scss
})
export class LossResolutionWizard {

  resolution = {
    transfer_id: '',
    node_id: '',
    item_id: ''
  };

  isSubmitting: boolean = false;
  result: { details: LedgerCommand } | null = null;

  simulateResolution() {
    this.isSubmitting = true;

    // Simulate API Roundtrip delay
    setTimeout(() => {
      // Construct the strict DTO needed to satisfy Backend constraints Phase 14
      const mockCommand: LedgerCommand = {
        source_system: 'manual_resolution_ui',
        source_event_id: crypto.randomUUID(), // New Idempotency key for the resolution event
        transaction_type: 'LOSS_IN_TRANSIT',
        node_id: this.resolution.node_id,
        item_id: this.resolution.item_id,
        quantity: 0, // MUST BE ZERO for accountability events
        occurred_at: new Date().toISOString(),
        transfer_id: this.resolution.transfer_id
        // target_node_id omitted as per LOSS_IN_TRANSIT rule set
      };

      this.result = {
        details: mockCommand
      };

      this.isSubmitting = false;
    }, 400);
  }
}
