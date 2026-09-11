from app.verifier.claim_verifier import ClaimVerifier, SearchResult


def test_extract_claim_prefers_checkable_sentence():
    text = (
        "Welcome to today's report. "
        "The ministry announced petrol prices will decrease by 5 percent from Monday. "
        "Readers can find more stories below."
    )
    claim = ClaimVerifier.extract_claim(text)
    assert "petrol prices" in claim.lower()


def test_claim_kind_for_attributed_promise():
    kind = ClaimVerifier.classify_claim_kind(
        "The minister announced petrol prices will decrease by 5 percent from Monday."
    )
    assert kind == "attributed_promise"
    questions = ClaimVerifier.verification_questions(
        "The minister announced petrol prices will decrease by 5 percent from Monday."
    )
    assert any("actually make" in q for q in questions)
    assert any("implemented" in q for q in questions)


def test_unicode_query_keeps_non_latin_words():
    query = ClaimVerifier._build_query(
        "सरकार ने कहा पेट्रोल की कीमत 5 रुपये कम होगी",
        None,
    )
    assert "पेट्रोल" in query
    assert "5" in query


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
    assert result["confidence_name"] == "evidence_strength"


def test_origin_domain_does_not_count_as_independent_support():
    claim = "The ministry announced petrol prices will decrease by 5 percent from Monday."
    evidence = [
        SearchResult(
            title="Original article",
            url="https://origin.example/story",
            snippet=claim,
            domain="origin.example",
        )
    ]
    result = ClaimVerifier.evaluate_evidence(
        claim, evidence, exclude_domain="origin.example"
    )
    assert result["supporting_sources"] == 0
    assert result["verdict"] == "INCONCLUSIVE"


def test_fact_check_rating_false_is_contradicting():
    assert ClaimVerifier._fact_check_stance("False") == "contradicting"
    assert ClaimVerifier._fact_check_stance("True") == "supporting"
    assert ClaimVerifier._fact_check_stance("Mostly true") == "related"


def test_no_evidence_returns_inconclusive():
    result = ClaimVerifier.evaluate_evidence(
        "A specific factual claim happened yesterday.", []
    )
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["confidence"] <= 49
