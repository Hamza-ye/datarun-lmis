export interface ErrorEnvelope {
    error_code: string;
    detail: string | any;
    correlation_id?: string;
}
