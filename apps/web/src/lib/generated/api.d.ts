// Generated from services/api/openapi.json. Do not edit.
export interface paths {
    "/api/v1/ai/ask": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Ask
         * @description 자연어 질문에 교내 데이터·(로그인 시) 본인 가상 학적을 근거로 LLM이 답한다.
         *
         *     history를 보내면 '거기 몇 시까지 해?' 같은 후속 질문을 완전한 질문으로 바꿔 처리한다.
         */
        post: operations["ask_api_v1_ai_ask_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
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
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Login
         * @description 학번과 초기 비밀번호로 로그인한다. 학생·학적은 모두 가상(DEMO) 데이터다.
         */
        post: operations["login_api_v1_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Logout */
        post: operations["logout_api_v1_auth_logout_post"];
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
        /** AskData */
        AskData: {
            /** Answer */
            answer: string;
            /**
             * Classified By
             * @enum {string}
             */
            classified_by: "keyword" | "llm";
            /** Found */
            found: boolean;
            /**
             * Generated
             * @default true
             * @constant
             */
            generated: true;
            /** Intent */
            intent: string;
            /** Locations */
            locations: components["schemas"]["AskLocation"][];
            /** Need Login */
            need_login: boolean;
            /** Personal Data Access */
            personal_data_access: boolean;
            /**
             * Record Source
             * @default DEMO
             * @constant
             */
            record_source: "DEMO";
            /** Rewritten Question */
            rewritten_question?: string | null;
            /** Sources */
            sources: string[];
        };
        /** AskInput */
        AskInput: {
            /** History */
            history?: components["schemas"]["AskTurn"][];
            /** Question */
            question: string;
        };
        /** AskLocation */
        AskLocation: {
            /** Building */
            building: string;
            /** Id */
            id: string;
            /** Lat */
            lat: number;
            /** Lng */
            lng: number;
            /** Name */
            name: string;
        };
        /** AskTurn */
        AskTurn: {
            /** Content */
            content: string;
            /**
             * Role
             * @enum {string}
             */
            role: "user" | "assistant";
        };
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
        /** LoginData */
        LoginData: {
            /** Name */
            name: string;
            /**
             * Record Source
             * @default DEMO
             * @constant
             */
            record_source: "DEMO";
            /** Student Id */
            student_id: string;
            /** Token */
            token: string;
            /**
             * Token Type
             * @default Bearer
             * @constant
             */
            token_type: "Bearer";
        };
        /** LoginInput */
        LoginInput: {
            /** Password */
            password: string;
            /** Student Id */
            student_id: string;
        };
        /** SuccessResponse[AskData] */
        SuccessResponse_AskData_: {
            data: components["schemas"]["AskData"];
            /** Resource Version */
            resource_version?: number | null;
            /**
             * Server Time
             * Format: date-time
             */
            server_time?: string;
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
        /** SuccessResponse[LoginData] */
        SuccessResponse_LoginData_: {
            data: components["schemas"]["LoginData"];
            /** Resource Version */
            resource_version?: number | null;
            /**
             * Server Time
             * Format: date-time
             */
            server_time?: string;
        };
        /** SuccessResponse[dict[str, str]] */
        SuccessResponse_dict_str__str__: {
            /** Data */
            data: {
                [key: string]: string;
            };
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
    ask_api_v1_ai_ask_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AskInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SuccessResponse_AskData_"];
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
    login_api_v1_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SuccessResponse_LoginData_"];
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
    logout_api_v1_auth_logout_post: {
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
                    "application/json": components["schemas"]["SuccessResponse_dict_str__str__"];
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
