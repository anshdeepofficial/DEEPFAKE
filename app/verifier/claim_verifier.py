"""Source-backed claim verification for DeepGuard.

The verifier deliberately separates retrieval from truth judgement. It can use a
zero-key public-web bootstrap search and, when configured, Google's Fact Check
Tools API. The result is evidence-oriented: links, source types, support/
contradiction signals and verification questions are returned instead of a
fabricated certainty score.
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
import re
from dataclasses import asdict, dataclass
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://html.duckduckgo.com/html/?q={query}"
_FACT_CHECK_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/153.0 Safari/537.36 DeepGuard/1.2"
)
_MAX_RESULTS = 12

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by",
    "for", "from", "had", "has", "have", "he", "her", "his", "i", "in", "is",
    "it", "its", "of", "on", "or", "our", "she", "that", "the", "their", "them",
    "they", "this", "to", "was", "we", "were", "will", "with", "you", "your",
    "said", "says", "say", "according", "about",
}
_NEGATIONS = {
    "no", "not", "never", "false", "deny", "denied", "denies", "cannot", "cant",
    "won't", "wont", "didn't", "didnt",
}
_CLAIM_HINTS = {
    "said", "says", "announced", "announces", "claimed", "claims", "will",
    "would", "has", "have", "is", "are", "approved", "banned", "reduced",
    "increase", "increased", "decrease", "decreased", "launched", "confirmed",
    "promised", "pledged", "implemented", "passed", "signed",
}
_PROMISE_HINTS = {
    "will", "would", "promise", "promised", "pledge", "pledged", "plan", "plans",
    "planned", "intend", "intends", "expected", "target",
}
_ATTRIBUTION_HINTS = {
    "said", "says", "announced", "claimed", "stated", "told", "confirmed",
}
_OUTCOME_HINTS = {
    "implemented", "happened", "reduced", "increased", "passed", "signed",
    "launched", "completed", "delivered", "became", "effective",
}


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    domain: str
    relevance: float = 0.0
    stance: str = "related"
    source_type: str = "web"
    quality: float = 0.5
    published_at: str | None = None
    publisher: str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["relevance"] = round(self.relevance, 3)
        data["quality"] = round(self.quality, 3)
        return data


class ClaimVerifier:
    """Retrieve public evidence and produce an evidence-oriented verdict."""

    def __init__(self, timeout_seconds: float = 8.0):
        self.timeout_seconds = timeout_seconds
        self.fact_check_api_key = os.getenv("GOOGLE_FACT_CHECK_API_KEY", "").strip()
        self.fact_check_language = os.getenv("DEEPGUARD_FACT_CHECK_LANGUAGE", "").strip()

    def capabilities(self) -> dict:
        return {
            "web_search": "duckduckgo_html_bootstrap",
            "google_fact_check": bool(self.fact_check_api_key),
            "claim_decomposition": True,
            "unicode_queries": True,
        }

    async def verify(
        self,
        claim: str | None,
        *,
        context_url: str | None = None,
        page_title: str | None = None,
        page_text: str | None = None,
    ) -> dict:
        clean_claim = self._clean_claim(claim or "")
        if not clean_claim:
            clean_claim = self.extract_claim(page_text or "")
        if len(clean_claim) < 12:
            return self._empty_result(
                clean_claim,
                "No clear factual claim was selected. Select a sentence containing a checkable statement.",
            )

        query = self._build_query(clean_claim, page_title)
        providers_used: list[str] = []
        warnings: list[str] = []

        web_task = asyncio.create_task(self._safe_web_search(query))
        fact_task = (
            asyncio.create_task(self._safe_fact_check_search(clean_claim))
            if self.fact_check_api_key
            else None
        )

        web_results, web_error = await web_task
        if web_results:
            providers_used.append("duckduckgo_html")
        if web_error:
            warnings.append(web_error)

        fact_results: list[SearchResult] = []
        if fact_task:
            fact_results, fact_error = await fact_task
            if fact_results:
                providers_used.append("google_fact_check")
            if fact_error:
                warnings.append(fact_error)

        all_results = self._deduplicate([*fact_results, *web_results])
        if not all_results and web_error:
            result = self._empty_result(
                clean_claim,
                "Live evidence providers are currently unavailable. No verdict was fabricated.",
                status="SEARCH_UNAVAILABLE",
            )
            result.update({
                "query": query,
                "providers_used": providers_used,
                "warnings": warnings,
                "claim_kind": self.classify_claim_kind(clean_claim),
                "verification_questions": self.verification_questions(clean_claim),
            })
            return result

        source_domain = ""
        if context_url:
            source_domain = urlparse(context_url).netloc.lower().removeprefix("www.")

        evaluated = self.evaluate_evidence(
            clean_claim,
            all_results,
            exclude_domain=source_domain,
        )
        evaluated.update({
            "claim": clean_claim,
            "query": query,
            "context_url": context_url,
            "page_title": page_title,
            "claim_kind": self.classify_claim_kind(clean_claim),
            "verification_questions": self.verification_questions(clean_claim),
            "providers_used": providers_used,
            "warnings": warnings,
            "method": "source_backed_verification_v2",
            "calibrated": False,
            "disclaimer": (
                "Evidence strength is not a mathematical probability that the claim is true. "
                "Coverage can be incomplete, sources can repeat one another, and breaking claims "
                "may not yet have independent confirmation."
            ),
        })
        return evaluated

    async def _safe_web_search(self, query: str) -> tuple[list[SearchResult], str | None]:
        searches = await asyncio.gather(
            self.search(query),
            self.search(f"{query} fact check"),
            return_exceptions=True,
        )
        combined: list[SearchResult] = []
        failures = 0
        for result in searches:
            if isinstance(result, Exception):
                failures += 1
                logger.warning("Public web search branch failed: %s", result)
                continue
            combined.extend(result)
        if not combined:
            return [], "Public web search was unavailable."
        warning = "One public-web search path was unavailable; results may be incomplete." if failures else None
        return self._deduplicate(combined), warning

    async def _safe_fact_check_search(
        self, claim: str
    ) -> tuple[list[SearchResult], str | None]:
        try:
            return await self.search_fact_checks(claim), None
        except Exception as exc:
            logger.warning("Google Fact Check search failed: %s", exc)
            return [], "Google Fact Check lookup was unavailable."

    async def search(self, query: str) -> list[SearchResult]:
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

    async def search_fact_checks(self, claim: str) -> list[SearchResult]:
        if not self.fact_check_api_key:
            return []

        params: dict[str, str | int] = {
            "query": claim[:500],
            "pageSize": 10,
            "key": self.fact_check_api_key,
        }
        if self.fact_check_language:
            params["languageCode"] = self.fact_check_language

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=False,
        ) as client:
            response = await client.get(_FACT_CHECK_URL, params=params)
            response.raise_for_status()
            payload = response.json()

        results: list[SearchResult] = []
        for claim_item in payload.get("claims", []) or []:
            checked_text = str(claim_item.get("text") or "").strip()
            claimant = str(claim_item.get("claimant") or "").strip()
            for review in claim_item.get("claimReview", []) or []:
                url = str(review.get("url") or "").strip()
                publisher_obj = review.get("publisher") or {}
                publisher = str(publisher_obj.get("name") or "").strip()
                site = str(publisher_obj.get("site") or "").strip()
                domain = (
                    urlparse(url).netloc.lower().removeprefix("www.")
                    or site.lower().removeprefix("www.")
                )
                rating = str(review.get("textualRating") or "").strip()
                title = str(review.get("title") or "").strip() or checked_text
                snippet_parts = [x for x in (
                    f"Claim: {checked_text}" if checked_text else "",
                    f"Claimant: {claimant}" if claimant else "",
                    f"Rating: {rating}" if rating else "",
                ) if x]
                stance = self._fact_check_stance(rating)
                results.append(SearchResult(
                    title=title[:240],
                    url=url,
                    snippet=" · ".join(snippet_parts)[:700],
                    domain=domain,
                    stance=stance,
                    source_type="fact_check",
                    quality=0.95,
                    published_at=str(review.get("reviewDate") or "") or None,
                    publisher=publisher or None,
                ))
                if len(results) >= _MAX_RESULTS:
                    return results
        return results

    @classmethod
    def extract_claim(cls, page_text: str) -> str:
        text = re.sub(r"\s+", " ", page_text or " ").strip()
        if not text:
            return ""
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?।])\s+", text)
            if 25 <= len(s.strip()) <= 500
        ]
        if not sentences:
            return text[:500]

        def score(sentence: str) -> tuple[int, int]:
            words = set(cls._tokens(sentence))
            hint_hits = len(words & _CLAIM_HINTS)
            has_number = int(bool(re.search(r"\d+(?:\.\d+)?%?|₹|\$", sentence)))
            has_proper = int(bool(re.search(r"\b[A-Z][a-z]{2,}\b", sentence)))
            quote_like = int('"' in sentence or "“" in sentence or "”" in sentence)
            return (
                hint_hits * 3 + has_number * 2 + has_proper + quote_like,
                min(len(sentence), 220),
            )

        return max(sentences, key=score)[:500]

    @classmethod
    def classify_claim_kind(cls, claim: str) -> str:
        tokens = set(cls._tokens(claim))
        has_promise = bool(tokens & _PROMISE_HINTS)
        has_attribution = bool(tokens & _ATTRIBUTION_HINTS)
        has_outcome = bool(tokens & _OUTCOME_HINTS)
        if has_promise and has_attribution:
            return "attributed_promise"
        if has_promise:
            return "promise_or_future_claim"
        if has_outcome:
            return "outcome_or_event_claim"
        if has_attribution:
            return "attributed_statement"
        return "factual_claim"

    @classmethod
    def verification_questions(cls, claim: str) -> list[str]:
        kind = cls.classify_claim_kind(claim)
        questions = ["Do independent sources report the same core claim?"]
        if kind in {"attributed_promise", "attributed_statement"}:
            questions.insert(0, "Did the named person or organisation actually make this statement?")
        if kind in {"attributed_promise", "promise_or_future_claim"}:
            questions.append("Was the promised action formally announced or documented?")
            questions.append("If the effective date has passed, was the promise actually implemented?")
        if kind == "outcome_or_event_claim":
            questions.append("Did the claimed event or outcome occur at the stated time and place?")
        return questions

    @classmethod
    def evaluate_evidence(
        cls,
        claim: str,
        results: Iterable[SearchResult],
        *,
        exclude_domain: str = "",
    ) -> dict:
        evaluated: list[SearchResult] = []
        supporting_domains: set[str] = set()
        contradicting_domains: set[str] = set()
        relevant_domains: set[str] = set()
        source_types: set[str] = set()

        for item in results:
            combined = f"{item.title}. {item.snippet}".strip()
            item.relevance = cls._relevance(claim, combined)
            if item.source_type != "fact_check" or item.stance == "related":
                item.stance = cls._stance(claim, combined, item.relevance)
            item.quality = max(item.quality, cls._source_quality(item.domain, item.source_type))

            if item.relevance >= 0.16 or item.source_type == "fact_check":
                evaluated.append(item)
                if item.domain:
                    relevant_domains.add(item.domain)
                source_types.add(item.source_type)

                is_origin = bool(exclude_domain and item.domain == exclude_domain)
                if is_origin:
                    continue
                if item.stance == "supporting" and item.domain:
                    supporting_domains.add(item.domain)
                elif item.stance == "contradicting" and item.domain:
                    contradicting_domains.add(item.domain)

        evaluated.sort(
            key=lambda r: (
                r.source_type == "fact_check",
                r.quality,
                r.relevance,
            ),
            reverse=True,
        )

        support = len(supporting_domains)
        contradict = len(contradicting_domains)
        fact_support = any(
            r.source_type == "fact_check" and r.stance == "supporting" for r in evaluated
        )
        fact_contradict = any(
            r.source_type == "fact_check" and r.stance == "contradicting" for r in evaluated
        )

        if fact_support and not fact_contradict and contradict == 0:
            verdict = "SUPPORTED"
        elif fact_contradict and not fact_support and support == 0:
            verdict = "DISPUTED"
        elif support >= 2 and contradict == 0:
            verdict = "SUPPORTED"
        elif contradict >= 2 and support == 0:
            verdict = "DISPUTED"
        elif (support >= 1 and contradict >= 1) or (fact_support and fact_contradict):
            verdict = "MIXED"
        else:
            verdict = "INCONCLUSIVE"

        coverage = min(1.0, len(relevant_domains) / 5.0)
        agreement = min(1.0, max(support, contradict) / 3.0)
        avg_relevance = (
            sum(r.relevance * r.quality for r in evaluated[:6]) / min(len(evaluated), 6)
            if evaluated else 0.0
        )
        fact_bonus = 0.15 if (fact_support or fact_contradict) else 0.0
        evidence_strength = min(
            1.0,
            0.30 * coverage + 0.30 * agreement + 0.40 * avg_relevance + fact_bonus,
        )
        if verdict == "INCONCLUSIVE":
            evidence_strength = min(evidence_strength, 0.49)

        return {
            "status": "OK",
            "verdict": verdict,
            "confidence": round(evidence_strength * 100, 1),
            "confidence_name": "evidence_strength",
            "supporting_sources": support,
            "contradicting_sources": contradict,
            "independent_domains": len(relevant_domains),
            "source_types": sorted(source_types),
            "evidence": [r.to_dict() for r in evaluated[:_MAX_RESULTS]],
        }

    @staticmethod
    def _clean_claim(claim: str) -> str:
        return re.sub(r"\s+", " ", claim).strip()[:2000]

    @classmethod
    def _build_query(cls, claim: str, page_title: str | None) -> str:
        terms: list[str] = []
        for token in cls._query_tokens(claim):
            if len(token) < 2 or token.lower() in _STOPWORDS:
                continue
            if token.lower() not in {t.lower() for t in terms}:
                terms.append(token)
            if len(terms) >= 14:
                break
        query = " ".join(terms) or claim[:360]
        if page_title:
            for token in cls._query_tokens(page_title)[:6]:
                if token.lower() not in _STOPWORDS and token.lower() not in {
                    t.lower() for t in terms
                }:
                    query += f" {token}"
        return query[:500].strip()

    @staticmethod
    def _query_tokens(text: str) -> list[str]:
        return re.findall(
            r"[^\W_]+(?:['’-][^\W_]+)?|\d+(?:\.\d+)?%?|[₹$]",
            text,
            flags=re.UNICODE,
        )

    @classmethod
    def _tokens(cls, text: str) -> set[str]:
        return {
            token.casefold().replace("’", "'")
            for token in cls._query_tokens(text)
            if len(token) > 1 and token.casefold() not in _STOPWORDS
        }

    @classmethod
    def _relevance(cls, claim: str, evidence: str) -> float:
        a = cls._tokens(claim)
        b = cls._tokens(evidence)
        if not a or not b:
            return 0.0
        overlap = len(a & b) / max(len(a), 1)
        numeric_claim = set(re.findall(r"\d+(?:\.\d+)?%?", claim))
        numeric_hits = sum(1 for x in numeric_claim if x and x in evidence)
        number_bonus = min(0.15, numeric_hits * 0.05)
        proper = set(re.findall(r"\b[A-Z][A-Za-z.-]{2,}\b", claim))
        proper_hits = sum(1 for x in proper if x.casefold() in evidence.casefold())
        proper_bonus = min(0.15, proper_hits * 0.03)
        return min(1.0, overlap + number_bonus + proper_bonus)

    @classmethod
    def _stance(cls, claim: str, evidence: str, relevance: float) -> str:
        if relevance < 0.16:
            return "related"
        claim_tokens = cls._tokens(claim)
        evidence_tokens = cls._tokens(evidence)
        claim_neg = bool(claim_tokens & _NEGATIONS)
        evidence_neg = bool(evidence_tokens & _NEGATIONS)
        lower = evidence.casefold()
        contradiction_markers = (
            "false", "not true", "denied", "no evidence", "misleading", "debunked",
            "incorrect", "fabricated", "did not", "has not", "never said",
        )
        if any(marker in lower for marker in contradiction_markers) and relevance >= 0.22:
            return "contradicting"
        if claim_neg != evidence_neg and relevance >= 0.34:
            return "contradicting"
        if relevance >= 0.28:
            return "supporting"
        return "related"

    @staticmethod
    def _source_quality(domain: str, source_type: str) -> float:
        if source_type == "fact_check":
            return 0.95
        d = domain.lower()
        official_patterns = (
            ".gov", ".gov.", ".gov.in", ".nic.in", ".mil", "who.int", "un.org",
            "europa.eu",
        )
        if any(p in d for p in official_patterns):
            return 0.90
        if d:
            return 0.60
        return 0.40

    @staticmethod
    def _fact_check_stance(rating: str) -> str:
        lower = rating.casefold()
        if any(x in lower for x in (
            "false", "incorrect", "misleading", "fake", "pants on fire",
            "not true", "debunked",
        )):
            return "contradicting"
        if any(x in lower for x in (
            "true", "correct", "accurate",
        )) and not any(x in lower for x in ("half", "mostly", "partly", "partially")):
            return "supporting"
        return "related"

    @staticmethod
    def _deduplicate(results: Iterable[SearchResult]) -> list[SearchResult]:
        out: list[SearchResult] = []
        seen_urls: set[str] = set()
        for item in results:
            key = item.url.rstrip("/")
            if not key or key in seen_urls:
                continue
            seen_urls.add(key)
            out.append(item)
            if len(out) >= _MAX_RESULTS * 2:
                break
        return out

    @staticmethod
    def _parse_duckduckgo_html(raw_html: str) -> list[SearchResult]:
        blocks = re.split(
            r'<div[^>]+class="[^\"]*result[^\"]*"',
            raw_html,
            flags=re.I,
        )[1:]
        results: list[SearchResult] = []
        seen: set[str] = set()
        for block in blocks:
            link_match = re.search(
                r'<a[^>]+class="[^\"]*result__a[^\"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
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
            normalized = final_url.rstrip("/")
            if normalized in seen:
                continue
            seen.add(normalized)

            snippet_match = re.search(
                r'class="[^\"]*result__snippet[^\"]*"[^>]*>(.*?)</(?:a|div|span)>',
                block,
                flags=re.I | re.S,
            )
            snippet = (
                ClaimVerifier._strip_html(snippet_match.group(1))
                if snippet_match else ""
            )
            domain = parsed.netloc.lower().removeprefix("www.")
            results.append(SearchResult(
                title=title[:240],
                url=final_url,
                snippet=snippet[:700],
                domain=domain,
                source_type="official" if ClaimVerifier._source_quality(domain, "web") >= 0.9 else "web",
                quality=ClaimVerifier._source_quality(domain, "web"),
            ))
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
    def _empty_result(
        claim: str,
        message: str,
        status: str = "INSUFFICIENT_DATA",
    ) -> dict:
        return {
            "status": status,
            "claim": claim,
            "verdict": "INCONCLUSIVE",
            "confidence": 0.0,
            "confidence_name": "evidence_strength",
            "supporting_sources": 0,
            "contradicting_sources": 0,
            "independent_domains": 0,
            "source_types": [],
            "evidence": [],
            "message": message,
            "method": "source_backed_verification_v2",
            "calibrated": False,
        }
