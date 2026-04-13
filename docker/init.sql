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
    -- Publicistisk roll (ledare|krönika|nyheter|kultur|politik|tankesmedja|forskning|fack|sociala_medier|internationell|myndighet)
    writing_section             TEXT,
    -- Politisk profil
    political_leaning           TEXT,
    gal_tan_position            TEXT,
    economic_position           TEXT,
    topics_profile              TEXT[],
    -- Klassificeringsmetadata
    classification_source       TEXT,
    classification_confidence   TEXT DEFAULT 'medium',
    classification_notes        TEXT,
    linkedin_url        TEXT,
    notes               TEXT,
    -- Revealed position — aggregated from actual statements via Claude analysis
    revealed_political_leaning  TEXT,
    revealed_gal_tan_position   TEXT,
    revealed_economic_position  TEXT,
    revealed_confidence         FLOAT,
    revealed_updated_at         TIMESTAMPTZ,
    leaning_discrepancy         TEXT,  -- none|minor|moderate|significant
    statements_count            INTEGER DEFAULT 0,
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

CREATE TABLE person_statements (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id       UUID REFERENCES source_persons(id) ON DELETE CASCADE NOT NULL,
    -- platform: riksdag | twitter | facebook | blog | press_release | party_web | interview | news
    platform        TEXT NOT NULL,
    content         TEXT NOT NULL,
    url             TEXT,
    title           TEXT,
    published_at    TIMESTAMPTZ,
    word_count      INTEGER,
    embedding       vector(768),
    -- Per-statement Claude analysis (populated by analyze_persons pipeline)
    stmt_leaning    TEXT,
    stmt_gal_tan    TEXT,
    stmt_confidence FLOAT,
    stmt_topics     TEXT[],
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_person_statements_person ON person_statements(person_id);
CREATE INDEX idx_person_statements_platform ON person_statements(platform);
CREATE INDEX idx_person_statements_published ON person_statements(published_at DESC);

CREATE TABLE fact_checks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id      UUID REFERENCES articles(id) ON DELETE CASCADE NOT NULL UNIQUE,
    triggered_by    UUID REFERENCES users(id),
    model_used      TEXT NOT NULL,
    claims          JSONB,
    sourcing_score  FLOAT,
    framing_notes   TEXT,
    bias_indicators TEXT[],
    vs_source_profile TEXT,
    summary         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- ANALYTISKT PROVENIENSSCHEMA  (v0.2 — april 2025)
-- ============================================================
-- Designprincip: en persons politiska position är en funktion
-- av tid, källmaterial och mätmetod — aldrig ett statiskt värde.
--
-- Tabeller:
--   analysis_runs                  — en körning av analysmodellen
--   analysis_statement_contributions — vilka uttalanden + vikter (beta)
--   person_position_snapshots      — tidsstämplad klassificering
--   person_trajectories            — detekterade politiska förflyttningar
-- ============================================================

-- 1. Analyskörningar — en rad per person+tillfälle+modell
CREATE TABLE IF NOT EXISTS analysis_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id           UUID REFERENCES source_persons(id) ON DELETE CASCADE NOT NULL,

    model_used          TEXT NOT NULL,
    source_platforms    TEXT[],         -- vilka plattformar inkluderades
    statements_analyzed INTEGER,        -- antal uttalanden som skickades

    -- API-kostnadsspårning
    tokens_input        INTEGER,
    tokens_output       INTEGER,
    cost_usd            FLOAT,          -- API-kostnad i USD

    -- Tidsspann för inkluderade uttalanden
    period_start        DATE,           -- äldsta uttalandets datum
    period_end          DATE,           -- senaste uttalandets datum

    status              TEXT DEFAULT 'completed',  -- pending|running|completed|failed
    error_msg           TEXT,

    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Uttalandebidrag — junction: uttalande × analyskörning med beta-vikt
--    Svarar på: "Vilka sources och med vilka vikter genererade klassificeringen?"
CREATE TABLE IF NOT EXISTS analysis_statement_contributions (
    analysis_run_id     UUID REFERENCES analysis_runs(id) ON DELETE CASCADE NOT NULL,
    statement_id        UUID REFERENCES person_statements(id) ON DELETE CASCADE NOT NULL,

    -- Sammansatt beta-vikt (normaliserad till [0, 1])
    weight              FLOAT NOT NULL DEFAULT 1.0,

    -- Viktkomponenter (för insyn i hur vikten beräknades)
    weight_recency      FLOAT,  -- tidsvikt (exponentiellt avfall, halvliv 3 år)
    weight_platform     FLOAT,  -- plattformsfaktor (riksdag=1.5, twitter=0.7 etc.)
    weight_length       FLOAT,  -- relativ längd vs median i körningen

    -- Inkluderades uttalandet i prompten (kan exkluderas pga token-gräns)?
    included            BOOLEAN DEFAULT true,

    -- Registrerat politiskt signal för detta enskilda uttalande (valfritt)
    signal_leaning      TEXT,
    signal_confidence   FLOAT,

    PRIMARY KEY (analysis_run_id, statement_id)
);

-- 3. Positions-snapshots — tidsstämplad politisk klassificering
--    Den auktoritativa sanningskällan; source_persons.revealed_* är bara convenience-cache
CREATE TABLE IF NOT EXISTS person_position_snapshots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id           UUID REFERENCES source_persons(id) ON DELETE CASCADE NOT NULL,
    analysis_run_id     UUID REFERENCES analysis_runs(id),

    -- Tidsspann för uttalanden som låg till grund
    period_start        DATE,
    period_end          DATE,

    -- Politiska dimensioner (samma skala som source_persons)
    political_leaning   TEXT,   -- far-left → far-right
    gal_tan_position    TEXT,   -- gal → tan
    economic_position   TEXT,   -- far-left → far-right

    confidence          FLOAT,  -- modellens konfidens 0-1

    -- Avvikelse vs deklarerad (institutionell) position
    vs_declared_discrepancy TEXT,   -- none|minor|moderate|significant

    -- Nyckelinsikter
    key_themes          TEXT[],
    analysis_notes      TEXT,

    -- Metainformation
    source_platforms    TEXT[],
    statements_count    INTEGER,

    -- Flagga senaste snapshot för enkel åtkomst
    is_current          BOOLEAN DEFAULT false,

    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Trajektorier — detekterade politiska förflyttningar över tid
--    Beräknas automatiskt när ny snapshot läggs till (om tidigare finns)
CREATE TABLE IF NOT EXISTS person_trajectories (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id           UUID REFERENCES source_persons(id) ON DELETE CASCADE NOT NULL,

    snapshot_from_id    UUID REFERENCES person_position_snapshots(id),
    snapshot_to_id      UUID REFERENCES person_position_snapshots(id),

    period_from         DATE,       -- period_end för from-snapshot
    period_to           DATE,       -- period_end för to-snapshot

    -- Vilken dimension analyseras
    dimension           TEXT NOT NULL,  -- political_leaning|gal_tan|economic

    -- Förflyttningen
    value_from          TEXT,       -- t.ex. "left"
    value_to            TEXT,       -- t.ex. "center-left"
    direction           TEXT,       -- left|right|more_gal|more_tan|stable
    magnitude           TEXT,       -- none|minor|moderate|significant

    -- Narrativ förklaring
    trajectory_notes    TEXT,
    significance        TEXT,       -- routine|notable|major (för highlighting i UI)

    computed_at         TIMESTAMPTZ DEFAULT NOW()
);

-- Index för snabb åtkomst
CREATE INDEX IF NOT EXISTS idx_analysis_runs_person     ON analysis_runs(person_id);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_created    ON analysis_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_stmt_contrib_run         ON analysis_statement_contributions(analysis_run_id);
CREATE INDEX IF NOT EXISTS idx_stmt_contrib_statement   ON analysis_statement_contributions(statement_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_person_time    ON person_position_snapshots(person_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_current        ON person_position_snapshots(person_id) WHERE is_current = true;
CREATE INDEX IF NOT EXISTS idx_trajectories_person      ON person_trajectories(person_id);
CREATE INDEX IF NOT EXISTS idx_trajectories_dimension   ON person_trajectories(person_id, dimension);

-- Admin user
INSERT INTO users (email, display_name, role) VALUES ('xerxes@analytech.se', 'Xerxes', 'admin');
