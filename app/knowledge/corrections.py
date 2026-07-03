from app.classifier.models import CATEGORIES
from app.knowledge.base import KnowledgeBase
from app.resolver.github import GitHubClient


async def handle_correction(
    payload: dict,
    kb: KnowledgeBase,
    gh: GitHubClient,
):
    reaction = payload.get("reaction", {})
    content = reaction.get("content", "")
    if content != "-1":
        return

    comment = payload.get("comment", {})
    issue = payload.get("issue", {})
    comment_body = comment.get("body", "")
    comment_id = comment.get("id")
    repo_full = payload.get("repository", {}).get("full_name", "")
    owner, repo = repo_full.split("/") if "/" in repo_full else ("", "")
    pr_number = issue.get("number")

    if not comment_id or not owner or not pr_number:
        return

    await gh.post_comment(
        owner, repo, pr_number,
        f"ci-doctor correction:\n\nWhat is the correct category? Reply with one of: {', '.join(CATEGORIES)}",
    )


async def apply_correction(
    reply_body: str,
    kb: KnowledgeBase,
    gh: GitHubClient,
    owner: str,
    repo: str,
    pr_number: int,
):
    clean = reply_body.strip().lower()
    if clean not in CATEGORIES:
        await gh.post_comment(
            owner, repo, pr_number,
            f"ci-doctor correction:\n\nInvalid category. Reply with one of: {', '.join(CATEGORIES)}",
        )
        return

    kb.update({
        "category": clean,
        "confidence": 0.95,
        "signatures": [f"corrected:{clean}"],
        "remediation": "User-corrected entry",
    })

    await gh.post_comment(
        owner, repo, pr_number,
        f"ci-doctor correction:\n\nUpdated knowledge base. '{clean}' will be used for similar failures going forward.",
    )
