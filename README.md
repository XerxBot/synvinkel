# Synvinkel

**Alla har en synvinkel — vi visar vilken.**

Synvinkel är en öppen plattform för analys av politisk bias i svenska medier. Systemet klassificerar avsändare — organisationer och personer — inte enskilda åsikter eller artiklar.

---

## Innehåll

- [Arkitektur](#arkitektur)
- [Kom igång](#kom-igång)
- [Seed-data](#seed-data)
- [Revealed positions](#revealed-positions)
- [Deploy](#deploy)
- [Miljövariabler](#miljövariabler)

---

## Arkitektur

```
frontend/        Astro 4 + React islands + Tailwind CSS → Cloudflare Pages
backend/         FastAPI (Python 3.12) + SQLAlchemy async → Fly.io
docker/          init.sql (schema bootstrap)
data/seed/       organizations.json + persons.json + topics.json
```

**Tjänster (Docker Compose):**

| Tjänst | Image | Port |
|--------|-------|------|
| `db` | pgvector/pgvector:pg16 | 5432 |
| `redis` | redis:7-alpine | 6379 |
| `backend` | FastAPI (uvicorn) | 8000 |
| `frontend` | Astro SSR | 4321 |

**Centrala tabeller:**

| Tabell | Innehåll |
|--------|----------|
| `source_organizations` | Medieorganisationer med politisk klassificering och journalistkårsbias |
| `source_persons` | Journalister, politiker, forskare, krönkiörer m.fl. |
| `articles` | Scrapade artiklar kopplade till organisation |
| `person_statements` | Uttalanden för revealed-position-analys |
| `analysis_runs` | Körningsmetadata (modell, tokens, kostnad) |
| `person_position_snapshots` | Tidsstämplade politiska positioner per person |
| `person_trajectories` | Automatisk detektering av politiska förflyttningar |

---

## Kom igång

**Krav:** Docker Desktop, pnpm

```bash
# Klona och starta
git clone https://github.com/XerxBot/synvinkel.git
cd synvinkel
cp .env.example .env          # fyll i ANTHROPIC_API_KEY m.m.

docker compose up -d db redis backend

# Läs in seed-data
docker compose exec backend python -m app.seed

# Starta frontend lokalt
cd frontend && pnpm install && pnpm dev
```

- Backend API + Swagger: http://localhost:8000/docs
- Frontend: http://localhost:4321

---

## Seed-data

Seed-filerna ligger i `backend/data/seed/` och körs med `python -m app.seed` (upsert — säkert att köra om).

| Fil | Innehåll |
|-----|----------|
| `organizations.json` | ~61 organisationer med politisk linje, GAL-TAN, ekonomisk position, journalistkårsbias |
| `persons.json` | ~245 personer — politiker, journalister, forskare, krönkiörer, podcasters |
| `topics.json` | Ämnestaggar |

**Klassificeringsdimensioner:**

- `political_leaning` — `far-left` → `far-right`
- `gal_tan_position` — redaktionell linje på GAL–TAN-axeln
- `economic_position` — `state-interventionist` → `free-market`
- `staff_bias_gal_tan` — journalistkårens sammansättning (ej redaktionell policy), baserat på Asp (2011) m.fl.
- `writing_section` — `ledare` | `krönika` | `nyheter` | `debatt` | `podcast` | `forskning` | `politik` | m.fl.

---

## Revealed positions

Systemet samlar in verkliga uttalanden och analyserar dem med Claude för att beräkna en *revealed* politisk position — skild från den deklarerade.

```bash
# Samla riksdagsanföranden (Riksdagens öppna data API)
docker compose exec backend python -m app.collect_statements

# Analysera med Claude och uppdatera revealed_* på source_persons
docker compose exec backend python -m app.analyze_persons
```

Proveniensspårning sker via `analysis_runs` och `analysis_statement_contributions`. Beta-vikter per uttalande: `platform_weight × recency_weight × length_weight`.

---

## Deploy

**Backend → Fly.io**

```bash
fly deploy --config fly.toml
```

**Frontend → Cloudflare Pages**

Bygg-kommando: `pnpm build` · Output: `dist/` · Node: 20+

Sätt miljövariablerna `API_URL` och `PUBLIC_API_URL` i Cloudflare Pages dashboard.

---

## Miljövariabler

| Variabel | Beskrivning |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL async URL (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Redis URL |
| `SECRET_KEY` | JWT-signeringsnyckel |
| `ANTHROPIC_API_KEY` | Claude API — faktakoll och revealed-position-analys |
| `FACTCHECK_MODEL` | Standardmodell för faktakoll (default: `claude-sonnet-4-6`) |
| `TWITTER_BEARER_TOKEN` | Twitter/X API v2 (kräver Basic-nivå, $100/mån) |

---

## Metodologi

Klassificeringen skiljer på två nivåer:

- **Redaktionell linje** (`gal_tan_position`) — vad organisationen publicerar och förespråkar
- **Journalistkårens bias** (`staff_bias_gal_tan`) — journalistkårens politiska sammansättning, baserat på forskning (bl.a. Asp 2011: SVT/SR-journalister ~54% MP, <7% M)

Dessa kan skilja sig åt: SVT:s redaktionella linje är `center`, men journalistkårens bias är `gal`.

Revealed positions baseras på faktiska anföranden och uttalanden analyserade av Claude — inte på partibok eller deklarerad ideologi. Diskrepans mellan declared och revealed position flaggas automatiskt.
