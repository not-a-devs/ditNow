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
)ENGINE=InnoDB CHARSET=utf8mb4;

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
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE TABLE opportunities (
	kind VARCHAR(50) NOT NULL,
	title VARCHAR(120) NOT NULL,
	deadline_at DATETIME(6) NOT NULL,
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
)ENGINE=InnoDB CHARSET=utf8mb4;

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
)ENGINE=InnoDB CHARSET=utf8mb4;

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
)ENGINE=InnoDB CHARSET=utf8mb4;

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
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE TABLE profiles (
	user_id CHAR(32) NOT NULL,
	display_name VARCHAR(100) NOT NULL,
	source_kind VARCHAR(20) NOT NULL,
	PRIMARY KEY (user_id),
	FOREIGN KEY(user_id) REFERENCES identities (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE TABLE recruitments (
	owner_id CHAR(32) NOT NULL,
	opportunity_id CHAR(32),
	title VARCHAR(120) NOT NULL,
	`body` TEXT NOT NULL,
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
	FOREIGN KEY(owner_id) REFERENCES identities (id) ON DELETE RESTRICT,
	FOREIGN KEY(opportunity_id) REFERENCES opportunities (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4;

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
)ENGINE=InnoDB CHARSET=utf8mb4;

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
)ENGINE=InnoDB CHARSET=utf8mb4;

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
	FOREIGN KEY(saved_opportunity_id) REFERENCES saved_opportunities (id) ON DELETE RESTRICT
)ENGINE=InnoDB CHARSET=utf8mb4;
