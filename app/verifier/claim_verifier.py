"""Claim verification using live public-web evidence.

This module intentionally separates *evidence retrieval* from *truth scoring*.
It does not claim that search-engine agreement proves a statement true. Instead,
it gathers independent sources, measures relevance, detects simple support/
contradiction signals, and returns an evidence-oriented verdict with links.
"""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, asdict
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://html.duckduckgo.com/html/?q={query}"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/153.0 Safari/537.36 DeepGuard/1.1"
)
_MAX_RESULTS = 8

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but",
    "by", "for", "from", "had", "has", "have", "he", "her", "his", "i",
    "in", "is", "it", "its", "of", "on", "or", "our", "she", "that", "the",
    "their", "them", "they", "this", "to", "was", "we", "were", "will", "with",
    "you", "your", "said", "says", "say", "according", "about",
}
_NEGATIONS = {"no", "not", "never", "false", "deny", "denied", "denies", "won't", "cannot", "can't"}
_CLAIM_HINTS = {
    "said", "says", "announced", "announces", "claimed", "claims", "will",
    "would", "has", "have", "is", "are", "approved", "banned", "reduced",
    "increase", "increased", "decrease", "decreased", "launched", "confirmed",
}


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    domain: str
    relevance: float = 0.0
    stance: str = "related"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["relevance"] = round(self.relevance, 3)
        return data


