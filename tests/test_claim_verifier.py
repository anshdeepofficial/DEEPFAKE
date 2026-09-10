from app.verifier.claim_verifier import ClaimVerifier, SearchResult


def test_extract_claim_prefers_checkable_sentence():
    text = (
        "Welcome to today's report. "
        "The ministry announced petrol prices will decrease by 5 percent from Monday. "
        "Readers can find more stories below."
    )
    claim = ClaimVerifier.extract_claim(text)
    assert "petrol prices" in claim.lower()


def test_multiple_independent_supporting_sources_can_support_claim():
    claim = "The ministry announced petrol prices will decrease by 5 percent from Monday."
    evidence = [
        SearchResult(
            title="Ministry announces petrol price decrease of 5 percent from Monday",
            url="https://ministry.example.gov/notice",
            snippet="The ministry announced petrol prices will decrease by 5 percent from Monday.",
            domain="ministry.example.gov",
        ),
        SearchResult(
            title="Petrol prices to decrease 5 percent from Monday",
            url="https://news.example/report",
            snippet="Officials confirmed the ministry announcement and the 5 percent petrol price decrease.",
            domain="news.example",
        ),
    ]
    result = ClaimVerifier.evaluate_evidence(claim, evidence)
    assert result["verdict"] == "SUPPORTED"
    assert result["supporting_sources"] >= 2


def test_no_evidence_returns_inconclusive():
    result = ClaimVerifier.evaluate_evidence("A specific factual claim happened yesterday.", [])
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["confidence"] <= 49
