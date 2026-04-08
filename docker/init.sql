-- Synvinkel Database Schema v0.1
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE TABLE source_organizations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL UNIQUE,
    slug                TEXT NOT NULL UNIQUE,
    type                TEXT NOT NULL,
    website             TEXT,
    description         TEXT,
    logo_url            TEXT,
    political_leaning   TEXT,
    gal_tan_position    TEXT,
    economic_position   TEXT,
    declared_ideology   TEXT,
    primary_funder      TEXT,
    funding_category    TEXT,
    annual_budget_sek   INTEGER,
    parent_org          TEXT,
    founded_year        INTEGER,
    country             TEXT DEFAULT 'SE',
    is_active           BOOLEAN DEFAULT true,
    classification_source       TEXT,
    classification_confidence   TEXT DEFAULT 'high',
    classification_notes        TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE source_persons (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    slug                TEXT NOT NULL UNIQUE,
    title               TEXT,
    organization_id     UUID REFERENCES source_organizations(id),
    secondary_org_ids   UUID[],
    is_journalist       BOOLEAN DEFAULT false,
    is_politician       BOOLEAN DEFAULT false,
    is_researcher       BOOLEAN DEFAULT false,
    party_affiliation   TEXT,
    linkedin_url        TEXT,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE articles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url             TEXT UNIQUE,
    title           TEXT NOT NULL,
    subtitle        TEXT,
    published_at    TIMESTAMPTZ,
    scraped_at      TIMESTAMPTZ DEFAULT NOW(),
    source_org_id   UUID REFERENCES source_organizations(id),
    author_ids      UUID[],
    author_names    TEXT[],
    article_type    TEXT,
    section         TEXT,
    full_text       TEXT,
    summary         TEXT,
    word_count      INTEGER,
    language        TEXT DEFAULT 'sv',
    topics          TEXT[],
    mentioned_parties TEXT[],
    mentioned_persons TEXT[],
    mentioned_orgs  TEXT[],
    sentiment_score FLOAT,
    embedding       vector(768),
    data_source     TEXT,
    scrape_job_id   UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE article_analyses (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id                  UUID REFERENCES articles(id) NOT NULL,
    source_political_leaning    TEXT,
    source_funding_category     TEXT,
    source_type                 TEXT,
    claims_count                INTEGER,
    sourced_claims_count        INTEGER,
    statistical_claims_count    INTEGER,
    statistical_verified        BOOLEAN,
    verification_notes          TEXT,
    related_article_ids         UUID[],
    coverage_spectrum           JSONB,
    analysis_version            TEXT DEFAULT 'v0.1',
    confidence_score            FLOAT,
    confidence_explanation      TEXT,
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE topics (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL UNIQUE,
    slug        TEXT NOT NULL UNIQUE,
    description TEXT,
    keywords    TEXT[],
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE article_topics (
    article_id      UUID REFERENCES articles(id) ON DELETE CASCADE,
    topic_id        UUID REFERENCES topics(id) ON DELETE CASCADE,
    relevance_score FLOAT,
    PRIMARY KEY (article_id, topic_id)
);

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT,
    display_name    TEXT,
    role            TEXT DEFAULT 'user',
    reputation_score FLOAT DEFAULT 0,
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE community_notes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id      UUID REFERENCES articles(id) NOT NULL,
    author_user_id  UUID REFERENCES users(id) NOT NULL,
    note_type       TEXT NOT NULL,
    content         TEXT NOT NULL,
    evidence_urls   TEXT[],
    verdict         TEXT,
    status          TEXT DEFAULT 'pending',
    upvotes         INTEGER DEFAULT 0,
    downvotes       INTEGER DEFAULT 0,
    helpful_score   FLOAT,
    reviewed_by     UUID REFERENCES users(id),
    reviewed_at     TIMESTAMPTZ,
    review_notes    TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE scrape_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name     TEXT NOT NULL,
    status          TEXT DEFAULT 'pending',
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    articles_found  INTEGER DEFAULT 0,
    articles_new    INTEGER DEFAULT 0,
    errors          JSONB,
    config          JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE data_source_configs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    org_id      UUID REFERENCES source_organizations(id),
    config      JSONB NOT NULL,
    schedule    TEXT,
    is_active   BOOLEAN DEFAULT true,
    last_run_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE note_votes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    note_id     UUID REFERENCES community_notes(id) ON DELETE CASCADE NOT NULL,
    user_id     UUID REFERENCES users(id) NOT NULL,
    is_upvote   BOOLEAN NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(note_id, user_id)
);

-- Indexes
CREATE INDEX idx_articles_fulltext ON articles USING GIN (to_tsvector('swedish', coalesce(title, '') || ' ' || coalesce(full_text, '')));
CREATE INDEX idx_articles_source ON articles(source_org_id);
CREATE INDEX idx_articles_published ON articles(published_at DESC);
CREATE INDEX idx_articles_type ON articles(article_type);
CREATE INDEX idx_community_notes_article ON community_notes(article_id);
CREATE INDEX idx_community_notes_status ON community_notes(status);
CREATE INDEX idx_source_orgs_slug ON source_organizations(slug);
CREATE INDEX idx_source_orgs_leaning ON source_organizations(political_leaning);
CREATE INDEX idx_source_persons_org ON source_persons(organization_id);
CREATE INDEX idx_scrape_jobs_status ON scrape_jobs(status);

-- Admin user
INSERT INTO users (email, display_name, role) VALUES ('xerxes@analytech.se', 'Xerxes', 'admin');
