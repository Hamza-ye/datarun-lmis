import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';

import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

import { KernelService } from '../../services/kernel.service';
import { NodeTopologyCorrection } from '../../models/kernel.dto';
import { ErrorEnvelope } from '../../../../core/models/error-envelope.dto';

@Component({
  selector: 'app-topology-wizard',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatInputModule,
    MatFormFieldModule,
    MatButtonModule,
    MatIconModule
  ],
  templateUrl: './topology-wizard.html',
  styleUrls: ['./topology-wizard.scss'] // Reusing analogous styles from Inbox Form for MVP
})
export class TopologyWizard {
  private kernelService = inject(KernelService);

  correction = {
    nodeId: '',
    payload: {
      new_parent_id: '',
      effective_date: new Date().toISOString().split('T')[0] // today's date YYYY-MM-DD
    } as NodeTopologyCorrection
  };

  isSubmitting: boolean = false;
  result: { status: 'success' | 'error', details: any, correlation_id?: string } | null = null;

  previewCorrection() {
    this.result = null;
    this.isSubmitting = true;

    this.kernelService.applyTopologyCorrection(this.correction.nodeId, this.correction.payload).subscribe({
      next: (response) => {
        this.isSubmitting = false;
        this.result = {
          status: 'success',
          details: response
        };
      },
      error: (err: HttpErrorResponse) => {
        this.isSubmitting = false;

        // ErrorInterceptor unboxes ErrorEnvelope
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
