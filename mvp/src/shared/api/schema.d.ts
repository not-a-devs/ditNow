// Generated from services/api/openapi.json. Do not edit.
export interface paths {
    "/api/v1/ai/campus/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Search Campus
         * @description 공개 시설 스냅샷 검색. LLM 생성·개인정보 질의·별도 로그인은 제공하지 않는다.
         */
        get: operations["search_campus_api_v1_ai_campus_search_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Health
         * @description Process liveness only. Does not assert database/authentication readiness.
         */
        get: operations["health_api_v1_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/public-campus": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Guides */
        get: operations["list_guides_api_v1_public_campus_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/public-campus/{record_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Guide */
        get: operations["get_guide_api_v1_public_campus__record_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Health
         * @description Process liveness only. Does not assert database/authentication readiness.
         */
        get: operations["health_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** CampusSearchData */
        CampusSearchData: {
            /** Found */
            found: boolean;
            /**
             * Generated
             * @default false
             * @constant
             */
            generated: false;
            /** Hits */
            hits: components["schemas"]["CampusSearchHit"][];
            /**
             * Mode
             * @default retrieval_only
             * @constant
             */
            mode: "retrieval_only";
            /**
             * Personal Data Access
             * @default false
             * @constant
             */
            personal_data_access: false;
            /**
             * Source
             * @default chatbot/data/facilities.json
             * @constant
             */
            source: "chatbot/data/facilities.json";
            /**
             * Source Notice
             * @default 기존 챗봇 시설 스냅샷이며 공식 출처와 최신성은 검증되지 않았습니다.
             */
            source_notice: string;
            /**
             * Verification
             * @default UNKNOWN
             * @constant
             */
            verification: "UNKNOWN";
        };
        /** CampusSearchHit */
        CampusSearchHit: {
            /** Building */
            building?: string | null;
            /** Category */
            category: string;
            /** Floor */
            floor?: string | null;
            /** Hours */
            hours?: string | null;
            /**
             * Matched By
             * @enum {string}
             */
            matched_by: "alias" | "fuzzy" | "keyword";
            /** Name */
            name: string;
            /** Room */
            room?: string | null;
            /** Score */
            score: number;
            /** Source Id */
            source_id: string;
            /** Text */
            text: string;
        };
        /**
         * ErrorCode
         * @enum {string}
         */
        ErrorCode: "VALIDATION" | "UNAUTHORIZED" | "FORBIDDEN" | "NOT_FOUND" | "CONFLICT" | "RATE_LIMITED" | "UNAVAILABLE" | "INTERNAL" | "HTTP_ERROR";
        /** ErrorResponse */
        ErrorResponse: {
            code: components["schemas"]["ErrorCode"];
            /** Field Errors */
            field_errors?: {
                [key: string]: string;
            } | null;
            /** Message */
            message: string;
            /** Request Id */
            request_id: string;
            /**
             * Retryable
             * @default false
             */
            retryable: boolean;
        };
        /** GuideSection */
        GuideSection: {
            /** Heading */
            heading: string;
            /** Paragraphs */
            paragraphs: string[];
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** HealthData */
        HealthData: {
            /**
             * Service
             * @constant
             */
            service: "ditnow-api";
            /**
             * Status
             * @constant
             */
            status: "ok";
        };
        /** PublicGuide */
        PublicGuide: {
            /**
             * Category
             * @enum {string}
             */
            category: "university" | "campus" | "disclosure" | "news" | "department";
            /**
             * Content Kind
             * @default EDITORIAL_PUBLIC_SUMMARY
             * @constant
             */
            content_kind: "EDITORIAL_PUBLIC_SUMMARY";
            /** Feature Ids */
            feature_ids: ("FR-WEB-001" | "FR-WEB-002" | "FR-WEB-003" | "FR-WEB-004" | "FR-DEPT-007" | "FR-DEPT-008")[];
            /** Id */
            id: string;
            /** Sections */
            sections: components["schemas"]["GuideSection"][];
            source: components["schemas"]["SourceEvidence"];
            /** Summary */
            summary: string;
            /** Tags */
            tags: string[];
            /** Title */
            title: string;
        };
        /** PublicGuideCard */
        PublicGuideCard: {
            /**
             * Category
             * @enum {string}
             */
            category: "university" | "campus" | "disclosure" | "news" | "department";
            /** Id */
            id: string;
            source: components["schemas"]["SourceEvidence"];
            /** Summary */
            summary: string;
            /** Tags */
            tags: string[];
            /** Title */
            title: string;
        };
        /** PublicGuidePage */
        PublicGuidePage: {
            /** Items */
            items: components["schemas"]["PublicGuideCard"][];
            /** Limit */
            limit: number;
            /**
             * Notice
             * @default 공식 공개 페이지를 참고한 DIT NOW 편집 요약입니다. 최신 공식 안내와 처리 규칙은 원문을 확인하세요.
             */
            notice: string;
            /** Offset */
            offset: number;
            /** Snapshot Version */
            snapshot_version: string;
            /** Total */
            total: number;
        };
        /** SourceEvidence */
        SourceEvidence: {
            /**
             * Checked At
             * Format: date
             */
            checked_at: string;
            /**
             * Checked Scope
             * @default 공식 페이지의 도구 반환본 확인. 원문 수정일이나 실시간 최신성을 보장하지 않음.
             */
            checked_scope: string;
            /** Evidence */
            evidence: string;
            /**
             * Existence
             * @default VERIFIED
             * @constant
             */
            existence: "VERIFIED";
            /**
             * Freshness
             * @default UNKNOWN
             * @constant
             */
            freshness: "UNKNOWN";
            /**
             * Processing Rules
             * @default PARTIAL
             * @constant
             */
            processing_rules: "PARTIAL";
            /**
             * Site
             * @enum {string}
             */
            site: "university" | "cs";
            /** Url */
            url: string;
        };
        /** SuccessResponse[CampusSearchData] */
        SuccessResponse_CampusSearchData_: {
            data: components["schemas"]["CampusSearchData"];
            /** Resource Version */
            resource_version?: number | null;
            /**
             * Server Time
             * Format: date-time
             */
            server_time?: string;
        };
        /** SuccessResponse[HealthData] */
        SuccessResponse_HealthData_: {
            data: components["schemas"]["HealthData"];
            /** Resource Version */
            resource_version?: number | null;
            /**
             * Server Time
             * Format: date-time
             */
            server_time?: string;
        };
        /** SuccessResponse[PublicGuidePage] */
        SuccessResponse_PublicGuidePage_: {
            data: components["schemas"]["PublicGuidePage"];
            /** Resource Version */
            resource_version?: number | null;
            /**
             * Server Time
             * Format: date-time
             */
            server_time?: string;
        };
        /** SuccessResponse[PublicGuide] */
        SuccessResponse_PublicGuide_: {
            data: components["schemas"]["PublicGuide"];
            /** Resource Version */
            resource_version?: number | null;
            /**
             * Server Time
             * Format: date-time
             */
            server_time?: string;
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    search_campus_api_v1_ai_campus_search_get: {
        parameters: {
            query: {
                q: string;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SuccessResponse_CampusSearchData_"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    health_api_v1_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SuccessResponse_HealthData_"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_guides_api_v1_public_campus_get: {
        parameters: {
            query?: {
                q?: string;
                category?: ("university" | "campus" | "disclosure" | "news" | "department") | null;
                site?: ("university" | "cs") | null;
                offset?: number;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SuccessResponse_PublicGuidePage_"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_guide_api_v1_public_campus__record_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                record_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SuccessResponse_PublicGuide_"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    health_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SuccessResponse_HealthData_"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
}
