from fastapi import APIRouter, HTTPException, Query
from app.db.firestore import get_db
from app.models.article import Article, ArticleList

router = APIRouter()

CATEGORIES = ["IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"]


@router.get("/stats")
def articles_stats():
    db = get_db()
    all_docs = list(db.collection("articles").stream())
    total = len(all_docs)
    counts = {cat: 0 for cat in CATEGORIES}
    for doc in all_docs:
        cat = doc.to_dict().get("category", "Autre")
        if cat in counts:
            counts[cat] += 1
        else:
            counts["Autre"] += 1
    return {"total": total, "by_category": counts}


@router.get("/")
def list_articles(
    category: str | None = Query(None),
    source_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
):
    db = get_db()
    query = db.collection("articles").order_by("published_at", direction="DESCENDING")

    if category:
        query = query.where("category", "==", category)
    if source_id:
        query = query.where("source_id", "==", source_id)

    all_docs = list(query.stream())
    total = len(all_docs)
    start = (page - 1) * page_size
    page_docs = all_docs[start: start + page_size]

    items = [Article(**{**doc.to_dict(), "id": doc.id}) for doc in page_docs]
    return ArticleList(items=items, total=total, page=page, page_size=page_size)


@router.get("/{article_id}", response_model=Article)
def get_article(article_id: str):
    db = get_db()
    doc = db.collection("articles").document(article_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Article introuvable")
    return Article(**{**doc.to_dict(), "id": doc.id})
