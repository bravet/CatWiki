/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Task = {
    task_type: string;
    status: string;
    progress?: number;
    job_id?: (string | null);
    site_id?: (number | null);
    id: number;
    tenant_id: number;
    payload?: (Record<string, any> | null);
    result?: (Record<string, any> | null);
    error?: (string | null);
    created_by: string;
    created_at: string;
    updated_at: string;
};

