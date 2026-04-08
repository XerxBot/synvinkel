/**
 * API-klient för Synvinkel backend.
 * Server-sida: använder API_URL (Docker-intern eller localhost).
 * Klient-sida: använder PUBLIC_API_URL (tillgänglig från webbläsaren).
 */

const SERVER_BASE = import.meta.env.API_URL ?? 'http://localhost:8000/api/v1';
export const CLIENT_BASE = import.meta.env.PUBLIC_API_URL ?? 'http://localhost:8000/api/v1';

// ── Types ────────────────────────────────────────────────────────────────────

export interface Organization {
  id: string;
  slug: string;
  name: string;
  type: string;
  website: string | null;
  description: string | null;
  political_leaning: string | null;
  gal_tan_position: string | null;
  economic_position: string | null;
  declared_ideology: string | null;
  primary_funder: string | null;
  funding_category: string | null;
  founded_year: number | null;
  classification_confidence: string;
  classification_notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OrganizationProfile extends Organization {
  domains: string[];
}

export interface Article {
  id: string;
  url: string | null;
  title: string;
  subtitle: string | null;
  published_at: string | null;
  scraped_at: string;
  source_org_id: string | null;
  data_source: string | null;
  author_names: string[] | null;
  article_type: string | null;
  section: string | null;
  word_count: number | null;
  language: string;
  topics: string[] | null;
  mentioned_parties: string[] | null;
  mentioned_persons: string[] | null;
  mentioned_orgs: string[] | null;
  sentiment_score: number | null;
  full_text?: string | null;
  created_at: string;
}

export interface AnalysisSummary {
  source_political_leaning: string | null;
  source_funding_category: string | null;
  source_type: string | null;
  confidence_score: number | null;   // deviation_score 0–1
  confidence_explanation: string | null;
  coverage_spectrum: {
    deviation_score: number;
    sentiment_alignment: number;
    party_alignment: number;
    flags: string[];
    version: string;
  } | null;
}

export interface ArticleDetail extends Article {
  full_text: string | null;
  mentioned_persons: string[] | null;
  mentioned_orgs: string[] | null;
  analysis: AnalysisSummary | null;
}

export interface TopicCoverage {
  topic: { slug: string; name: string; description: string | null };
  stats: { total_articles: number; avg_sentiment: number | null; sources_count: number };
  source_distribution: { slug: string; name: string; count: number; political_leaning: string | null; type: string | null }[];
  top_parties: { party: string; count: number }[];
  recent_articles: { id: string; title: string; url: string | null; data_source: string | null; published_at: string | null; sentiment_score: number | null; article_type: string | null }[];
}

export interface Perspective {
  leaning: string;
  id: string;
  title: string;
  data_source: string | null;
  published_at: string | null;
  sentiment_score: number | null;
}

export interface ExportResponse {
  meta: {
    total_returned: number;
    offset: number;
    limit: number;
    filters: Record<string, string>;
  };
  articles: Article[];
}

export interface DashboardData {
  counts: {
    articles: number;
    organizations: number;
    topics: number;
    pending_community_notes: number;
  };
  recent_scrape_jobs: ScrapeJob[];
}

export interface ScrapeJob {
  id: string;
  source_name: string;
  status: string;
  articles_found: number;
  articles_new: number;
  created_at?: string;
  started_at?: string | null;
  completed_at?: string | null;
  errors?: Record<string, string> | null;
}

// ── Server-side fetchers (used in .astro pages) ───────────────────────────────

export async function fetchSources(params?: { type?: string; leaning?: string }): Promise<Organization[]> {
  const qs = new URLSearchParams(params as Record<string, string>);
  const res = await fetch(`${SERVER_BASE}/sources?${qs}`);
  if (!res.ok) throw new Error(`sources: ${res.status}`);
  return res.json();
}

export async function fetchSource(slug: string): Promise<OrganizationProfile> {
  const res = await fetch(`${SERVER_BASE}/sources/${slug}`);
  if (!res.ok) throw new Error(`source/${slug}: ${res.status}`);
  return res.json();
}

export async function fetchArticle(id: string): Promise<ArticleDetail> {
  const res = await fetch(`${SERVER_BASE}/articles/${id}`);
  if (!res.ok) throw new Error(`article/${id}: ${res.status}`);
  return res.json();
}

export async function fetchTopics(): Promise<{ id: string; name: string; slug: string; description: string | null }[]> {
  const res = await fetch(`${SERVER_BASE}/topics`);
  if (!res.ok) return [];
  return res.json();
}

export async function fetchTopicCoverage(slug: string, limit = 20): Promise<TopicCoverage> {
  const res = await fetch(`${SERVER_BASE}/topics/${slug}/coverage?limit=${limit}`);
  if (!res.ok) throw new Error(`topics/${slug}/coverage: ${res.status}`);
  return res.json();
}

export async function fetchPerspectives(topicSlug: string): Promise<Perspective[]> {
  const res = await fetch(`${SERVER_BASE}/topics/${topicSlug}/perspectives`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.perspectives ?? [];
}

export async function fetchArticlesBySource(slug: string, limit = 10): Promise<Article[]> {
  const res = await fetch(`${SERVER_BASE}/export/articles?source_slug=${slug}&limit=${limit}`);
  if (!res.ok) return [];
  const data: ExportResponse = await res.json();
  return data.articles;
}

export async function fetchDashboard(): Promise<DashboardData> {
  const res = await fetch(`${SERVER_BASE}/admin/dashboard`);
  if (!res.ok) throw new Error(`dashboard: ${res.status}`);
  return res.json();
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Mappa political_leaning → position 0–100 på vänster-höger-skala */
export function leaningToPosition(leaning: string | null): number {
  const map: Record<string, number> = {
    'far-left': 5, 'left': 20, 'center-left': 35,
    'center': 50, 'neutral': 50,
    'center-right': 65, 'right': 80, 'far-right': 95,
    'libertarian': 70,
  };
  return map[leaning ?? 'neutral'] ?? 50;
}

/** Mappa political_leaning → färgklass */
export function leaningColor(leaning: string | null): string {
  const pos = leaningToPosition(leaning);
  if (pos <= 20) return 'text-red-600';
  if (pos <= 40) return 'text-rose-500';
  if (pos <= 60) return 'text-gray-600';
  if (pos <= 75) return 'text-blue-500';
  return 'text-blue-700';
}

/** Formatera sentiment-poäng */
export function formatSentiment(score: number | null): string {
  if (score === null) return '–';
  if (score > 0.3) return 'Positiv';
  if (score < -0.3) return 'Negativ';
  return 'Neutral';
}

/** Formatera datum på svenska */
export function formatDate(iso: string | null): string {
  if (!iso) return '–';
  return new Date(iso).toLocaleDateString('sv-SE', {
    year: 'numeric', month: 'short', day: 'numeric',
  });
}

/** Etiketter för politisk lutning */
export const LEANING_LABELS: Record<string, string> = {
  'far-left': 'Yttersta vänster',
  'left': 'Vänster',
  'center-left': 'Vänster-center',
  'center': 'Center',
  'neutral': 'Neutral',
  'center-right': 'Höger-center',
  'right': 'Höger',
  'far-right': 'Yttersta höger',
  'libertarian': 'Libertariansk',
};

export const TYPE_LABELS: Record<string, string> = {
  'think_tank': 'Tankesmedja',
  'newspaper': 'Tidning',
  'public_broadcaster': 'Public service',
  'political_party': 'Politiskt parti',
  'government': 'Regering/myndighet',
  'interest_org': 'Intresseorganisation',
  'social_media': 'Sociala medier',
  'online_news': 'Nätnyhet',
  'magazine': 'Tidskrift',
  'news_agency': 'Nyhetsbyrå',
};
