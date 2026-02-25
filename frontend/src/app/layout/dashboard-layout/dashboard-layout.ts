import { Component, inject, OnInit } from '@angular/core';
import { RouterOutlet, RouterModule } from '@angular/router';
import { CommonModule } from '@angular/common';

import { AuthService } from '../../core/services/auth.service';
import { TopologyService } from '../../core/services/topology.service';

@Component({
  selector: 'app-dashboard-layout',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    RouterModule
  ],
  templateUrl: './dashboard-layout.html',
  styleUrls: ['./dashboard-layout.scss']
})
export class DashboardLayout implements OnInit {
  authService = inject(AuthService);
  topologyService = inject(TopologyService);

  // Directly bind to the computed signal from the service
  actor = this.authService.currentActor;

  ngOnInit() {
    this.authService.loadContext().subscribe();
    this.topologyService.loadTopology().subscribe();
  }
}
