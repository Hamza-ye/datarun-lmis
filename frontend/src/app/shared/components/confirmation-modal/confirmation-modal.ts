import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { MAT_DIALOG_DATA, MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatTooltipModule } from '@angular/material/tooltip';

export interface ConfirmationModalData {
  title: string;
  summaryText: string;
  mappedPayload?: any;             // Optional JSON object representation
  requireRbacAffirmation: boolean; // Forces user to click absolute checkbox
  dryRunSupported: boolean;        // Exposes Dry-Run shortcut
  idempotencyKey?: string;         // Pre-seeded GUID from parent form
}

export interface ConfirmationModalResult {
  action: 'submit_live' | 'submit_dry_run' | 'cancel';
  idempotencyKey: string;
}

@Component({
  selector: 'app-confirmation-modal',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatCheckboxModule,
    MatInputModule,
    MatFormFieldModule,
    MatTooltipModule
  ],
  templateUrl: './confirmation-modal.html',
  styleUrls: ['./confirmation-modal.scss']
})
export class ConfirmationModal {
  userConfirmed: boolean = false;
  localIdempotencyKey: string;

  constructor(
    public dialogRef: MatDialogRef<ConfirmationModal>,
    @Inject(MAT_DIALOG_DATA) public data: ConfirmationModalData
  ) {
    this.localIdempotencyKey = data.idempotencyKey || crypto.randomUUID();
  }

  regenerateKey() {
    this.localIdempotencyKey = crypto.randomUUID();
  }

  onCancel(): void {
    this.dialogRef.close({ action: 'cancel', idempotencyKey: this.localIdempotencyKey } as ConfirmationModalResult);
  }

  onDryRun(): void {
    this.dialogRef.close({ action: 'submit_dry_run', idempotencyKey: this.localIdempotencyKey } as ConfirmationModalResult);
  }

  onLiveSubmit(): void {
    if (this.data.requireRbacAffirmation && !this.userConfirmed) {
      return;
    }
    this.dialogRef.close({ action: 'submit_live', idempotencyKey: this.localIdempotencyKey } as ConfirmationModalResult);
  }
}
