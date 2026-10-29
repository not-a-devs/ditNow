-- REVIEW ONLY: no production connection or grants. Not applied.

CREATE TABLE departments (
	code VARCHAR(50) NOT NULL,
	name VARCHAR(100) NOT NULL,
	id CHAR(32) NOT NULL,
	revision INTEGER NOT NULL,
	created_at DATETIME(6) NOT NULL,
	updated_at DATETIME(6) NOT NULL,
	source_kind VARCHAR(20) NOT NULL,
	source_url VARCHAR(2048),
	checked_at DATETIME(6),
	PRIMARY KEY (id),
	UNIQUE (code)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE identities (
	issuer VARCHAR(2048) NOT NULL,
	subject VARCHAR(512) NOT NULL,
	binding_digest BINARY(32) NOT NULL,
	status VARCHAR(16) NOT NULL,
	id CHAR(32) NOT NULL,
	revision INTEGER NOT NULL,
	created_at DATETIME(6) NOT NULL,
	updated_at DATETIME(6) NOT NULL,
	source_kind VARCHAR(20) NOT NULL,
	source_url VARCHAR(2048),
	checked_at DATETIME(6),
	PRIMARY KEY (id),
	CONSTRAINT ck_identity_status CHECK (status IN ('pending','active','disabled')),
	CONSTRAINT ck_identity_revision CHECK (revision > 0),
	CONSTRAINT uq_identity_binding_digest UNIQUE (binding_digest)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE opportunities (
	kind VARCHAR(50) NOT NULL,
	title VARCHAR(120) NOT NULL,
	organization VARCHAR(200) NOT NULL,
	eligibility TEXT NOT NULL,
	status VARCHAR(16) NOT NULL,
	target_scope JSON NOT NULL,
	files JSON NOT NULL,
	apply_starts_at DATETIME(6),
	deadline_at DATETIME(6),
	original_url VARCHAR(2048),
	submission_mode VARCHAR(40) NOT NULL,
	destination VARCHAR(1000),
	source_kind VARCHAR(20) NOT NULL,
	source_url VARCHAR(2048),
	id CHAR(32) NOT NULL,
	revision INTEGER NOT NULL,
	created_at DATETIME(6) NOT NULL,
	updated_at DATETIME(6) NOT NULL,
	checked_at DATETIME(6),
	PRIMARY KEY (id),
	CONSTRAINT ck_opportunity_submission_mode CHECK (submission_mode IN ('external_document_submission','external_link','info_only')),
	CONSTRAINT ck_origin CHECK (source_kind IN ('OFFICIAL_PUBLIC','DEMO','USER_DEMO')),
	CONSTRAINT ck_official_origin CHECK (source_kind != 'OFFICIAL_PUBLIC' OR (source_url IS NOT NULL AND checked_at IS NOT NULL))
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE academic_memberships (
	user_id CHAR(32) NOT NULL,
	department_id CHAR(32) NOT NULL,
	academic_year INTEGER NOT NULL,
	status VARCHAR(16) NOT NULL,
	valid_from DATETIME(6) NOT NULL,
	valid_to DATETIME(6),
	id CHAR(32) NOT NULL,
	revision INTEGER NOT NULL,
	created_at DATETIME(6) NOT NULL,
	updated_at DATETIME(6) NOT NULL,
	source_kind VARCHAR(20) NOT NULL,
	source_url VARCHAR(2048),
	checked_at DATETIME(6),
	PRIMARY KEY (id),
	CONSTRAINT ck_membership_year CHECK (academic_year > 0),
	CONSTRAINT ck_membership_status CHECK (status IN ('pending','active','inactive')),
	CONSTRAINT ck_membership_period CHECK (valid_to IS NULL OR valid_to > valid_from),
	FOREIGN KEY(user_id) REFERENCES identities (id) ON DELETE RESTRICT,
	FOREIGN KEY(department_id) REFERENCES departments (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE anonymous_posts_private (
	author_id CHAR(32) NOT NULL,
	title VARCHAR(120) NOT NULL,
	`body` TEXT NOT NULL,
	status VARCHAR(16) NOT NULL,
	id CHAR(32) NOT NULL,
	revision INTEGER NOT NULL,
	created_at DATETIME(6) NOT NULL,
	updated_at DATETIME(6) NOT NULL,
	source_kind VARCHAR(20) NOT NULL,
	source_url VARCHAR(2048),
	checked_at DATETIME(6),
	PRIMARY KEY (id),
	CONSTRAINT ck_post_status CHECK (status IN ('active','hidden','deleted')),
	CONSTRAINT ck_post_revision CHECK (revision > 0),
	FOREIGN KEY(author_id) REFERENCES identities (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE audit_logs (
	event VARCHAR(100) NOT NULL,
	resource_kind VARCHAR(32) NOT NULL,
	actor_id CHAR(32),
	entity_id CHAR(32),
	id CHAR(32) NOT NULL,
	revision INTEGER NOT NULL,
	created_at DATETIME(6) NOT NULL,
	updated_at DATETIME(6) NOT NULL,
	source_kind VARCHAR(20) NOT NULL,
	source_url VARCHAR(2048),
	checked_at DATETIME(6),
	PRIMARY KEY (id),
	CONSTRAINT ck_audit_no_anonymous_mapping CHECK (resource_kind != 'anonymous_post' OR actor_id IS NULL OR entity_id IS NULL),
	FOREIGN KEY(actor_id) REFERENCES identities (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE community_idempotency_claims (
	namespace_digest BINARY(32) NOT NULL,
	actor_id CHAR(32) NOT NULL,
	method VARCHAR(8) NOT NULL,
	canonical_path VARCHAR(128) NOT NULL,
	`key` VARCHAR(128) NOT NULL,
	body_digest VARCHAR(64) NOT NULL,
	resource_id CHAR(32) NOT NULL,
	PRIMARY KEY (namespace_digest),
	FOREIGN KEY(actor_id) REFERENCES identities (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE opportunity_check_idempotency (
	namespace_digest BINARY(32) NOT NULL,
	actor_id CHAR(32) NOT NULL,
	opportunity_id CHAR(32) NOT NULL,
	operation VARCHAR(128) NOT NULL,
	`key` VARCHAR(128) NOT NULL,
	request_hash VARCHAR(64) NOT NULL,
	check_id CHAR(32) NOT NULL,
	original_saved_id CHAR(32) NOT NULL,
	tombstone BOOL NOT NULL,
	PRIMARY KEY (namespace_digest),
	FOREIGN KEY(actor_id) REFERENCES identities (id) ON DELETE RESTRICT,
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE profiles (
	user_id CHAR(32) NOT NULL,
	display_name VARCHAR(100) NOT NULL,
	source_kind VARCHAR(20) NOT NULL,
	PRIMARY KEY (user_id),
	FOREIGN KEY(user_id) REFERENCES identities (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE recruitments (
	owner_id CHAR(32) NOT NULL,
	opportunity_id CHAR(32),
	title VARCHAR(120) NOT NULL,
	`body` TEXT NOT NULL,
	field VARCHAR(30) NOT NULL,
	roles JSON NOT NULL,
	accepted_count INTEGER NOT NULL,
	capacity INTEGER NOT NULL,
	deadline_at DATETIME(6) NOT NULL,
	status VARCHAR(16) NOT NULL,
	id CHAR(32) NOT NULL,
	revision INTEGER NOT NULL,
	created_at DATETIME(6) NOT NULL,
	updated_at DATETIME(6) NOT NULL,
	source_kind VARCHAR(20) NOT NULL,
	source_url VARCHAR(2048),
	checked_at DATETIME(6),
	PRIMARY KEY (id),
	CONSTRAINT ck_recruitment_capacity CHECK (capacity >= 2),
	CONSTRAINT ck_recruitment_status CHECK (status IN ('open','closed','cancelled')),
	CONSTRAINT ck_recruitment_revision CHECK (revision > 0),
	CONSTRAINT ck_recruitment_seats CHECK (accepted_count >= 0 AND accepted_count + 1 <= capacity),
	FOREIGN KEY(owner_id) REFERENCES identities (id) ON DELETE RESTRICT,
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE role_assignments (
	user_id CHAR(32) NOT NULL,
	role VARCHAR(16) NOT NULL,
	scope_type VARCHAR(32) NOT NULL,
	scope_id CHAR(32),
	status VARCHAR(16) NOT NULL,
	valid_from DATETIME(6) NOT NULL,
	valid_to DATETIME(6),
	id CHAR(32) NOT NULL,
	revision INTEGER NOT NULL,
	created_at DATETIME(6) NOT NULL,
	updated_at DATETIME(6) NOT NULL,
	source_kind VARCHAR(20) NOT NULL,
	source_url VARCHAR(2048),
	checked_at DATETIME(6),
	PRIMARY KEY (id),
	CONSTRAINT ck_role_kind CHECK (role IN ('student','professor','assistant','admin')),
	CONSTRAINT ck_role_status CHECK (status IN ('pending','active','revoked')),
	CONSTRAINT ck_role_period CHECK (valid_to IS NULL OR valid_to > valid_from),
	CONSTRAINT ck_role_scope CHECK ((scope_type = 'platform' AND scope_id IS NULL) OR (scope_type IN ('department','course_offering') AND scope_id IS NOT NULL)),
	FOREIGN KEY(user_id) REFERENCES identities (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE saved_opportunities (
	user_id CHAR(32) NOT NULL,
	opportunity_id CHAR(32) NOT NULL,
	status VARCHAR(32) NOT NULL,
	memo TEXT NOT NULL,
	self_reported_submitted_at DATETIME(6),
	id CHAR(32) NOT NULL,
	revision INTEGER NOT NULL,
	created_at DATETIME(6) NOT NULL,
	updated_at DATETIME(6) NOT NULL,
	source_kind VARCHAR(20) NOT NULL,
	source_url VARCHAR(2048),
	checked_at DATETIME(6),
	PRIMARY KEY (id),
	CONSTRAINT uq_saved_user_opportunity UNIQUE (user_id, opportunity_id),
	CONSTRAINT ck_saved_status CHECK (status IN ('interested','preparing','self_reported_submitted','closed')),
	CONSTRAINT ck_saved_submission_date CHECK (status != 'self_reported_submitted' OR self_reported_submitted_at IS NOT NULL),
	CONSTRAINT ck_saved_revision CHECK (revision > 0),
	FOREIGN KEY(user_id) REFERENCES identities (id) ON DELETE RESTRICT,
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE saved_opportunity_status_events (
	id CHAR(32) NOT NULL,
	saved_id CHAR(32) NOT NULL,
	user_id CHAR(32) NOT NULL,
	from_status VARCHAR(32) NOT NULL,
	to_status VARCHAR(32) NOT NULL,
	occurred_at DATETIME(6) NOT NULL,
	correction BOOL NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES identities (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE anonymous_posts_public (
	id CHAR(32) NOT NULL,
	title VARCHAR(120) NOT NULL,
	`body` TEXT NOT NULL,
	status VARCHAR(16) NOT NULL,
	comment_count INTEGER NOT NULL,
	revision INTEGER NOT NULL,
	created_at DATETIME(6) NOT NULL,
	updated_at DATETIME(6) NOT NULL,
	source_kind VARCHAR(20) NOT NULL,
	source_url VARCHAR(2048),
	checked_at DATETIME(6),
	PRIMARY KEY (id),
	CONSTRAINT ck_public_post_status CHECK (status IN ('active','hidden','deleted')),
	CONSTRAINT ck_public_post_revision CHECK (revision > 0),
	FOREIGN KEY(id) REFERENCES anonymous_posts_private (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE opportunity_check_items (
	saved_opportunity_id CHAR(32) NOT NULL,
	text VARCHAR(500) NOT NULL,
	sort_order INTEGER NOT NULL,
	completed_at DATETIME(6),
	id CHAR(32) NOT NULL,
	revision INTEGER NOT NULL,
	created_at DATETIME(6) NOT NULL,
	updated_at DATETIME(6) NOT NULL,
	source_kind VARCHAR(20) NOT NULL,
	source_url VARCHAR(2048),
	checked_at DATETIME(6),
	PRIMARY KEY (id),
	CONSTRAINT ck_check_order CHECK (sort_order >= 0),
	CONSTRAINT ck_check_revision CHECK (revision > 0),
	CONSTRAINT uq_check_parent_order UNIQUE (saved_opportunity_id, sort_order),
	FOREIGN KEY(saved_opportunity_id) REFERENCES saved_opportunities (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE recruitment_applications (
	recruitment_id CHAR(32) NOT NULL,
	applicant_id CHAR(32) NOT NULL,
	message TEXT NOT NULL,
	status VARCHAR(16) NOT NULL,
	id CHAR(32) NOT NULL,
	revision INTEGER NOT NULL,
	created_at DATETIME(6) NOT NULL,
	updated_at DATETIME(6) NOT NULL,
	source_kind VARCHAR(20) NOT NULL,
	source_url VARCHAR(2048),
	checked_at DATETIME(6),
	PRIMARY KEY (id),
	CONSTRAINT uq_recruitment_applicant UNIQUE (recruitment_id, applicant_id),
	CONSTRAINT ck_application_status CHECK (status IN ('pending','accepted','rejected','withdrawn')),
	FOREIGN KEY(recruitment_id) REFERENCES recruitments (id) ON DELETE RESTRICT,
	FOREIGN KEY(applicant_id) REFERENCES identities (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
