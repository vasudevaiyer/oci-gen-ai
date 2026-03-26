from types import SimpleNamespace

from backend.app.retrieval import RetrievalService


class StubGenAi:
    def __init__(
        self,
        intents_by_query: dict[str, set[str]] | None = None,
        rewrites_by_query: dict[str, list[str]] | None = None,
        reranks_by_query: dict[str, list[str]] | None = None,
        profiles_by_query: dict[str, dict[str, object]] | None = None,
        *,
        raises: bool = False,
        rewrite_raises: bool = False,
        rerank_raises: bool = False,
        profile_raises: bool = False,
    ) -> None:
        self.intents_by_query = intents_by_query or {}
        self.rewrites_by_query = rewrites_by_query or {}
        self.reranks_by_query = reranks_by_query or {}
        self.profiles_by_query = profiles_by_query or {}
        self.raises = raises
        self.rewrite_raises = rewrite_raises
        self.rerank_raises = rerank_raises
        self.profile_raises = profile_raises

    def understand_query_for_retrieval(self, question: str, *, limit: int = 3) -> dict[str, object]:
        if self.profile_raises:
            raise RuntimeError("query understanding unavailable")
        profile = self.profiles_by_query.get(question)
        if profile is None:
            return {
                "intents": list(self.intents_by_query.get(question, set())),
                "answer_shape": "",
                "evidence_types": [],
                "rewrites": self.rewrites_by_query.get(question, [])[:limit],
            }
        return {
            "intents": profile.get("intents", []),
            "answer_shape": profile.get("answer_shape", ""),
            "evidence_types": profile.get("evidence_types", []),
            "rewrites": profile.get("rewrites", [])[:limit],
        }

    def classify_query_intents(self, question: str) -> set[str]:
        if self.raises:
            raise RuntimeError("intent service unavailable")
        return self.intents_by_query.get(question, set())

    def expand_query_for_retrieval(self, question: str) -> list[str]:
        if self.rewrite_raises:
            raise RuntimeError("rewrite service unavailable")
        return self.rewrites_by_query.get(question, [])

    def rerank_retrieval_candidates(self, question: str, candidates: list[dict[str, str]], *, limit: int = 6) -> list[str]:
        if self.rerank_raises:
            raise RuntimeError("rerank service unavailable")
        allowed_ids = {candidate["chunk_id"] for candidate in candidates}
        return [candidate_id for candidate_id in self.reranks_by_query.get(question, []) if candidate_id in allowed_ids][:limit]


def _service(
    intents_by_query: dict[str, set[str]] | None = None,
    rewrites_by_query: dict[str, list[str]] | None = None,
    reranks_by_query: dict[str, list[str]] | None = None,
    profiles_by_query: dict[str, dict[str, object]] | None = None,
    *,
    raises: bool = False,
    rewrite_raises: bool = False,
    rerank_raises: bool = False,
    profile_raises: bool = False,
) -> RetrievalService:
    service = RetrievalService.__new__(RetrievalService)
    service.settings = SimpleNamespace(max_context_images=4)
    service.store = None
    service.genai = StubGenAi(
        intents_by_query,
        rewrites_by_query,
        reranks_by_query,
        profiles_by_query,
        raises=raises,
        rewrite_raises=rewrite_raises,
        rerank_raises=rerank_raises,
        profile_raises=profile_raises,
    )
    service._query_profile_cache = {}
    service._intent_cache = {}
    service._rerank_cache = {}
    return service


def test_hybrid_rank_prefers_procedure_chunks_for_how_to_queries() -> None:
    question = "How do I start the failover workflow?"
    rerank_key = "\n".join((f"Question: {question}", "Expected answer shape: steps"))
    service = _service(reranks_by_query={rerank_key: ["proc", "policy"]})
    matches = [
        {
            "chunk_id": "policy",
            "document_id": "doc-1",
            "source_path": "policy.docx",
            "title": "Access Policy",
            "section_path": ["Access Policy", "Controls"],
            "content": "Managers must approve access reviews.",
            "chunk_type": "policy_clause_chunk",
            "image_refs": [],
            "metadata": {"document_archetype": "regulatory"},
            "score": 0.82,
        },
        {
            "chunk_id": "proc",
            "document_id": "doc-2",
            "source_path": "runbook.docx",
            "title": "Failover",
            "section_path": ["Runbook", "Failover"],
            "content": "Step 1. Start the failover workflow and verify standby health.",
            "chunk_type": "procedure_chunk",
            "image_refs": ["assets/failover.png"],
            "metadata": {"document_archetype": "procedural"},
            "score": 0.79,
        },
    ]

    ranked = service._hybrid_rank(question, matches, top_k=2)

    assert ranked[0]["chunk_id"] == "proc"


