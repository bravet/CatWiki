/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ModelConfig } from './ModelConfig';
/**
 * 更新 AI 配置
 */
export type AIConfigUpdate = {
    /**
     * 对话模型配置
     */
    chat?: (ModelConfig | null);
    /**
     * 向量模型配置
     */
    embedding?: (ModelConfig | null);
    /**
     * 重排序模型配置
     */
    rerank?: (ModelConfig | null);
    /**
     * 视觉模型配置
     */
    vl?: (ModelConfig | null);
};

