/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ChatCompletionResponse } from '../models/ChatCompletionResponse';
import type { InternalChatCompletionRequest } from '../models/InternalChatCompletionRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class ChatService {
    constructor(public readonly httpRequest: BaseHttpRequest) {}
    /**
     * Create Chat Completion
     * 创建聊天补全（内部接口，非 OpenAI 兼容）
     * @returns ChatCompletionResponse Successful Response
     * @throws ApiError
     */
    public createChatCompletion({
        requestBody,
        origin,
        referer,
    }: {
        requestBody: InternalChatCompletionRequest,
        origin?: (string | null),
        referer?: (string | null),
    }): CancelablePromise<ChatCompletionResponse> {
        return this.httpRequest.request({
            method: 'POST',
            url: '/v1/chat/completions',
            headers: {
                'origin': origin,
                'referer': referer,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
