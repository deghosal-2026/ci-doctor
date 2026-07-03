import httpx

from app.config import Settings


class GitHubClient:
    def __init__(self, cfg: Settings):
        self._token = cfg.github_token
        self._client = httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {cfg.github_token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "ci-doctor",
            },
        )

    async def fetch_run_logs(self, owner: str, repo: str, run_id: int) -> bytes | None:
        r = await self._client.get(f"/repos/{owner}/{repo}/actions/runs/{run_id}/logs", follow_redirects=True)
        return r.content if r.is_success else None

    async def fetch_jobs(self, owner: str, repo: str, run_id: int) -> list[dict]:
        r = await self._client.get(f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs")
        return r.json().get("jobs", []) if r.is_success else []

    async def rerun_job(self, owner: str, repo: str, job_id: int) -> bool:
        r = await self._client.post(f"/repos/{owner}/{repo}/actions/jobs/{job_id}/rerun")
        return r.is_success

    async def post_comment(self, owner: str, repo: str, pr_number: int, body: str) -> bool:
        r = await self._client.post(
            f"/repos/{owner}/{repo}/issues/{pr_number}/comments",
            json={"body": body},
        )
        return r.is_success

    async def fetch_diff(self, owner: str, repo: str, pr_number: int) -> str:
        r = await self._client.get(
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
            headers={"Accept": "application/vnd.github.v3.diff"},
        )
        return r.text if r.is_success else ""

    async def fetch_run(self, owner: str, repo: str, run_id: int) -> dict:
        r = await self._client.get(f"/repos/{owner}/{repo}/actions/runs/{run_id}")
        return r.json() if r.is_success else {}

    async def close(self):
        await self._client.aclose()
