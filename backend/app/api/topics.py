from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.article import Article
from app.models.organization import SourceOrganization
from app.models.topic import Topic
from app.schemas.topic import TopicResponse

router = APIRouter()


@router.get("", response_model=list[TopicResponse])
async def list_topics(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Topic).order_by(Topic.name))
    return result.scalars().all()


@router.get("/{slug}", response_model=TopicResponse)
async def get_topic(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Topic).where(Topic.slug == slug))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Ämne hittades inte")
    return topic


@router.get("/{slug}/coverage")
async def topic_coverage(
    slug: str,
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Artiklar om detta ämne fördelat per källa och politisk lutning.
    Returnerar täckningsprofil + senaste artiklar.
    """
    topic = await db.scalar(select(Topic).where(Topic.slug == slug))
    if not topic:
        raise HTTPException(status_code=404, detail="Ämne hittades inte")

    # Artiklar med detta ämne
    articles_result = await db.execute(
        select(Article)
        .where(Article.topics.contains([slug]))
        .order_by(Article.published_at.desc())
        .limit(limit)
    )
    articles = articles_result.scalars().all()

    # Total count
    total = await db.scalar(
        select(func.count(Article.id)).where(Article.topics.contains([slug]))
    )

    # Källfördelning — gruppera på data_source
    source_counts: Counter = Counter(
        a.data_source for a in articles if a.data_source
    )

    # Hämta politisk lutning per källa
    slugs = list(source_counts.keys())
    orgs_result = await db.execute(
        select(SourceOrganization).where(SourceOrganization.slug.in_(slugs))
    )
    orgs_by_slug = {o.slug: o for o in orgs_result.scalars()}

    source_distribution = []
    for src_slug, count in source_counts.most_common():
        org = orgs_by_slug.get(src_slug)
        source_distribution.append({
            "slug": src_slug,
            "name": org.name if org else src_slug,
            "count": count,
            "political_leaning": org.political_leaning if org else None,
            "type": org.type if org else None,
        })

    # Sentimentfördelning
    sentiments = [a.sentiment_score for a in articles if a.sentiment_score is not None]
    avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else None

    # Partifördelning
    party_counter: Counter = Counter()
    for a in articles:
        for p in (a.mentioned_parties or []):
            party_counter[p] += 1

    return {
        "topic": {"slug": topic.slug, "name": topic.name, "description": topic.description},
        "stats": {
            "total_articles": total,
            "avg_sentiment": round(avg_sentiment, 3) if avg_sentiment is not None else None,
            "sources_count": len(source_counts),
        },
        "source_distribution": source_distribution,
        "top_parties": [{"party": p, "count": c} for p, c in party_counter.most_common(5)],
        "recent_articles": [
            {
                "id": str(a.id),
                "title": a.title,
                "url": a.url,
                "data_source": a.data_source,
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "sentiment_score": a.sentiment_score,
                "article_type": a.article_type,
            }
            for a in articles[:limit]
        ],
    }


@router.get("/{slug}/perspectives")
async def topic_perspectives(
    slug: str,
    limit: int = Query(default=4, le=10),
    db: AsyncSession = Depends(get_db),
):
    """
    'Samma ämne, andra perspektiv' — ett artikel per politisk lutning.
    """
    topic = await db.scalar(select(Topic).where(Topic.slug == slug))
    if not topic:
        raise HTTPException(status_code=404, detail="Ämne hittades inte")

    leanings = ["left", "center-left", "center", "center-right", "right"]
    perspectives = []

    orgs_result = await db.execute(
        select(SourceOrganization).where(
            SourceOrganization.political_leaning.in_(leanings)
        )
    )
    orgs_by_leaning: dict[str, list] = {}
    for org in orgs_result.scalars():
        orgs_by_leaning.setdefault(org.political_leaning, []).append(org.slug)

    for leaning in leanings:
        slugs = orgs_by_leaning.get(leaning, [])
        if not slugs:
            continue
        article = await db.scalar(
            select(Article)
            .where(
                Article.topics.contains([slug]),
                Article.data_source.in_(slugs),
                Article.title.isnot(None),
            )
            .order_by(Article.published_at.desc())
            .limit(1)
        )
        if article:
            perspectives.append({
                "leaning": leaning,
                "id": str(article.id),
                "title": article.title,
                "data_source": article.data_source,
                "published_at": article.published_at.isoformat() if article.published_at else None,
                "sentiment_score": article.sentiment_score,
            })
        if len(perspectives) >= limit:
            break

    return {"topic": topic.slug, "perspectives": perspectives}
