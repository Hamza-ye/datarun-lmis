import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';

import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { AdapterService } from '../../services/adapter.service';
import { InboxPayload, MappingContract } from '../../models/adapter.dto';
import { ErrorEnvelope } from '../../../../core/models/error-envelope.dto';

@Component({
  selector: 'app-inbox-form',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatInputModule,
    MatFormFieldModule,
    MatSelectModule,
    MatSlideToggleModule,
    MatButtonModule,
    MatIconModule,
    MatTooltipModule
  ],
  templateUrl: './inbox-form.html',
  styleUrls: ['./inbox-form.scss']
})
export class InboxForm implements OnInit {
  private adapterService = inject(AdapterService);

  payload: Partial<InboxPayload> = {
    mapping_profile: '',
    source_system: 'manual_simulator',
    source_event_id: crypto.randomUUID(),
    dry_run: true
  };

  rawJsonInput: string = '{\n  "tracking_id": "test-sync-01",\n  "type": "RECEIPT",\n  "source_system": "DHIS2",\n  "destination_facility": "CLINIC_1",\n  "commodity_code": "AL_6x3",\n  "transaction_type": "PHYSICAL_COUNT",\n  "quantity": 500,\n  "occurred_at": "2026-02-25T12:00:00Z"\n}';
  jsonError: boolean = false;
  isSubmitting: boolean = false;

  result: { status: 'success' | 'error', details: any, correlation_id?: string } | null = null;
  contracts: MappingContract[] = [];

  ngOnInit() {
    this.adapterService.getContracts().subscribe({
      next: (data) => {
        // Only show active contracts in the dropdown
        this.contracts = data.filter(c => c.status === 'ACTIVE');
        if (this.contracts.length > 0) {
          this.payload.mapping_profile = this.contracts[0].id;
        }
      },
      error: (err) => console.error("Failed to load mapping contracts", err)
    });
  }

  generateId() {
    this.payload.source_event_id = crypto.randomUUID();
    this.result = null; // Clear previous results
  }

  submitPayload() {
    this.jsonError = false;
    this.result = null;
    let parsedPayload;

    try {
      parsedPayload = JSON.parse(this.rawJsonInput);
    } catch (e) {
      this.jsonError = true;
      return;
    }

    const finalPayload: InboxPayload = {
      mapping_profile: this.payload.mapping_profile!,
      source_system: this.payload.source_system,
      source_event_id: this.payload.source_event_id,
      dry_run: this.payload.dry_run,
      payload: parsedPayload
    };

    this.isSubmitting = true;

    this.adapterService.submitToInbox(finalPayload).subscribe({
      next: (response) => {
        this.isSubmitting = false;
        this.result = {
          status: 'success',
          details: response
        };
      },
      error: (err: HttpErrorResponse) => {
        this.isSubmitting = false;

        // ErrorInterceptor has already unboxed the ErrorEnvelope
        const env = err.error as ErrorEnvelope;
        this.result = {
          status: 'error',
          correlation_id: env.correlation_id,
          details: env.detail || env
        };
      }
    });
  }
}
