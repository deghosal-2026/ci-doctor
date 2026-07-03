from app.classifier.llm import classify_with_mlx
from app.classifier.models import Classification
from app.classifier.rules import load_rules, match_rules
from app.knowledge.base import KnowledgeBase


async def classify(
    log_snippet: str,
    kb: KnowledgeBase,
    rules_path: str,
    mlx_endpoint: str | None = None,
) -> Classification:
    kb_result = kb.query(log_snippet)
    if kb_result:
        return kb_result

    rules = load_rules(rules_path)
    rules_result = match_rules(log_snippet, rules)
    if rules_result:
        return rules_result

    if mlx_endpoint:
        llm_result = await classify_with_mlx(log_snippet, mlx_endpoint)
        if llm_result:
            return llm_result

    return Classification(
        category="unknown",
        root_cause="No matching rules or LLM response",
        confidence=0.0,
    )