def test_hybrid_rank_prefers_policy_chunks_for_policy_queries() -> None:
    question = "What does the access policy require for approval exceptions?"
    rerank_key = "\n".join((f"Question: {question}", "Expected answer shape: summary"))
    service = _service(reranks_by_query={rerank_key: ["policy", "proc"]})
    matches = [
        {
            "chunk_id": "proc",
            "document_id": "doc-2",
            "source_path": "runbook.docx",
            "title": "Failover",
            "section_path": ["Runbook", "Failover"],
            "content": "Step 1. Start the failover workflow and verify standby health.",
            "chunk_type": "procedure_chunk",
            "image_refs": ["assets/failover.png"],
            "metadata": {"document_archetype": "procedural"},
            "score": 0.82,
        },
        {
            "chunk_id": "policy",
            "document_id": "doc-1",
            "source_path": "policy.docx",
            "title": "Access Policy",
            "section_path": ["Access Policy", "Controls"],
            "content": "Managers must approve access reviews and document all exceptions.",
            "chunk_type": "policy_clause_chunk",
            "image_refs": [],
            "metadata": {"document_archetype": "regulatory"},
            "score": 0.79,
        },
    ]

    ranked = service._hybrid_rank(question, matches, top_k=2)

    assert ranked[0]["chunk_id"] == "policy"


def test_hybrid_rank_prefers_policy_chunks_for_entitlement_queries() -> None:
    question = "How many days can I work from home?"
    rerank_key = "\n".join((f"Question: {question}", "Expected answer shape: summary"))
    service = _service(reranks_by_query={rerank_key: ["policy", "proc"]})
    matches = [
        {
            "chunk_id": "proc",
            "document_id": "doc-1",
            "source_path": "employee-guide.docx",
            "title": "Remote Access Setup",
            "section_path": ["Employee Guide", "Remote Access"],
            "content": "Step 1. Connect to VPN before accessing internal tools from home.",
            "chunk_type": "procedure_chunk",
            "image_refs": [],
            "metadata": {"document_archetype": "procedural"},
            "score": 0.83,
        },
        {
            "chunk_id": "policy",
            "document_id": "doc-2",
            "source_path": "hybrid-policy.docx",
            "title": "Hybrid Work Policy",
            "section_path": ["Policies", "Hybrid Work"],
            "content": "Employees may work from home up to two days per week with manager approval.",
            "chunk_type": "policy_clause_chunk",
            "image_refs": [],
            "metadata": {"document_archetype": "regulatory"},
            "matched_queries": ["remote work policy"],
            "score": 0.79,
        },
    ]

    ranked = service._hybrid_rank(question, matches, top_k=2)

    assert ranked[0]["chunk_id"] == "policy"


def test_hybrid_rank_respects_ai_rerank_for_cross_lingual_policy_pages() -> None:
    question = "How many days can I work from home?"
    rerank_key = "\n".join((f"Question: {question}", "Expected answer shape: summary"))
    service = _service(reranks_by_query={rerank_key: ["page-3", "page-4"]})
    matches = [
        {
            "chunk_id": "page-4",
            "document_id": "doc-policy",
            "source_path": "policy.pdf",
            "title": "Page 4",
            "section_path": ["Policy", "Page 4"],
            "content": "General remote-work rules and responsibilities.",
            "chunk_type": "section_chunk",
            "image_refs": [],
            "metadata": {"document_archetype": "regulatory"},
            "score": 0.45,
        },
        {
            "chunk_id": "page-3",
            "document_id": "doc-policy",
            "source_path": "policy.pdf",
            "title": "Page 3",
            "section_path": ["Policy", "Page 3"],
            "content": "Remote work based on employee request may not exceed 30 days per year.",
            "chunk_type": "section_chunk",
            "image_refs": [],
            "metadata": {"document_archetype": "regulatory"},
            "score": 0.44,
        },
    ]

    ranked = service._hybrid_rank(question, matches, top_k=2)

    assert ranked[0]["chunk_id"] == "page-3"


def test_rerank_images_prefers_visual_caption_match() -> None:
    question = "Show me the topology diagram"
    service = _service(intents_by_query={question: {"visual"}})
    matches = [
        {
            "image_id": "img-1",
            "image_path": "assets/plain.png",
            "caption_text": "General dashboard view",
            "source_path": "guide.pdf",
            "section_path": ["Guide", "Overview"],
            "score": 0.84,
        },
        {
            "image_id": "img-2",
            "image_path": "assets/diagram.png",
            "caption_text": "Disaster recovery topology diagram",
            "source_path": "design.pdf",
            "section_path": ["Design", "Architecture"],
            "score": 0.78,
        },
    ]

    ranked = service._rerank_images(question, matches, top_k=2)

    assert ranked[0]["image_id"] == "img-2"


