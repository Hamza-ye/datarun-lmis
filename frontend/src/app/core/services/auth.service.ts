import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, tap, catchError, of } from 'rxjs';
import { ActorContext } from '../models/actor-context.dto';

@Injectable({
    providedIn: 'root'
})
export class AuthService {
    private http = inject(HttpClient);

    // We store the current actor context in a BehaviorSubject so components can react to changes
    private currentActorSubject = new BehaviorSubject<ActorContext | null>(null);
    public currentActor$ = this.currentActorSubject.asObservable();

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
        this.currentActorSubject.next(null);
    }

    /**
     * Fetches the ActorContext from the backend based on the current JWT.
     */
    loadContext(): Observable<ActorContext | null> {
        return this.http.get<ActorContext>('/api/auth/me').pipe(
            tap(actor => this.currentActorSubject.next(actor)),
            catchError(err => {
                console.error('Failed to load auth context', err);
                this.currentActorSubject.next(null);
                return of(null);
            })
        );
    }

    hasRole(role: string): boolean {
        const actor = this.currentActorSubject.value;
        return actor ? actor.roles.includes(role) : false;
    }
}