class ClaimVerifier:
    """Retrieve public-web evidence and produce an evidence-oriented verdict."""

    def __init__(self, timeout_seconds: float = 8.0):
        self.timeout_seconds = timeout_seconds

    async def verify(
        self,
        claim: str | None,
        *,
        context_url: str | None = None,
        page_title: str | None = None,
        page_text: str | None = None,
    ) -> dict:
        clean_claim = (claim or "").strip()
        if not clean_claim:
            clean_claim = self.extract_claim(page_text or "")
        if len(clean_claim) < 12:
            return self._empty_result(
                clean_claim,
                "No clear factual claim was selected. Select a sentence containing a checkable statement.",
            )

        query = self._build_query(clean_claim, page_title)
        try:
            results = await self.search(query)
        except Exception as exc:
            logger.warning("Web evidence search failed: %s", exc)
            return self._empty_result(
                clean_claim,
                "Live web search is currently unavailable. No verdict was fabricated.",
                status="SEARCH_UNAVAILABLE",
            )

        source_domain = ""
        if context_url:
            source_domain = urlparse(context_url).netloc.lower().removeprefix("www.")
        evaluated = self.evaluate_evidence(clean_claim, results, exclude_domain=source_domain)
        evaluated.update({
            "claim": clean_claim,
            "query": query,
            "context_url": context_url,
            "page_title": page_title,
            "method": "live_web_evidence_v1",
            "disclaimer": (
                "This is an evidence-assistance result, not legal proof. Search coverage can be incomplete, "
                "sources can repeat each other, and breaking claims may not yet be independently reported."
            ),
        })
        return evaluated

    async def search(self, query: str) -> list[SearchResult]:
        """Search the public web without requiring an API key.

        DuckDuckGo's HTML endpoint is used as a zero-key bootstrap provider. The
        provider is isolated here so it can later be replaced with a licensed
        search API without changing the extension or API contract.
        """
        url = _SEARCH_URL.format(query=quote_plus(query[:500]))
        headers = {"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers=headers,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
        return self._parse_duckduckgo_html(response.text)

    @classmethod
    def extract_claim(cls, page_text: str) -> str:
        """Pick a likely checkable sentence from visible page text."""
        text = re.sub(r"\s+", " ", page_text or " ").strip()
        if not text:
            return ""
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if 25 <= len(s.strip()) <= 500]
        if not sentences:
            return text[:500]

        def score(sentence: str) -> tuple[int, int]:
            words = set(re.findall(r"[A-Za-z0-9₹$%']+", sentence.lower()))
            hint_hits = len(words & _CLAIM_HINTS)
            has_number = int(bool(re.search(r"\b\d+(?:\.\d+)?%?\b|₹|\$", sentence)))
            has_proper = int(bool(re.search(r"\b[A-Z][a-z]{2,}\b", sentence)))
            return (hint_hits * 3 + has_number * 2 + has_proper, min(len(sentence), 220))

        return max(sentences, key=score)[:500]

    @classmethod
    def evaluate_evidence(
        cls, claim: str, results: Iterable[SearchResult], *, exclude_domain: str = ""
    ) -> dict:
        evaluated: list[SearchResult] = []
        supporting_domains: set[str] = set()
        contradicting_domains: set[str] = set()

        for item in results:
            combined = f"{item.title}. {item.snippet}".strip()
            item.relevance = cls._relevance(claim, combined)
            item.stance = cls._stance(claim, combined, item.relevance)
            if item.relevance >= 0.18:
                evaluated.append(item)
                is_origin = bool(exclude_domain and item.domain == exclude_domain)
                if not is_origin and item.stance == "supporting":
                    supporting_domains.add(item.domain)
                elif not is_origin and item.stance == "contradicting":
                    contradicting_domains.add(item.domain)

        evaluated.sort(key=lambda r: r.relevance, reverse=True)
        support = len(supporting_domains)
        contradict = len(contradicting_domains)
        relevant_domains = {r.domain for r in evaluated if r.domain}

        if support >= 2 and contradict == 0:
            verdict = "SUPPORTED"
        elif contradict >= 2 and support == 0:
            verdict = "DISPUTED"
        elif support >= 1 and contradict >= 1:
            verdict = "MIXED"
        else:
            verdict = "INCONCLUSIVE"

        coverage = min(1.0, len(relevant_domains) / 4.0)
        agreement = min(1.0, max(support, contradict) / 3.0)
        avg_relevance = (
            sum(r.relevance for r in evaluated[:5]) / min(len(evaluated), 5)
            if evaluated else 0.0
        )
        confidence = round((0.35 * coverage + 0.35 * agreement + 0.30 * avg_relevance) * 100, 1)
        if verdict == "INCONCLUSIVE":
            confidence = min(confidence, 49.0)

        return {
            "status": "OK",
            "verdict": verdict,
            "confidence": confidence,
            "supporting_sources": support,
            "contradicting_sources": contradict,
            "independent_domains": len(relevant_domains),
            "evidence": [r.to_dict() for r in evaluated[:_MAX_RESULTS]],
        }

    @staticmethod
    def _build_query(claim: str, page_title: str | None) -> str:
        claim = re.sub(r"\s+", " ", claim).strip()
        raw_tokens = re.findall(r"[A-Za-z0-9₹$%'.-]+", claim)
        terms: list[str] = []
        for token in raw_tokens:
            clean = token.strip(".,'\"")
            if len(clean) < 3 or clean.lower() in _STOPWORDS:
                continue
            if clean.lower() not in {t.lower() for t in terms}:
                terms.append(clean)
            if len(terms) >= 12:
                break
        query = " ".join(terms) or claim[:360]
        if page_title:
            title_terms = [
                t for t in re.findall(r"[A-Za-z0-9₹$%'.-]+", page_title)
                if len(t) >= 3 and t.lower() not in _STOPWORDS
            ][:5]
            query = f"{query} {' '.join(title_terms)}".strip()
        return query[:500]

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token for token in re.findall(r"[a-z0-9₹$%']+", text.lower())
            if len(token) > 2 and token not in _STOPWORDS
        }

    @classmethod
    def _relevance(cls, claim: str, evidence: str) -> float:
        a = cls._tokens(claim)
        b = cls._tokens(evidence)
        if not a or not b:
            return 0.0
        overlap = len(a & b) / max(len(a), 1)
        anchors = set(re.findall(r"\b(?:[A-Z][A-Za-z.-]{2,}|\d+(?:\.\d+)?%?)\b", claim))
        anchor_hits = sum(1 for x in anchors if x.lower() in evidence.lower())
        anchor_bonus = min(0.25, anchor_hits * 0.05)
        return min(1.0, overlap + anchor_bonus)

    @classmethod
    def _stance(cls, claim: str, evidence: str, relevance: float) -> str:
        if relevance < 0.18:
            return "related"
        claim_neg = bool(cls._tokens(claim) & _NEGATIONS)
        evidence_neg = bool(cls._tokens(evidence) & _NEGATIONS)
        lower = evidence.lower()
        contradiction_markers = ("false", "not true", "denied", "no evidence", "misleading", "debunked")
        if any(marker in lower for marker in contradiction_markers) and relevance >= 0.25:
            return "contradicting"
        if claim_neg != evidence_neg and relevance >= 0.32:
            return "contradicting"
        if relevance >= 0.30:
            return "supporting"
        return "related"

    @staticmethod
    def _parse_duckduckgo_html(raw_html: str) -> list[SearchResult]:
        blocks = re.split(r'<div[^>]+class="[^"]*result[^"]*"', raw_html, flags=re.I)[1:]
        results: list[SearchResult] = []
        seen: set[str] = set()
        for block in blocks:
            link_match = re.search(
                r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                block,
                flags=re.I | re.S,
            )
            if not link_match:
                continue
            href = html.unescape(link_match.group(1))
            title = ClaimVerifier._strip_html(link_match.group(2))
            final_url = ClaimVerifier._decode_ddg_url(href)
            parsed = urlparse(final_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
            if final_url in seen:
                continue
            seen.add(final_url)

            snippet_match = re.search(
                r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|div|span)>',
                block,
                flags=re.I | re.S,
            )
            snippet = ClaimVerifier._strip_html(snippet_match.group(1)) if snippet_match else ""
            results.append(
                SearchResult(
                    title=title[:240],
                    url=final_url,
                    snippet=snippet[:700],
                    domain=parsed.netloc.lower().removeprefix("www."),
                )
            )
            if len(results) >= _MAX_RESULTS:
                break
        return results

    @staticmethod
    def _decode_ddg_url(url: str) -> str:
        if url.startswith("//"):
            url = "https:" + url
        parsed = urlparse(url)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            if target:
                return unquote(target)
        return url

    @staticmethod
    def _strip_html(value: str) -> str:
        value = re.sub(r"<[^>]+>", " ", value)
        value = html.unescape(value)
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _empty_result(claim: str, message: str, status: str = "INSUFFICIENT_DATA") -> dict:
        return {
            "status": status,
            "claim": claim,
            "verdict": "INCONCLUSIVE",
            "confidence": 0.0,
            "supporting_sources": 0,
            "contradicting_sources": 0,
            "independent_domains": 0,
            "evidence": [],
            "message": message,
            "method": "live_web_evidence_v1",
        }
