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
    "/api/v1/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Me */
        get: operations["me_api_v1_auth_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/campus-travel/calculate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Calculate */
        post: operations["calculate_api_v1_campus_travel_calculate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data-provenance": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Provenance Overview */
        get: operations["get_provenance_overview_api_v1_data_provenance_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data-provenance/labels/{label}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Provenance Label */
        get: operations["get_provenance_label_api_v1_data_provenance_labels__label__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/discovery": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Discover
         * @description Public snapshots only. No personal, authenticated, remote or generated sources.
         */
        get: operations["discover_api_v1_discovery_get"];
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
        /** DiscoveryItem */
        DiscoveryItem: {
            /** Detail Path */
            detail_path: string;
            /** Id */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "guide" | "facility";
            /** Source */
            source: components["schemas"]["GuideSource"] | components["schemas"]["FacilitySource"];
            /** Summary */
            summary: string;
            /** Title */
            title: string;
        };
        /** DiscoveryPage */
        DiscoveryPage: {
            /** Complete */
            complete: boolean;
            /** Counts */
            counts: {
                [key: string]: number;
            };
            /**
             * Generated
             * @default false
             * @constant
             */
            generated: false;
            /** Items */
            items: components["schemas"]["DiscoveryItem"][];
            /**
             * Kind
             * @enum {string}
             */
            kind: "all" | "guide" | "facility";
            /** Limit */
            limit: number;
            /**
             * Notice
             * @default 공개 대학 안내와 시설 스냅샷만 검색합니다. 개인 시간표·성적·신청·대화는 검색하지 않습니다. 출처별 확인 범위가 다르며 실시간 학교 정보나 AI 생성 답변이 아닙니다.
             */
            notice: string;
            /** Offset */
            offset: number;
            /**
             * Personal Data Access
             * @default false
             * @constant
             */
            personal_data_access: false;
            /** Query */
            query: string;
            /** Total */
            total: number;
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
        /** FacilitySource */
        FacilitySource: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "unverified_facility";
            /**
             * Notice
             * @default 기존 시설 스냅샷입니다. 공식 출처와 최신성은 검증되지 않았습니다.
             */
            notice: string;
            /**
             * Source Path
             * @default chatbot/data/facilities.json
             * @constant
             */
            source_path: "chatbot/data/facilities.json";
            /**
             * Verification
             * @default UNKNOWN
             * @constant
             */
            verification: "UNKNOWN";
        };
        /** GuideSection */
        GuideSection: {
            /** Heading */
            heading: string;
            /** Paragraphs */
            paragraphs: string[];
        };
        /** GuideSource */
        GuideSource: {
            evidence: components["schemas"]["SourceEvidence"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "official_summary";
            /** Snapshot Version */
            snapshot_version: string;
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
        /** ProvenanceLabelInfo */
        ProvenanceLabelInfo: {
            /** Description */
            description: string;
            /**
             * Label
             * @enum {string}
             */
            label: "DEMO" | "OFFICIAL_PUBLIC" | "PLATFORM" | "UNKNOWN";
            /** Title */
            title: string;
            /** User Guidance */
            user_guidance: string;
        };
        /** ProvenanceOverview */
        ProvenanceOverview: {
            /** Catalog Version */
            catalog_version: string;
            /** Feature Ids */
            feature_ids: string[];
            /** Labels */
            labels: components["schemas"]["ProvenanceLabelInfo"][];
            /** Notice */
            notice: string;
            status: components["schemas"]["ProvenanceStatus"];
        };
        /**
         * ProvenanceStatus
         * @description Fixed facts about this platform; every value is a constant, never configuration.
         */
        ProvenanceStatus: {
            /**
             * Content Administration
             * @default NOT_IMPLEMENTED
             * @constant
             */
            content_administration: "NOT_IMPLEMENTED";
            /**
             * Financial Effect
             * @default NONE
             * @constant
             */
            financial_effect: "NONE";
            /**
             * Persistence
             * @default IN_PROCESS_FIXED
             * @constant
             */
            persistence: "IN_PROCESS_FIXED";
            /**
             * School Sso Connected
             * @default false
             * @constant
             */
            school_sso_connected: false;
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
        /**
         * SessionProfile
         * @description Own-account projection; never reuse this model in anonymous post responses.
         */
        SessionProfile: {
            /** Academic Year */
            academic_year: number;
            /** Community Access */
            community_access: boolean;
            /** Department Code */
            department_code: string;
            /**
             * Department Id
             * Format: uuid
             */
            department_id: string;
            /** Display Name */
            display_name: string;
            /**
             * Record Source
             * @default DEMO
             * @constant
             */
            record_source: "DEMO";
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
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
        /** SuccessResponse[DiscoveryPage] */
        SuccessResponse_DiscoveryPage_: {
            data: components["schemas"]["DiscoveryPage"];
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
        /** SuccessResponse[ProvenanceLabelInfo] */
        SuccessResponse_ProvenanceLabelInfo_: {
            data: components["schemas"]["ProvenanceLabelInfo"];
            /** Resource Version */
            resource_version?: number | null;
            /**
             * Server Time
             * Format: date-time
             */
            server_time?: string;
        };
        /** SuccessResponse[ProvenanceOverview] */
        SuccessResponse_ProvenanceOverview_: {
            data: components["schemas"]["ProvenanceOverview"];
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
        /** SuccessResponse[SessionProfile] */
        SuccessResponse_SessionProfile_: {
            data: components["schemas"]["SessionProfile"];
            /** Resource Version */
            resource_version?: number | null;
            /**
             * Server Time
             * Format: date-time
             */
            server_time?: string;
        };
        /** SuccessResponse[TravelResult] */
        SuccessResponse_TravelResult_: {
            data: components["schemas"]["TravelResult"];
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
        /** TravelInput */
        TravelInput: {
            /** Estimated Travel Minutes */
            estimated_travel_minutes: number;
            /**
             * Next Starts At
             * Format: date-time
             */
            next_starts_at: string;
            /**
             * Previous Ends At
             * Format: date-time
             */
            previous_ends_at: string;
        };
        /** TravelResult */
        TravelResult: {
            /**
             * Calculation Version
             * @default manual-travel-v1
             * @constant
             */
            calculation_version: "manual-travel-v1";
            /**
             * Estimate Source
             * @default USER_INPUT
             * @constant
             */
            estimate_source: "USER_INPUT";
            /** Gap Seconds */
            gap_seconds: number;
            /**
             * Next Starts At
             * Format: date-time
             */
            next_starts_at: string;
            /**
             * Notice
             * @default 사용자가 입력한 시각과 예상 이동 시간만 계산합니다. 실제 지도·최단 경로·공식 이동 시간·접근 가능한 동선·도착을 보장하지 않습니다. 개인 시간표는 연결하지 않습니다.
             * @constant
             */
            notice: "사용자가 입력한 시각과 예상 이동 시간만 계산합니다. 실제 지도·최단 경로·공식 이동 시간·접근 가능한 동선·도착을 보장하지 않습니다. 개인 시간표는 연결하지 않습니다.";
            /**
             * Previous Ends At
             * Format: date-time
             */
            previous_ends_at: string;
            /** Remaining Seconds */
            remaining_seconds: number;
            /**
             * Status
             * @enum {string}
             */
            status: "OVERLAP" | "INSUFFICIENT" | "NO_MARGIN" | "HAS_MARGIN";
            /** Travel Seconds */
            travel_seconds: number;
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
    me_api_v1_auth_me_get: {
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
                    "application/json": components["schemas"]["SuccessResponse_SessionProfile_"];
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
    calculate_api_v1_campus_travel_calculate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TravelInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SuccessResponse_TravelResult_"];
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
            /** @description Unauthorized */
            401: {
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
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_provenance_overview_api_v1_data_provenance_get: {
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
                    "application/json": components["schemas"]["SuccessResponse_ProvenanceOverview_"];
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
            /** @description Not Found */
            404: {
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
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_provenance_label_api_v1_data_provenance_labels__label__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                label: "DEMO" | "OFFICIAL_PUBLIC" | "PLATFORM" | "UNKNOWN";
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
                    "application/json": components["schemas"]["SuccessResponse_ProvenanceLabelInfo_"];
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
            /** @description Not Found */
            404: {
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
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    discover_api_v1_discovery_get: {
        parameters: {
            query: {
                q: string;
                kind?: "all" | "guide" | "facility";
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
                    "application/json": components["schemas"]["SuccessResponse_DiscoveryPage_"];
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
