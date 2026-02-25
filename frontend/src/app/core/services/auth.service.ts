import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap, catchError, of } from 'rxjs';
import { ActorContext } from '../models/actor-context.dto';

@Injectable({
    providedIn: 'root'
})
export class AuthService {
    private http = inject(HttpClient);

    // State Management: Native Angular 19+ Signal
    private currentActorSignal = signal<ActorContext | null>(null);

    // Read-only computed signal exposed to the UI
    public currentActor = computed(() => this.currentActorSignal());

    // For MVP/Testing: we hardcode a mock token or read from localStorage
    private readonly TOKEN_KEY = 'lmis_token';

    constructor() {
        // Default to system admin for testing if no token exists
        if (!this.getToken()) {
            this.setToken('mock_system_admin_token');
        }
    }

    getToken(): string | null {
        return localStorage.getItem(this.TOKEN_KEY);
    }

    setToken(token: string): void {
        localStorage.setItem(this.TOKEN_KEY, token);
    }

    clearToken(): void {
        localStorage.removeItem(this.TOKEN_KEY);
        this.currentActorSignal.set(null);
    }

    /**
     * Fetches the ActorContext from the backend based on the current JWT.
     * Keeps RxJS purely for the HTTP stream, but updates the Signal.
     */
    loadContext(): Observable<ActorContext | null> {
        return this.http.get<ActorContext>('/api/auth/me').pipe(
            tap(actor => this.currentActorSignal.set(actor)),
            catchError(err => {
                console.error('Failed to load auth context', err);
                this.currentActorSignal.set(null);
                return of(null);
            })
        );
    }

    hasRole(role: string): boolean {
        const actor = this.currentActorSignal();
        return actor ? actor.roles.includes(role) : false;
    }
}
