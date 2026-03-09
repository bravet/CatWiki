/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { VectorRetrieveFilter } from './VectorRetrieveFilter';
/**
 * 内部聊天接口请求（非 OpenAI 兼容）
 */
export type InternalChatCompletionRequest = {
    message: string;
    thread_id?: (string | null);
    temperature?: (number | null);
    stream?: (boolean | null);
    user?: (string | null);
    filter?: (VectorRetrieveFilter | null);
};