def test_falls_back_to_embedding_and_lexical_signals_when_ai_rerank_fails() -> None:
    question = "Show me the topology diagram"
    service = _service(rerank_raises=True)
    matches = [
        {
            "chunk_id": "text",
            "document_id": "doc-1",
            "source_path": "design.docx",
            "title": "Architecture",
            "section_path": ["Design", "Architecture"],
            "content": "The service runs in two regions with standby failover.",
            "chunk_type": "section_chunk",
            "image_refs": [],
            "metadata": {"document_archetype": "technical"},
            "score": 0.80,
        },
        {
            "chunk_id": "visual",
            "document_id": "doc-2",
            "source_path": "design.pdf",
            "title": "Architecture Diagram",
            "section_path": ["Design", "Architecture Diagram"],
            "content": "Figure 2: Multi-region disaster recovery workflow.",
            "chunk_type": "figure_explainer_chunk",
            "image_refs": ["assets/diagram.png"],
            "metadata": {"document_archetype": "mixed_multimodal"},
            "score": 0.78,
        },
    ]

    ranked = service._hybrid_rank(question, matches, top_k=2)

    assert ranked[0]["chunk_id"] == "visual"


def test_search_queries_include_query_profile_rewrites() -> None:
    question = "How many days can I work from home?"
    service = _service(
        profiles_by_query={
            question: {
                "intents": ["regulatory", "reference"],
                "answer_shape": "limit",
                "evidence_types": ["policy", "section"],
                "rewrites": ["remote work policy", "العمل عن بعد"],
            }
        }
    )

    queries = service._search_queries(question)

    assert queries == [question, "remote work policy", "العمل عن بعد"]


def test_search_queries_fall_back_to_original_when_query_understanding_and_rewrite_fail() -> None:
    question = "How many days can I work from home?"
    service = _service(profile_raises=True, rewrite_raises=True)

    queries = service._search_queries(question)

    assert queries == [question]


def test_rewrite_matched_queries_boost_cross_lingual_policy_chunks() -> None:
    question = "How many days can I work from home?"
    rerank_key = "\n".join((f"Question: {question}", "Expected answer shape: summary"))
    service = _service(reranks_by_query={rerank_key: ["policy", "dr"]})
    matches = [
        {
            "chunk_id": "dr",
            "document_id": "doc-1",
            "source_path": "dr.pdf",
            "title": "Technical Brief",
            "section_path": ["Technical Brief", "Operations"],
            "content": "Start the servers in the secondary site during planned maintenance.",
            "chunk_type": "narrative_chunk",
            "image_refs": [],
            "metadata": {"document_archetype": "technical"},
            "matched_queries": [question],
            "score": 0.28,
        },
        {
            "chunk_id": "policy",
            "document_id": "doc-2",
            "source_path": "policy.pdf",
            "title": "Remote Work Policy",
            "section_path": ["Policy", "Remote Work"],
            "content": "Employees may work remotely up to 30 days per year.",
            "chunk_type": "narrative_chunk",
            "image_refs": [],
            "metadata": {"document_archetype": "knowledge"},
            "matched_queries": ["remote work policy", "سياسة العمل عن بعد"],
            "score": 0.26,
        },
    ]

    ranked = service._hybrid_rank(question, matches, top_k=2)

    assert ranked[0]["chunk_id"] == "policy"


def test_visual_queries_prefer_directly_linked_images_over_generic_same_document_images() -> None:
    question = "Show me the physical architecture"
    service = _service(intents_by_query={question: {"visual"}})
    chunk_matches = [
        {
            "chunk_id": "arch-1",
            "document_id": "doc-arch",
            "source_path": "arch.docx",
            "title": "Physical Architecture",
            "section_path": ["Architecture", "Physical Architecture"],
            "content": "The physical architecture diagram below illustrates the components.",
            "chunk_type": "figure_explainer_chunk",
            "image_refs": ["assets/physical-arch.png"],
            "metadata": {},
            "score": 0.88,
        }
    ]
    image_matches = [
        {
            "image_id": "img-linked",
            "document_id": "doc-arch",
            "related_chunk_id": "arch-1",
            "image_path": "assets/physical-arch.png",
            "caption_text": "Physical architecture diagram.",
            "source_path": "arch.docx",
            "section_path": ["Architecture", "Physical Architecture"],
            "score": 0.32,
        },
        {
            "image_id": "img-generic",
            "document_id": "doc-arch",
            "related_chunk_id": "other",
            "image_path": "assets/cover.png",
            "caption_text": "Generic cover image.",
            "source_path": "arch.docx",
            "section_path": ["Architecture"],
            "score": 0.61,
        },
    ]

    filtered = service._candidate_images_for_query(question, chunk_matches, image_matches)

    assert [image["image_id"] for image in filtered] == ["img-linked"]


