import asyncio
import io
import zipfile
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.classifier import classify
from app.config import load as load_config
from app.knowledge.base import KnowledgeBase
from app.knowledge.corrections import apply_correction, handle_correction
from app.resolver.actions import dispatch
from app.resolver.extract import extract_snippet
from app.resolver.github import GitHubClient
from app.webhook.receiver import router as webhook_router
from app.worker.queue import worker_loop

cfg = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global cfg
    cfg = load_config()
    app.state.cfg = cfg
    task = asyncio.create_task(worker_loop(_handle_event))
    yield
    task.cancel()


app = FastAPI(title="ci-doctor", lifespan=lifespan)
app.include_router(webhook_router)

from app.mcp_api import router as mcp_router
app.include_router(mcp_router)


async def _handle_event(event):
    if cfg is None:
        return

    event_type = event.event_type

    if event_type == "workflow_run":
        payload = event.payload
        workflow_run = payload.get("workflow_run", {})
        action = workflow_run.get("action", "")
        conclusion = workflow_run.get("conclusion", "")
        if action != "completed" or conclusion != "failure":
            return

        owner = payload.get("repository", {}).get("owner", {}).get("login", "")
        repo = payload.get("repository", {}).get("name", "")
        run_id = workflow_run.get("id")
        pr_number = 0
        commit_sha = workflow_run.get("head_commit", {}).get("id", "")

        pulls = workflow_run.get("pull_requests", [])
        if pulls:
            pr_number = pulls[0].get("number", 0)

        if not owner or not repo or not run_id:
            return

        gh = GitHubClient(cfg)
        kb = KnowledgeBase(cfg.kb_path)

        try:
            zip_data = await gh.fetch_run_logs(owner, repo, run_id)
            if not zip_data:
                return
            log_text = _extract_logs(zip_data)
            if not log_text:
                return
            snippet = extract_snippet(log_text)
        except Exception:
            return
        finally:
            await gh.close()

        classification = await classify(snippet, kb, cfg.rules_path, cfg.mlx_endpoint)
        jobs = await gh.fetch_jobs(owner, repo, run_id)
        job_id = jobs[0].get("id") if jobs else None

        await dispatch(classification, snippet, owner, repo, run_id, pr_number, job_id, cfg, gh, kb)

    elif event_type == "reaction":
        payload = event.payload
        gh = GitHubClient(cfg)
        kb = KnowledgeBase(cfg.kb_path)
        try:
            await handle_correction(payload, kb, gh)
        finally:
            await gh.close()

    elif event_type == "issue_comment":
        payload = event.payload
        action = payload.get("action", "")
        if action != "created":
            return
        comment = payload.get("comment", {})
        comment_body = comment.get("body", "")
        repo_full = payload.get("repository", {}).get("full_name", "")
        owner, repo = repo_full.split("/") if "/" in repo_full else ("", "")
        issue = payload.get("issue", {})
        pr_number = issue.get("number")

        if not owner or not pr_number or not comment_body:
            return

        gh = GitHubClient(cfg)
        kb = KnowledgeBase(cfg.kb_path)
        try:
            await apply_correction(comment_body, kb, gh, owner, repo, pr_number)
        finally:
            await gh.close()


def _extract_logs(data: bytes) -> str | None:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        parts = []
        for name in sorted(z.namelist()):
            if name.endswith(".txt"):
                parts.append(z.read(name).decode("utf-8", errors="replace"))
        return "\n".join(parts) if parts else None
    except zipfile.BadZipFile:
        return None


@app.get("/health")
async def health():
    return {"status": "ok"}
