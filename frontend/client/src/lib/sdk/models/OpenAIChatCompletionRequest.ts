/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { app__schemas__chat__ChatMessage } from './app__schemas__chat__ChatMessage';
/**
 * 严格 OpenAI 兼容聊天请求（用于对外 Bot API）
 */
export type OpenAIChatCompletionRequest = {
    model: string;
    messages: Array<app__schemas__chat__ChatMessage>;
    temperature?: (number | null);
    top_p?: (number | null);
    'n'?: (number | null);
    stream?: (boolean | null);
    stop?: (string | Array<string> | null);
    max_tokens?: (number | null);
    presence_penalty?: (number | null);
    frequency_penalty?: (number | null);
    logit_bias?: (Record<string, number> | null);
    user?: (string | null);
    response_format?: (Record<string, any> | null);
    seed?: (number | null);
    tools?: null;
    tool_choice?: (string | Record<string, any> | null);
    stream_options?: (Record<string, any> | null);
    reasoning_effort?: (string | null);
    verbosity?: (string | null);
    serviceTier?: (string | null);
};

