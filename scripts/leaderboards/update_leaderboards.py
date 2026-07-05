#!/usr/bin/env python3
"""Collect and render QEMU Camp 2026 stage leaderboards."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


API_ROOT = "https://api.github.com"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T[0-9:.]+Z\s+")
PUBLIC_RECORD_FIELDS = (
    "stage",
    "direction",
    "rank",
    "github_id",
    "score",
    "total_score",
    "run_time",
    "completion_time",
)
PUBLIC_METADATA_FIELDS = ("generated_at",)
PUBLIC_DIRECTION_FIELDS = ("stage", "stage_title", "key", "title", "page")


@dataclass(frozen=True)
class Direction:
    stage: str
    stage_title: str
    output_dir: str
    key: str
    title: str
    page: str
    repository_prefix: str
    workflow_names: tuple[str, ...]
    job_names: tuple[str, ...]
    course_secret: str


@dataclass
class LeaderboardRecord:
    stage: str
    direction: str
    rank: int | None
    github_id: str
    score: float
    total_score: float
    run_time: str
    completion_time: str
    run_url: str
    run_id: int
    job_name: str
    commit_sha: str
    repository: str
    repository_url: str
    source: str


@dataclass
class Diagnostic:
    repository: str
    repository_url: str
    direction: str
    reason: str
    run_url: str | None = None
    run_time: str | None = None
    kind: str = "missing"


class GitHubError(RuntimeError):
    def __init__(self, status: int | None, path: str, message: str):
        self.status = status
        self.path = path
        super().__init__(f"GitHub API error {status or 'unknown'} for {path}: {message}")


class StripAuthRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        original_host = urlparse(req.full_url).netloc
        redirected_host = urlparse(newurl).netloc
        if original_host != redirected_host:
            redirected.remove_header("Authorization")
            redirected.remove_header("Accept")
            redirected.remove_header("X-GitHub-Api-Version")
        return redirected


class GitHubClient:
    def __init__(self, token: str | None):
        self.token = token
        self.opener = build_opener(StripAuthRedirectHandler)

    def _request(self, path_or_url: str, params: dict[str, Any] | None = None) -> bytes:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            url = path_or_url
        else:
            url = f"{API_ROOT}{path_or_url}"
        if params:
            url = f"{url}?{urlencode(params)}"

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "qemu-camp-leaderboards",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            with self.opener.open(Request(url, headers=headers), timeout=60) as response:
                return response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                message = json.loads(detail).get("message", detail)
            except json.JSONDecodeError:
                message = detail
            raise GitHubError(exc.code, path_or_url, message) from exc
        except URLError as exc:
            raise GitHubError(None, path_or_url, str(exc)) from exc

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return json.loads(self._request(path, params).decode("utf-8"))

    def get_bytes(self, path_or_url: str, params: dict[str, Any] | None = None) -> bytes:
        return self._request(path_or_url, params)

    def paginate(self, path: str, params: dict[str, Any] | None = None, limit: int | None = None) -> list[Any]:
        collected: list[Any] = []
        page = 1
        while True:
            request_params = {"per_page": 100, "page": page}
            if params:
                request_params.update(params)
            data = self.get_json(path, request_params)
            if isinstance(data, dict):
                items = data.get("items") or data.get("workflow_runs") or data.get("jobs") or data.get("artifacts")
            else:
                items = data
            if not items:
                break
            collected.extend(items)
            if limit is not None and len(collected) >= limit:
                return collected[:limit]
            if len(items) < int(request_params["per_page"]):
                break
            page += 1
        return collected


def load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "stages" not in data:
        stage = {
            "key": "professional",
            "title": "专业阶段",
            "output_dir": data["professional_output_dir"],
            "repository_prefix": data["repository_prefix"],
            "workflow_names": data.get("workflow_names", []),
            "directions": data["directions"],
        }
        data["stages"] = [stage]

    normalized_stages: list[dict[str, Any]] = []
    directions: list[Direction] = []
    for stage in data["stages"]:
        stage_directions: list[Direction] = []
        stage_prefix = stage.get("repository_prefix", data.get("repository_prefix", ""))
        stage_workflows = stage.get("workflow_names", data.get("workflow_names", []))
        for item in stage["directions"]:
            direction = Direction(
                stage=stage["key"],
                stage_title=stage["title"],
                output_dir=stage["output_dir"],
                key=item["key"],
                title=item["title"],
                page=item["page"],
                repository_prefix=item.get("repository_prefix", stage_prefix),
                workflow_names=tuple(item.get("workflow_names", stage_workflows)),
                job_names=tuple(item["job_names"]),
                course_secret=item["course_secret"],
            )
            stage_directions.append(direction)
            directions.append(direction)
        normalized_stages.append({
            "key": stage["key"],
            "title": stage["title"],
            "output_dir": stage["output_dir"],
            "directions": stage_directions,
        })
    data["stages"] = normalized_stages
    data["directions"] = directions
    return data


def parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.max.replace(tzinfo=timezone.utc)
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.max.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_time(value: str | None) -> str:
    if not value:
        return "-"
    parsed = parse_time(value)
    if parsed == datetime.max.replace(tzinfo=timezone.utc):
        return value
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def score_sort_key(record: LeaderboardRecord) -> tuple[float, datetime, str]:
    return (-float(record.score), parse_time(record.run_time), record.github_id.lower())


def rank_records(records: list[LeaderboardRecord]) -> list[LeaderboardRecord]:
    ranked = sorted(records, key=score_sort_key)
    for index, record in enumerate(ranked, start=1):
        record.rank = index
    return ranked


def clean_log(log_text: str) -> str:
    text = ANSI_RE.sub("", log_text)
    lines = [TIMESTAMP_RE.sub("", line.rstrip()) for line in text.splitlines()]
    return "\n".join(lines)


def _balanced_json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    starts = [match.start() for match in re.finditer(r"\{", text)]
    for start in starts:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : index + 1])
                    break
    return candidates


def normalize_masked_json(text: str) -> str:
    return re.sub(r":\s*\*\*\*(\s*[,}])", r": null\1", text)


def is_score_payload(payload: dict[str, Any]) -> bool:
    return (
        payload.get("channel") == "github"
        and isinstance(payload.get("name"), str)
        and isinstance(payload.get("score"), (int, float))
        and isinstance(payload.get("totalScore"), (int, float))
    )


def is_valid_score_payload(payload: dict[str, Any], expected_name: str | None = None) -> bool:
    if not is_score_payload(payload):
        return False
    if expected_name and payload["name"].lower() != expected_name.lower():
        return False
    score = float(payload["score"])
    total_score = float(payload["totalScore"])
    return 0 <= score <= total_score and total_score > 0


def _opencamp_upload_sections(text: str) -> list[str]:
    sections: list[str] = []
    lines = text.splitlines()
    marker_sets = (
        (
            'cat "$SUMMARY"',
            (
                "jq -n",
                "curl --fail-with-body",
                '-d @"$SUMMARY"',
                "OPENCAMP_COURSE_ID",
                "GITHUB_USER:",
                "SUMMARY:",
                "api.opencamp.cn",
                "/web/api/courseRank/createByThirdToken",
            ),
        ),
        (
            'echo "$summary"',
            (
                "summary=$(jq -n",
                "curl -X POST",
                '-d "$summary"',
                "--argjson score",
                "--argjson totalScore",
                "api.opencamp.cn",
                "/web/api/courseRank/createByThirdToken",
            ),
        ),
    )
    for index, line in enumerate(lines):
        required_markers: tuple[str, ...] | None = None
        for anchor, markers in marker_sets:
            if anchor in line:
                required_markers = markers
                break
        if required_markers is None:
            continue
        window_start = max(0, index - 30)
        window_end = min(len(lines), index + 80)
        window = "\n".join(lines[window_start:window_end])
        if all(marker in window for marker in required_markers):
            sections.append(window)
    return sections


def extract_payload_from_log(log_text: str, expected_name: str | None = None) -> dict[str, Any] | None:
    text = clean_log(log_text)
    for section in _opencamp_upload_sections(text):
        for candidate in _balanced_json_candidates(section):
            normalized = normalize_masked_json(candidate)
            try:
                payload = json.loads(normalized)
            except json.JSONDecodeError:
                continue
            if is_valid_score_payload(payload, expected_name):
                return payload

    return None


def extract_unverified_payload_from_log(log_text: str) -> dict[str, Any] | None:
    text = clean_log(log_text)
    for candidate in _balanced_json_candidates(text):
        normalized = normalize_masked_json(candidate)
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            continue
        if is_score_payload(payload):
            return payload

    name_match = re.search(r'"name"\s*:\s*"([^"]+)"', text)
    score_match = re.search(r'"score"\s*:\s*([0-9]+(?:\.[0-9]+)?)', text)
    total_match = re.search(r'"totalScore"\s*:\s*([0-9]+(?:\.[0-9]+)?)', text)
    if name_match and score_match and total_match and '"channel": "github"' in text:
        return {
            "channel": "github",
            "courseId": None,
            "ext": "{}",
            "name": name_match.group(1),
            "score": float(score_match.group(1)),
            "totalScore": float(total_match.group(1)),
        }
    return None


def expected_github_id(repo_name: str, direction: Direction) -> str:
    return repo_name.removeprefix(direction.repository_prefix)


def diagnostic_is_collection_error(diagnostic: Diagnostic) -> bool:
    return diagnostic.kind == "error"


def list_completed_workflow_runs(
    client: GitHubClient,
    organization: str,
    repo_name: str,
    workflow_names: set[str],
    limit: int,
    branch: str,
    event: str = "push",
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    page = 1
    while True:
        params = {
            "status": "completed",
            "branch": branch,
            "event": event,
            "per_page": 100,
            "page": page,
        }
        data = client.get_json(
            f"/repos/{organization}/{repo_name}/actions/runs",
            params,
        )
        runs = data.get("workflow_runs", []) if isinstance(data, dict) else data
        if not runs:
            break
        for run in runs:
            if workflow_names and run.get("name") not in workflow_names:
                continue
            if branch and run.get("head_branch") != branch:
                continue
            if event and run.get("event") != event:
                continue
            matched.append(run)
            if len(matched) >= limit:
                return matched
        if len(runs) < 100:
            break
        page += 1
    return matched


def discover_repositories(
    client: GitHubClient,
    organization: str,
    prefix: str,
    limit: int | None,
    repository_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    if repository_names:
        repos = []
        for name in repository_names:
            repo_name = name.split("/", 1)[-1]
            if not repo_name.startswith(prefix):
                continue
            repos.append(client.get_json(f"/repos/{organization}/{repo_name}"))
        return repos

    repos = client.paginate(f"/orgs/{organization}/repos", {"type": "public", "sort": "full_name"})
    matched = [
        repo
        for repo in repos
        if repo.get("name", "").startswith(prefix) and not repo.get("archived") and repo.get("visibility") == "public"
    ]
    matched.sort(key=lambda repo: repo["name"].lower())
    if limit is not None:
        return matched[:limit]
    return matched


def find_job_for_direction(jobs: list[dict[str, Any]], direction: Direction) -> dict[str, Any] | None:
    names = {name.lower() for name in direction.job_names}
    for job in jobs:
        if job.get("name", "").lower() in names:
            return job
    for job in jobs:
        job_name = job.get("name", "").lower()
        if any(name in job_name for name in names):
            return job
    return None


def record_from_payload(
    *,
    payload: dict[str, Any],
    direction: Direction,
    repo: dict[str, Any],
    run: dict[str, Any],
    job: dict[str, Any] | None,
    source: str,
) -> LeaderboardRecord:
    run_time = run.get("run_started_at") or run.get("created_at") or run.get("updated_at") or ""
    completion_time = (
        (job or {}).get("completed_at")
        or run.get("updated_at")
        or run.get("created_at")
        or run_time
        or ""
    )
    return LeaderboardRecord(
        stage=direction.stage,
        direction=direction.key,
        rank=None,
        github_id=str(payload.get("name") or repo["name"].removeprefix(direction.repository_prefix)),
        score=float(payload["score"]),
        total_score=float(payload["totalScore"]),
        run_time=run_time,
        completion_time=completion_time,
        run_url=run.get("html_url", ""),
        run_id=int(run.get("id", 0)),
        job_name=(job or {}).get("name", ""),
        commit_sha=run.get("head_sha", ""),
        repository=repo["name"],
        repository_url=repo.get("html_url", ""),
        source=source,
    )


def direction_matches_run(direction: Direction, run: dict[str, Any]) -> bool:
    return not direction.workflow_names or run.get("name") in direction.workflow_names


def collect_repository(
    client: GitHubClient,
    config: dict[str, Any],
    repo: dict[str, Any],
    directions: list[Direction],
    max_runs: int,
) -> tuple[list[LeaderboardRecord], list[Diagnostic]]:
    organization = config["organization"]
    repo_name = repo["name"]
    records: dict[str, LeaderboardRecord] = {}
    latest_seen: dict[str, Diagnostic] = {}
    blocked: set[str] = set()

    workflow_names = {name for direction in directions for name in direction.workflow_names}
    upload_branch = repo.get("default_branch") or "main"
    try:
        runs = list_completed_workflow_runs(client, organization, repo_name, workflow_names, max_runs, upload_branch)
    except GitHubError as exc:
        diagnostics = [
            Diagnostic(repo_name, repo.get("html_url", ""), direction.key, str(exc), kind="error")
            for direction in directions
        ]
        return [], diagnostics

    if not runs:
        return [], [
            Diagnostic(repo_name, repo.get("html_url", ""), direction.key, "no completed workflow run found")
            for direction in directions
        ]

    for run in runs:
        if all(direction.key in records or direction.key in blocked for direction in directions):
            break
        missing = [
            direction
            for direction in directions
            if direction.key not in records and direction.key not in blocked and direction_matches_run(direction, run)
        ]
        if not missing:
            continue

        try:
            jobs = client.paginate(f"/repos/{organization}/{repo_name}/actions/runs/{run['id']}/jobs")
        except GitHubError as exc:
            for direction in missing:
                latest_seen.setdefault(
                    direction.key,
                    Diagnostic(
                        repo_name,
                        repo.get("html_url", ""),
                        direction.key,
                        str(exc),
                        run_url=run.get("html_url"),
                        run_time=run.get("run_started_at") or run.get("created_at"),
                        kind="error",
                    ),
                )
                blocked.add(direction.key)
            continue

        for direction in missing:
            job = find_job_for_direction(jobs, direction)
            expected_name = expected_github_id(repo_name, direction)
            if not job:
                latest_seen.setdefault(
                    direction.key,
                    Diagnostic(
                        repo_name,
                        repo.get("html_url", ""),
                        direction.key,
                        "matching job not found in recent run",
                        run_url=run.get("html_url"),
                        run_time=run.get("run_started_at") or run.get("created_at"),
                    ),
                )
                continue

            try:
                log_bytes = client.get_bytes(f"/repos/{organization}/{repo_name}/actions/jobs/{job['id']}/logs")
            except GitHubError as exc:
                latest_seen.setdefault(
                    direction.key,
                    Diagnostic(
                        repo_name,
                        repo.get("html_url", ""),
                        direction.key,
                        str(exc),
                        run_url=run.get("html_url"),
                        run_time=run.get("run_started_at") or run.get("created_at"),
                        kind="error",
                    ),
                )
                blocked.add(direction.key)
                continue

            payload = extract_payload_from_log(
                log_bytes.decode("utf-8", errors="replace"),
                expected_name=expected_name,
            )
            if payload:
                records[direction.key] = record_from_payload(
                    payload=payload,
                    direction=direction,
                    repo=repo,
                    run=run,
                    job=job,
                    source="log",
                )
            else:
                latest_seen.setdefault(
                    direction.key,
                    Diagnostic(
                        repo_name,
                        repo.get("html_url", ""),
                        direction.key,
                        "no verified OpenCamp score payload in matching job log",
                        run_url=run.get("html_url"),
                        run_time=run.get("run_started_at") or run.get("created_at"),
                    ),
                )

    diagnostics = [
        latest_seen.get(
            direction.key,
            Diagnostic(repo_name, repo.get("html_url", ""), direction.key, "no parseable payload in inspected runs"),
        )
        for direction in directions
        if direction.key not in records
    ]
    return list(records.values()), diagnostics


def collect(
    config: dict[str, Any],
    repo_limit: int | None,
    max_runs: int | None,
    repository_names: list[str] | None = None,
    workers: int | None = None,
) -> tuple[list[LeaderboardRecord], list[Diagnostic]]:
    token = os.environ.get("LEADERBOARD_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    client = GitHubClient(token)
    directions: list[Direction] = config["directions"]
    groups: dict[str, list[Direction]] = {}
    for direction in directions:
        groups.setdefault(direction.repository_prefix, []).append(direction)

    work_items: list[tuple[dict[str, Any], list[Direction]]] = []
    for prefix, group_directions in groups.items():
        repos = discover_repositories(
            client,
            config["organization"],
            prefix,
            repo_limit,
            repository_names=repository_names,
        )
        work_items.extend((repo, group_directions) for repo in repos)

    records: list[LeaderboardRecord] = []
    diagnostics: list[Diagnostic] = []
    run_limit = max_runs or int(config.get("max_runs_per_repo", 6))
    worker_count = max(1, int(workers or config.get("workers", 1)))

    if worker_count == 1 or len(work_items) <= 1:
        for index, (repo, group_directions) in enumerate(work_items, start=1):
            print(f"[{index}/{len(work_items)}] collecting {repo['name']}", file=sys.stderr)
            repo_records, repo_diagnostics = collect_repository(client, config, repo, group_directions, run_limit)
            records.extend(repo_records)
            diagnostics.extend(repo_diagnostics)
        return records, diagnostics

    def collect_one(
        index: int,
        repo: dict[str, Any],
        group_directions: list[Direction],
    ) -> tuple[int, list[LeaderboardRecord], list[Diagnostic]]:
        thread_client = GitHubClient(token)
        repo_records, repo_diagnostics = collect_repository(thread_client, config, repo, group_directions, run_limit)
        return index, repo_records, repo_diagnostics

    by_index: dict[int, tuple[list[LeaderboardRecord], list[Diagnostic]]] = {}
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_repo = {
            executor.submit(collect_one, index, repo, group_directions): (index, repo, group_directions)
            for index, (repo, group_directions) in enumerate(work_items, start=1)
        }
        for completed, future in enumerate(as_completed(future_to_repo), start=1):
            index, repo, group_directions = future_to_repo[future]
            try:
                _, repo_records, repo_diagnostics = future.result()
            except Exception as exc:  # pragma: no cover - defensive diagnostics for collection runtime failures.
                repo_records = []
                repo_diagnostics = [
                    Diagnostic(repo["name"], repo.get("html_url", ""), direction.key, str(exc), kind="error")
                    for direction in group_directions
                ]
            by_index[index] = (repo_records, repo_diagnostics)
            print(f"[{completed}/{len(work_items)}] collected {repo['name']}", file=sys.stderr)

    for index in sorted(by_index):
        repo_records, repo_diagnostics = by_index[index]
        records.extend(repo_records)
        diagnostics.extend(repo_diagnostics)
    return records, diagnostics


def build_snapshot(config: dict[str, Any], records: list[LeaderboardRecord], diagnostics: list[Diagnostic]) -> dict[str, Any]:
    directions: list[Direction] = config["directions"]
    ranked: list[LeaderboardRecord] = []
    for direction in directions:
        direction_records = [
            record
            for record in records
            if record.stage == direction.stage and record.direction == direction.key
        ]
        ranked.extend(rank_records(direction_records))

    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "source_organization": config["organization"],
        },
        "directions": [public_direction(asdict(direction)) for direction in directions],
        "ranked": [public_record(asdict(record)) for record in ranked],
        "diagnostics": [asdict(diagnostic) for diagnostic in diagnostics],
    }


def refresh_snapshot_time(snapshot: dict[str, Any]) -> dict[str, Any]:
    snapshot = dict(snapshot)
    metadata = dict(snapshot.get("metadata", {}))
    metadata["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot["metadata"] = metadata
    return snapshot


def markdown_escape(value: Any) -> str:
    text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {field: record[field] for field in PUBLIC_RECORD_FIELDS if field in record}


def public_direction(direction: dict[str, Any]) -> dict[str, Any]:
    return {field: direction[field] for field in PUBLIC_DIRECTION_FIELDS if field in direction}


def public_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    cleaned = {
        "metadata": {
            field: snapshot.get("metadata", {})[field]
            for field in PUBLIC_METADATA_FIELDS
            if field in snapshot.get("metadata", {})
        },
        "directions": [public_direction(direction) for direction in snapshot.get("directions", [])],
    }
    cleaned["ranked"] = [public_record(record) for record in snapshot.get("ranked", [])]
    cleaned["diagnostics"] = []
    return cleaned


def direction_from_snapshot(item: dict[str, Any]) -> Direction:
    return Direction(
        stage=item["stage"],
        stage_title=item["stage_title"],
        output_dir="",
        key=item["key"],
        title=item["title"],
        page=item["page"],
        repository_prefix="",
        workflow_names=(),
        job_names=tuple(item.get("job_names", ())),
        course_secret=item.get("course_secret", ""),
    )


def render_direction_links(directions: list[Direction], active_key: str) -> str:
    links: list[str] = []
    for direction in directions:
        label = f"**{direction.title}**" if direction.key == active_key else direction.title
        links.append(f"[{label}]({direction.page})")
    return " | ".join(links)


def render_direction_page(
    snapshot: dict[str, Any],
    direction: Direction,
    directions: list[Direction],
    output_dir: Path,
) -> str:
    metadata = snapshot["metadata"]
    rows = [
        item
        for item in snapshot["ranked"]
        if item["stage"] == direction.stage and item["direction"] == direction.key
    ]
    title_suffix = " 排行榜" if re.search(r"[A-Za-z0-9]$", direction.title) else "排行榜"

    lines: list[str] = [
        f"# QEMU 训练营 2026 {direction.stage_title} {direction.title}{title_suffix}",
        "",
        render_direction_links(directions, direction.key),
        "",
    ]

    if rows:
        lines.extend([
            "| 排名 | GitHub ID | 得分 | 总分 | 评分 run 时间 |",
            "| --- | --- | ---: | ---: | --- |",
        ])
        for row in rows:
            github_id = markdown_escape(row["github_id"])
            lines.append(
                "| {rank} | {github_id} | {score:g} | {total:g} | {time} |".format(
                    rank=row["rank"],
                    github_id=github_id,
                    score=float(row["score"]),
                    total=float(row["total_score"]),
                    time=format_time(row.get("run_time") or row.get("completion_time")),
                )
            )
    else:
        lines.append("当前快照没有可展示的排名结果。")

    lines.extend([
        "",
        f"每天刷新一次｜快照生成时间：{format_time(metadata.get('generated_at'))}",
    ])

    lines.append("")
    text = "\n".join(lines)
    (output_dir / direction.page).write_text(text, encoding="utf-8")
    return text


def render(snapshot: dict[str, Any], config: dict[str, Any], root: Path) -> None:
    snapshot = refresh_snapshot_time(snapshot)
    snapshot = public_snapshot(snapshot)
    snapshot["max_diagnostics_per_page"] = config.get("max_diagnostics_per_page", 40)
    snapshot_path = root / config["snapshot_path"]
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps({k: v for k, v in snapshot.items() if k != "max_diagnostics_per_page"}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    for stage in config["stages"]:
        output_dir = root / stage["output_dir"]
        output_dir.mkdir(parents=True, exist_ok=True)
        for direction in stage["directions"]:
            render_direction_page(snapshot, direction, stage["directions"], output_dir)


def load_snapshot(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_snapshot_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return load_snapshot(path)


def record_identity(stage: str, direction: str, github_id: str) -> tuple[str, str, str]:
    return stage, direction, github_id.lower()


def snapshot_record(item: dict[str, Any]) -> LeaderboardRecord:
    return LeaderboardRecord(
        stage=str(item["stage"]),
        direction=str(item["direction"]),
        rank=None,
        github_id=str(item["github_id"]),
        score=float(item["score"]),
        total_score=float(item["total_score"]),
        run_time=str(item.get("run_time") or ""),
        completion_time=str(item.get("completion_time") or item.get("run_time") or ""),
        run_url="",
        run_id=0,
        job_name="",
        commit_sha="",
        repository="",
        repository_url="",
        source="snapshot",
    )


def diagnostic_identity(
    diagnostic: Diagnostic,
    directions_by_key: dict[str, Direction],
) -> tuple[str, str, str] | None:
    direction = directions_by_key.get(diagnostic.direction)
    if direction is None:
        return None
    github_id = diagnostic.repository.removeprefix(direction.repository_prefix)
    if github_id == diagnostic.repository:
        return None
    return record_identity(direction.stage, direction.key, github_id)


def diagnostic_allows_snapshot_preservation(diagnostic: Diagnostic) -> bool:
    reason = diagnostic.reason.lower()
    if diagnostic.kind != "error":
        return False
    if "expired" in reason or "gone" in reason:
        return True
    return "/logs" in reason and ("404" in reason or "410" in reason or "not found" in reason)


def preserve_snapshot_records(
    config: dict[str, Any],
    records: list[LeaderboardRecord],
    diagnostics: list[Diagnostic],
    previous_snapshot: dict[str, Any] | None,
) -> tuple[list[LeaderboardRecord], list[Diagnostic], int]:
    if not previous_snapshot:
        return records, diagnostics, 0

    directions_by_key = {direction.key: direction for direction in config["directions"]}
    current_keys = {
        record_identity(record.stage, record.direction, record.github_id)
        for record in records
    }
    diagnostic_keys = {
        key
        for diagnostic in diagnostics
        if diagnostic_allows_snapshot_preservation(diagnostic)
        and (key := diagnostic_identity(diagnostic, directions_by_key)) is not None
    }

    preserved: list[LeaderboardRecord] = []
    preserved_keys: set[tuple[str, str, str]] = set()
    for item in previous_snapshot.get("ranked", []):
        try:
            key = record_identity(str(item["stage"]), str(item["direction"]), str(item["github_id"]))
        except KeyError:
            continue
        if key in current_keys or key not in diagnostic_keys:
            continue
        preserved.append(snapshot_record(item))
        preserved_keys.add(key)

    if not preserved:
        return records, diagnostics, 0

    remaining_diagnostics = [
        diagnostic
        for diagnostic in diagnostics
        if diagnostic_identity(diagnostic, directions_by_key) not in preserved_keys
    ]
    return [*records, *preserved], remaining_diagnostics, len(preserved)


def self_test() -> None:
    untrusted_log = """
