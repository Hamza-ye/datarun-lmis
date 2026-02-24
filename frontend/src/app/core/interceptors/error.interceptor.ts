import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { ErrorEnvelope } from '../models/error-envelope.dto';

/**
 * Functional HTTP Interceptor that globally intercepts failed responses,
 * unwraps our standardized `ErrorEnvelope`, and routes it to a notification
 * service or logs the `correlation_id`.
 */
export const errorInterceptor: HttpInterceptorFn = (req, next) => {
    return next(req).pipe(
        catchError((error: HttpErrorResponse) => {
            let errorMsg = 'An unknown error occurred!';
            let correlationId = 'N/A';
            let errorCode = 'UNKNOWN';

            if (error.error instanceof ErrorEvent) {
                // Client-side or network error
                errorMsg = `Network Error: ${error.error.message}`;
            } else {
                // Backend returned an unsuccessful response code
                if (error.error && error.error.error_code) {
                    const env = error.error as ErrorEnvelope;
                    errorCode = env.error_code;
                    errorMsg = typeof env.detail === 'string' ? env.detail : JSON.stringify(env.detail);
                    correlationId = env.correlation_id || 'N/A';
                } else {
                    // Unhandled generic HTTP error
                    errorMsg = `HTTP ${error.status}: ${error.message}`;
                }
            }

            console.error(`[Global Error] Code: ${errorCode} | CorrID: ${correlationId} | Msg: ${errorMsg}`);

            // We pass the parsed error so the local component can show specific form validation messages
            return throwError(() => error);
        })
    );
};
