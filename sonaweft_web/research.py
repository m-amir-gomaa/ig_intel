"""User-requested scholarly metadata lookup; candidates are not evidence verdicts."""

import re
from urllib.parse import quote
import httpx
from .errors import DomainError


async def candidates(text, transport=None):
    if not isinstance(text, str) or not 1 <= len(text) <= 1000:
        raise DomainError("Choose a short source claim.")
    try:
        async with httpx.AsyncClient(
            timeout=10, transport=transport, follow_redirects=False
        ) as client:
            response = await client.get(
                "https://api.crossref.org/works",
                params={
                    "query.bibliographic": text[:350],
                    "rows": 3,
                    "select": "DOI,title,published",
                    "mailto": "mo.gomaa.formal@gmail.com",
                },
                headers={
                    "User-Agent": "Sonaweft/0.2 (mailto:mo.gomaa.formal@gmail.com)"
                },
            )
            response.raise_for_status()
            items = response.json()["message"]["items"]
            result = []
            for item in items[:3]:
                doi = item.get("DOI", "")
                title = item.get("title", [])
                if (
                    not re.fullmatch(r"10\.[0-9]{4,9}/[^\s<>]{1,250}", doi)
                    or not isinstance(title, list)
                    or not title
                    or not isinstance(title[0], str)
                ):
                    continue
                result.append(
                    {
                        "title": title[0][:500],
                        "doi": doi,
                        "url": "https://doi.org/" + quote(doi, safe="/"),
                        "status": "candidate-not-reviewed",
                    }
                )
            return {
                "provider": "Crossref",
                "notice": "Metadata matches only. Read the source and evaluate whether it supports or contradicts the claim. No verdict was produced.",
                "sources": result,
            }
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise DomainError(
            "Source lookup is unavailable. The transcript and notes remain usable; retry later."
        ) from None