2026-06-15T15:18:44.1483905Z {
2026-06-15T15:18:44.1484234Z   "channel": "github",
2026-06-15T15:18:44.1484662Z   "courseId": ***,
2026-06-15T15:18:44.1484978Z   "ext": "{}",
2026-06-15T15:18:44.1485294Z   "name": "alice",
2026-06-15T15:18:44.1485695Z   "score": 100,
2026-06-15T15:18:44.1485996Z   "totalScore": 100
2026-06-15T15:18:44.1486296Z }
"""
    assert extract_payload_from_log(untrusted_log, expected_name="alice") is None
    assert extract_unverified_payload_from_log(untrusted_log) is not None

    log = """
2026-06-15T15:18:44.1483905Z ##[group]Run jq -n
2026-06-15T15:18:44.1483905Z jq -n \\
2026-06-15T15:18:44.1483905Z   --arg channel "github" \\
2026-06-15T15:18:44.1483905Z   --arg courseId "$OPENCAMP_COURSE_ID" \\
2026-06-15T15:18:44.1483905Z   --arg ext "{}" \\
2026-06-15T15:18:44.1483905Z   --arg name "$GITHUB_USER" \\
2026-06-15T15:18:44.1483905Z   --argjson score "$TOTAL_SCORE" \\
2026-06-15T15:18:44.1483905Z   --argjson totalScore "$MAX_SCORE" \\
2026-06-15T15:18:44.1483905Z   '{channel: $channel, courseId: $courseId, ext: $ext, name: $name, score: $score, totalScore: $totalScore}' > "$SUMMARY"
2026-06-15T15:18:44.1483905Z cat "$SUMMARY"
2026-06-15T15:18:44.1483905Z curl --fail-with-body -X POST "$OPENCAMP_API_URL" \\
2026-06-15T15:18:44.1483905Z   -d @"$SUMMARY" \\
2026-06-15T15:18:44.1483905Z   -v
2026-06-15T15:18:44.1483905Z env:
2026-06-15T15:18:44.1483905Z   OPENCAMP_COURSE_ID: ***
2026-06-15T15:18:44.1483905Z   GITHUB_USER: alice
2026-06-15T15:18:44.1483905Z   TOTAL_SCORE: 100
2026-06-15T15:18:44.1483905Z   MAX_SCORE: 100
2026-06-15T15:18:44.1483905Z   SUMMARY: build/summary.json
2026-06-15T15:18:44.1483905Z ##[endgroup]
2026-06-15T15:18:44.1483905Z {
2026-06-15T15:18:44.1484234Z   "channel": "github",
2026-06-15T15:18:44.1484662Z   "courseId": ***,
2026-06-15T15:18:44.1484978Z   "ext": "{}",
2026-06-15T15:18:44.1485294Z   "name": "alice",
2026-06-15T15:18:44.1485695Z   "score": 100,
2026-06-15T15:18:44.1485996Z   "totalScore": 100
2026-06-15T15:18:44.1486296Z }
2026-06-15T15:18:44.1486296Z * Connected to api.opencamp.cn
2026-06-15T15:18:44.1486296Z > POST /web/api/courseRank/createByThirdToken HTTP/2
"""
    payload = extract_payload_from_log(log, expected_name="alice")
    assert payload is not None
    assert payload["name"] == "alice"
    assert payload["score"] == 100
    assert extract_payload_from_log(log, expected_name="bob") is None

    inline_summary_log = """
