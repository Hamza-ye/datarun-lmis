import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AuthService } from '../../core/services/auth.service';

@Component({
    selector: 'app-header',
    standalone: true,
    imports: [CommonModule],
    templateUrl: './header.html',
    styleUrls: ['./header.scss']
})
export class Header {
    authService = inject(AuthService);
    actor = this.authService.currentActor;
}
