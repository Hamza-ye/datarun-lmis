import { CanActivateFn, Router } from '@angular/router';
import { inject } from '@angular/core';
import { AuthService } from '../services/auth.service';

/**
 * Route guard that ensures the current actor has a specific role
 * before activating the route. 
 * Usage in app.routes.ts: `canActivate: [rbacGuard('system_admin')]`
 */
export const rbacGuard = (requiredRole: string): CanActivateFn => {
    return (route, state) => {
        const authService = inject(AuthService);
        const router = inject(Router);

        if (authService.hasRole(requiredRole)) {
            return true;
        }

        console.warn(`RBAC Guard Rejected: Missing role '${requiredRole}'`);
        // Redirect to a specialized unauthorized view or dashboard base
        return router.parseUrl('/unauthorized');
    };
};
