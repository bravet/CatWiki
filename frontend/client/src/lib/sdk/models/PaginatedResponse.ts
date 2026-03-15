/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PaginationInfo } from './PaginationInfo';
/**
 * 通用分页响应数据模型
 */
export type PaginatedResponse = {
    /**
     * 数据列表
     */
    list: Array<any>;
    /**
     * 分页信息
     */
    pagination: PaginationInfo;
};

