from app.classifier.models import Classification
from app.config import Settings
from app.knowledge.base import KnowledgeBase
from app.resolver.github import GitHubClient
from app.resolver.cloud_fix import generate_fix
from app.storage.decisions import write_decision


async def dispatch(
    classification: Classification,
    log_snippet: str,
    owner: str,
    repo: str,
    run_id: int,
    pr_number: int,
    job_id: int | None,
    cfg: Settings,
    gh: GitHubClient,
    kb: KnowledgeBase,
):
    cat = classification.category
    conf = classification.confidence
    threshold = cfg.confidence_threshold

    if cat == "unknown":
        await _escalate(gh, owner, repo, pr_number, classification, run_id)
        action = "escalate"
    elif conf >= threshold and cat == "flake":
        await _rerun(gh, owner, repo, pr_number, run_id, job_id, classification)
        action = "auto_rerun"
    elif conf >= threshold and cat in ("lint", "build", "dependency"):
        await _suggest_fix(gh, owner, repo, pr_number, run_id, classification, log_snippet, cfg)
        action = "suggest_fix"
    else:
        await _escalate(gh, owner, repo, pr_number, classification, run_id)
        action = "escalate"

    await write_decision(
        cfg.decisions_path,
        event_id=f"{run_id}",
        repo=f"{owner}/{repo}",
        commit_sha="",
        pr_number=pr_number,
        job_name="",
        category=cat,
        confidence=conf,
        action=action,
    )


async def _rerun(
    gh: GitHubClient, owner: str, repo: str, pr: int, run_id: int,
    job_id: int | None, c: Classification,
):
    await gh.post_comment(owner, repo, pr, _rerun_comment(c))
    if job_id:
        await gh.rerun_job(owner, repo, job_id)
        status = await _poll_rerun(gh, owner, repo, run_id)
        if status == "completed":
            await gh.post_comment(owner, repo, pr, _rerun_passed_comment())
        else:
            await gh.post_comment(owner, repo, pr, _rerun_failed_comment())


async def _suggest_fix(
    gh: GitHubClient, owner: str, repo: str, pr: int, run_id: int,
    c: Classification, snippet: str, cfg: Settings,
):
    diff = await gh.fetch_diff(owner, repo, pr)
    fix = await generate_fix(snippet, diff, cfg)
    if fix:
        await gh.post_comment(owner, repo, pr, _fix_comment(c, fix))
    else:
        await gh.post_comment(owner, repo, pr, _fix_skipped_comment(c))


async def _escalate(
    gh: GitHubClient, owner: str, repo: str, pr: int,
    c: Classification, run_id: int,
):
    await gh.post_comment(owner, repo, pr, _escalation_comment(c, run_id))


async def _poll_rerun(gh: GitHubClient, owner: str, repo: str, run_id: int) -> str:
    import asyncio

    for _ in range(20):
        data = await gh.fetch_run(owner, repo, run_id)
        status = data.get("status", "")
        if status == "completed":
            return "completed"
        await asyncio.sleep(30)
    return "timeout"


def _rerun_comment(c: Classification) -> str:
    return (
        "ci-doctor diagnosis:\n\n"
        f"Category: {c.category}\n"
        f"Confidence: {int(c.confidence * 100)}%\n"
        f"Root cause: {c.root_cause}\n"
        f"Action: auto-re-running job"
    )


def _rerun_passed_comment() -> str:
    return "ci-doctor update:\n\nRe-run passed. Flaky test confirmed. No action needed."


def _rerun_failed_comment() -> str:
    return "ci-doctor update:\n\nRe-run failed. Reclassifying and escalating."


def _fix_comment(c: Classification, fix: str) -> str:
    return (
        "ci-doctor diagnosis:\n\n"
        f"Category: {c.category}\n"
        f"Confidence: {int(c.confidence * 100)}%\n"
        f"Root cause: {c.root_cause}\n"
        f"Suggested fix:\n{fix}"
    )


def _fix_skipped_comment(c: Classification) -> str:
    return (
        "ci-doctor diagnosis:\n\n"
        f"Category: {c.category}\n"
        f"Confidence: {int(c.confidence * 100)}%\n"
        f"Root cause: {c.root_cause}\n"
        "Action: fix generation skipped — cost ceiling exceeded or API key missing. Manual triage recommended."
    )


def _escalation_comment(c: Classification, run_id: int) -> str:
    return (
        "ci-doctor diagnosis:\n\n"
        f"Category: {c.category}\n"
        f"Confidence: {int(c.confidence * 100)}%\n"
        f"Root cause: {c.root_cause}\n"
        f"Action: escalating — @author please confirm or correct"
    )