def test_non_visual_queries_only_keep_images_linked_to_top_chunks() -> None:
    question = "How many days can I work from home?"
    service = _service()
    chunk_matches = [
        {
            "chunk_id": "policy-1",
            "document_id": "doc-policy",
            "source_path": "policy.pdf",
            "title": "Remote Work Policy",
            "section_path": ["Policy", "Remote Work"],
            "content": "Employees may work remotely up to 30 days per year.",
            "chunk_type": "policy_clause_chunk",
            "image_refs": ["assets/policy-page-3.png"],
            "metadata": {"document_archetype": "regulatory"},
            "score": 0.81,
        }
    ]
    image_matches = [
        {
            "image_id": "img-policy",
            "document_id": "doc-policy",
            "related_chunk_id": "policy-1",
            "image_path": "assets/policy-page-3.png",
            "caption_text": "Page 3 remote work policy.",
            "source_path": "policy.pdf",
            "section_path": ["Policy", "Remote Work"],
            "score": 0.42,
        },
        {
            "image_id": "img-foreign",
            "document_id": "doc-dr",
            "related_chunk_id": "dr-9",
            "image_path": "assets/dr-architecture.png",
            "caption_text": "Disaster recovery architecture diagram.",
            "source_path": "dr.pdf",
            "section_path": ["Architecture"],
            "score": 0.60,
        },
    ]

    filtered = service._candidate_images_for_query(question, chunk_matches, image_matches)

    assert [image["image_id"] for image in filtered] == ["img-policy"]


def test_hybrid_rank_consolidates_same_section_and_keeps_richer_chunk() -> None:
    question = "How many days can I work from home?"
    rerank_key = "\n".join((f"Question: {question}", "Expected answer shape: summary"))
    service = _service(reranks_by_query={rerank_key: ["thin", "rich", "other"]})
    matches = [
        {
            "chunk_id": "thin",
            "document_id": "doc-policy",
            "source_path": "policy.pdf",
            "title": "Article 4",
            "section_path": ["Policy", "Remote Work", "Article 4"],
            "content": "Article 4",
            "chunk_type": "section_chunk",
            "image_refs": [],
            "metadata": {},
            "score": 0.57,
        },
        {
            "chunk_id": "rich",
            "document_id": "doc-policy",
            "source_path": "policy.pdf",
            "title": "Article 4",
            "section_path": ["Policy", "Remote Work", "Article 4"],
            "content": "Employees may work from home up to 30 days per year with manager approval.",
            "chunk_type": "section_chunk",
            "image_refs": [],
            "metadata": {},
            "score": 0.52,
        },
        {
            "chunk_id": "other",
            "document_id": "doc-policy",
            "source_path": "policy.pdf",
            "title": "Article 5",
            "section_path": ["Policy", "Remote Work", "Article 5"],
            "content": "General responsibilities apply to remote work staff.",
            "chunk_type": "section_chunk",
            "image_refs": [],
            "metadata": {},
            "score": 0.50,
        },
    ]

    ranked = service._hybrid_rank(question, matches, top_k=3)

    assert [match["chunk_id"] for match in ranked] == ["rich", "other"]


def test_reference_queries_prefer_structured_parameter_chunks() -> None:
    question = "What network ports are required for the system?"
    service = _service(
        profiles_by_query={
            question: {
                "intents": ["reference", "technical"],
                "answer_shape": "parameter_list",
                "evidence_types": ["table", "configuration"],
                "rewrites": ["required network ports", "firewall port list"],
            }
        }
    )
    matches = [
        {
            "chunk_id": "narrative",
            "document_id": "doc-1",
            "source_path": "guide.pdf",
            "title": "Networking Overview",
            "section_path": ["Guide", "Networking"],
            "content": "The system uses secure communication between components across sites.",
            "chunk_type": "section_chunk",
            "image_refs": [],
            "metadata": {},
            "score": 0.84,
        },
        {
            "chunk_id": "table",
            "document_id": "doc-1",
            "source_path": "guide.pdf",
            "title": "Required Ports",
            "section_path": ["Guide", "Networking", "Ports"],
            "content": "Port: 22 | Purpose: SSH\nPort: 1521 | Purpose: Listener\nPort: 7001 | Purpose: Admin",
            "chunk_type": "table_chunk",
            "image_refs": [],
            "metadata": {},
            "score": 0.79,
        },
    ]

    ranked = service._hybrid_rank(question, matches, top_k=2)

    assert ranked[0]["chunk_id"] == "table"