2026-06-15T15:18:44.1483905Z ##[group]Run summary=$(jq -n
2026-06-15T15:18:44.1483905Z summary=$(jq -n \\
2026-06-15T15:18:44.1483905Z   --arg channel "github" \\
2026-06-15T15:18:44.1483905Z   --arg courseId "***" \\
2026-06-15T15:18:44.1483905Z   --arg ext "{}" \\
2026-06-15T15:18:44.1483905Z   --arg name "alice" \\
2026-06-15T15:18:44.1483905Z   --argjson score "90" \\
2026-06-15T15:18:44.1483905Z   --argjson totalScore "100" \\
2026-06-15T15:18:44.1483905Z   '{channel: $channel, courseId: $courseId, ext: $ext, name: $name, score: $score, totalScore: $totalScore}')
2026-06-15T15:18:44.1483905Z echo "$summary"
2026-06-15T15:18:44.1483905Z curl -X POST "***" \\
2026-06-15T15:18:44.1483905Z   -d "$summary" \\
2026-06-15T15:18:44.1483905Z   -v
2026-06-15T15:18:44.1483905Z ##[endgroup]
2026-06-15T15:18:44.1483905Z {
2026-06-15T15:18:44.1484234Z   "channel": "github",
2026-06-15T15:18:44.1484662Z   "courseId": ***,
2026-06-15T15:18:44.1484978Z   "ext": "{}",
2026-06-15T15:18:44.1485294Z   "name": "alice",
2026-06-15T15:18:44.1485695Z   "score": 90,
2026-06-15T15:18:44.1485996Z   "totalScore": 100
2026-06-15T15:18:44.1486296Z }
2026-06-15T15:18:44.1486296Z * Connected to api.opencamp.cn
2026-06-15T15:18:44.1486296Z > POST /web/api/courseRank/createByThirdToken HTTP/2
"""
    inline_payload = extract_payload_from_log(inline_summary_log, expected_name="alice")
    assert inline_payload is not None
    assert inline_payload["score"] == 90

    repo = {"name": "qemu-camp-2026-exper-alice", "html_url": "https://github.com/gevico/repo"}
    direction = Direction(
        "professional",
        "专业阶段",
        "pages",
        "cpu",
        "CPU 方向",
        "cpu.md",
        "qemu-camp-2026-exper-",
        ("QEMU Camp 2026 CI",),
        ("CPU Experiment (TCG)",),
        "SECRET",
    )
    later = record_from_payload(
        payload=payload,
        direction=direction,
        repo=repo,
        run={"id": 2, "run_started_at": "2026-06-15T02:00:00Z", "html_url": "https://example.com/2"},
        job={"name": "CPU Experiment (TCG)", "completed_at": "2026-06-15T02:10:00Z"},
        source="log",
    )
    earlier = record_from_payload(
        payload={**payload, "name": "bob"},
        direction=direction,
        repo={**repo, "name": "qemu-camp-2026-exper-bob"},
        run={"id": 1, "run_started_at": "2026-06-15T01:00:00Z", "html_url": "https://example.com/1"},
        job={"name": "CPU Experiment (TCG)", "completed_at": "2026-06-15T01:10:00Z"},
        source="log",
    )
    ranked = rank_records([later, earlier])
    assert [record.github_id for record in ranked] == ["bob", "alice"]
    assert [record.rank for record in ranked] == [1, 2]

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = {
            "snapshot_path": "snapshot.json",
            "max_diagnostics_per_page": 10,
            "stages": [
                {
                    "key": "professional",
                    "title": "专业阶段",
                    "output_dir": "pages",
                    "directions": [direction],
                }
            ],
            "directions": [direction],
        }
        diagnostic = Diagnostic(
            "qemu-camp-2026-exper-charlie",
            "https://github.com/gevico/repo-charlie",
            "cpu",
            "GitHub API timeout",
            kind="error",
        )
        snapshot = build_snapshot(
            {"organization": "gevico", "directions": [direction]},
            [later, earlier],
            [diagnostic],
        )
        assert snapshot["diagnostics"][0]["kind"] == "error"
        render(snapshot, config, root)
        public = json.loads((root / "snapshot.json").read_text(encoding="utf-8"))
        assert public["diagnostics"] == []
        page = (root / "pages" / "cpu.md").read_text(encoding="utf-8")
        assert "qemu-camp-2026-exper" not in page.split("| GitHub ID |", 1)[-1].split("完整快照", 1)[0]
        assert "bob" in page and "alice" in page
        assert "每天刷新一次｜快照生成时间：" in page

        current_records, remaining_diagnostics, preserved = preserve_snapshot_records(
            config,
            [later],
            [
                Diagnostic(
                    "qemu-camp-2026-exper-bob",
                    "https://github.com/gevico/repo-bob",
                    "cpu",
                    "GitHub log expired",
                    kind="error",
                )
            ],
            public,
        )
        assert preserved == 1
        assert remaining_diagnostics == []
        assert {record.github_id for record in current_records} == {"alice", "bob"}

        current_records, remaining_diagnostics, preserved = preserve_snapshot_records(
            config,
            [later],
            [
                Diagnostic(
                    "qemu-camp-2026-exper-bob",
                    "https://github.com/gevico/repo-bob",
                    "cpu",
                    "GitHub API error 502 for /repos/gevico/repo/actions/jobs/1/logs: Bad Gateway",
                    kind="error",
                )
            ],
            public,
        )
        assert preserved == 0
        assert len(remaining_diagnostics) == 1
        assert {record.github_id for record in current_records} == {"alice"}

    class FakeGitHubClient:
        def __init__(self, runs: list[dict[str, Any]], jobs: dict[int, list[dict[str, Any]]], logs: dict[int, bytes | GitHubError]):
            self.runs = runs
            self.jobs = jobs
            self.logs = logs

        def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
            if path.endswith("/actions/runs"):
                return {"workflow_runs": self.runs}
            raise AssertionError(f"unexpected get_json path: {path}")

        def paginate(self, path: str, params: dict[str, Any] | None = None, limit: int | None = None) -> list[Any]:
            match = re.search(r"/actions/runs/(\d+)/jobs$", path)
            if not match:
                raise AssertionError(f"unexpected paginate path: {path}")
            return self.jobs[int(match.group(1))]

        def get_bytes(self, path_or_url: str, params: dict[str, Any] | None = None) -> bytes:
            match = re.search(r"/actions/jobs/(\d+)/logs$", path_or_url)
            if not match:
                raise AssertionError(f"unexpected get_bytes path: {path_or_url}")
            result = self.logs[int(match.group(1))]
            if isinstance(result, GitHubError):
                raise result
            return result

    filtered_runs = list_completed_workflow_runs(
        FakeGitHubClient(
            [
                {"id": 10, "name": "QEMU Camp 2026 CI", "event": "pull_request", "head_branch": "main"},
                {"id": 11, "name": "QEMU Camp 2026 CI", "event": "push", "head_branch": "feature"},
                {"id": 12, "name": "QEMU Camp 2026 CI", "event": "push", "head_branch": "main"},
            ],
            {},
            {},
        ),
        "gevico",
        "qemu-camp-2026-exper-alice",
        {"QEMU Camp 2026 CI"},
        6,
        "main",
    )
    assert [run["id"] for run in filtered_runs] == [12]

    stale_payload_log = log.replace('"score": 100', '"score": 10')
    records, diagnostics = collect_repository(
        FakeGitHubClient(
            [
                {
                    "id": 21,
                    "name": "QEMU Camp 2026 CI",
                    "event": "push",
                    "head_branch": "main",
                    "run_started_at": "2026-06-16T02:00:00Z",
                    "created_at": "2026-06-16T02:00:00Z",
                    "html_url": "https://example.com/21",
                },
                {
                    "id": 20,
                    "name": "QEMU Camp 2026 CI",
                    "event": "push",
                    "head_branch": "main",
                    "run_started_at": "2026-06-15T02:00:00Z",
                    "created_at": "2026-06-15T02:00:00Z",
                    "html_url": "https://example.com/20",
                },
            ],
            {
                21: [{"id": 210, "name": "CPU Experiment (TCG)", "completed_at": "2026-06-16T02:10:00Z"}],
                20: [{"id": 200, "name": "CPU Experiment (TCG)", "completed_at": "2026-06-15T02:10:00Z"}],
            },
            {
                210: GitHubError(502, "/jobs/210/logs", "Bad Gateway"),
                200: stale_payload_log.encode("utf-8"),
            },
        ),
        {"organization": "gevico"},
        repo,
        [direction],
        6,
    )
    assert records == []
    assert len(diagnostics) == 1
    assert diagnostics[0].kind == "error"
    assert "Bad Gateway" in diagnostics[0].reason


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="scripts/leaderboards/config.json", help="Path to leaderboard config JSON.")
    parser.add_argument("--repo-limit", type=int, default=None, help="Limit repositories for local sampling.")
    parser.add_argument(
        "--repository",
        action="append",
        default=None,
        help="Collect only the named repository. Can be passed multiple times.",
    )
    parser.add_argument("--max-runs", type=int, default=None, help="Override max workflow runs inspected per repository.")
    parser.add_argument("--workers", type=int, default=None, help="Override concurrent repository collection workers.")
    parser.add_argument("--output-root", default=".", help="Repository root for generated files.")
    parser.add_argument("--dry-run", action="store_true", help="Collect and render into a temporary directory.")
    parser.add_argument("--render-only", help="Render pages from an existing snapshot JSON instead of collecting.")
    parser.add_argument(
        "--fail-on-collection-errors",
        action="store_true",
        help="Exit non-zero when GitHub API or log download errors occurred during collection.",
    )
    parser.add_argument("--self-test", action="store_true", help="Run parser, ranking, and rendering self-tests.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        print("self-test passed")
        return 0

    config = load_config(Path(args.config))
    root = Path(args.output_root)
    preserved_count = 0
    if args.render_only:
        snapshot = load_snapshot(Path(args.render_only))
        diagnostics: list[Diagnostic] = []
    else:
        records, diagnostics = collect(config, args.repo_limit, args.max_runs, args.repository, args.workers)
        records, diagnostics, preserved_count = preserve_snapshot_records(
            config,
            records,
            diagnostics,
            load_snapshot_if_exists(root / config["snapshot_path"]),
        )
        collection_errors = [diagnostic for diagnostic in diagnostics if diagnostic_is_collection_error(diagnostic)]
        if args.fail_on_collection_errors and collection_errors:
            print(
                f"collection failed with {len(collection_errors)} GitHub API/log errors; refusing to render partial leaderboards",
                file=sys.stderr,
            )
            for diagnostic in collection_errors[:20]:
                print(
                    f"- {diagnostic.repository} {diagnostic.direction}: {diagnostic.reason}",
                    file=sys.stderr,
                )
            if len(collection_errors) > 20:
                print(f"- ... {len(collection_errors) - 20} more errors", file=sys.stderr)
            return 1
        snapshot = build_snapshot(config, records, diagnostics)
    collection_error_count = len([diagnostic for diagnostic in diagnostics if diagnostic_is_collection_error(diagnostic)])

    if args.dry_run:
        with tempfile.TemporaryDirectory() as tmp:
            render(snapshot, config, Path(tmp))
            print(f"dry-run rendered files under {tmp}")
            print(
                f"ranked={len(snapshot['ranked'])} diagnostics={len(diagnostics)} "
                f"collection_errors={collection_error_count} preserved={preserved_count} "
                f"generated_at={snapshot['metadata']['generated_at']}"
            )
    else:
        render(snapshot, config, root)
        print(
            f"rendered leaderboards: ranked={len(snapshot['ranked'])} diagnostics={len(diagnostics)} "
            f"collection_errors={collection_error_count} preserved={preserved_count}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
