#!/usr/bin/env python3
"""Post advisory Gemini reviews with inline comments on open pull requests.

Run by .github/workflows/gemini-review.yml on a schedule or manual
dispatch, never on an event a pull request can influence: repository rule
#119 forbids repository secrets in PR-triggered workflows, so this script
polls open pull requests from a default-branch context instead of running
on the pull request event itself.

Each open, non-draft pull request is reviewed once per head commit; a
later push is reviewed again. The review event is always COMMENT:
advisory only, never REQUEST_CHANGES, and this job is not a required
check. Every expected failure (no API key, quota exhausted, Gemini or
GitHub API error) is written to the job step summary and the process
exits 0, so this job can never block anything.

The diff is untrusted input, so everything the model says is sanitized
before it is posted or logged: mentions, links and runner workflow
commands are neutralized, lengths are capped, and merge endorsements
are removed. The bot never speaks for the maintainer.

Only pull request diffs of a public repository are sent to the Gemini
API; the workflow refuses to run on private repositories.

Environment:
    GEMINI_API_KEY         AI Studio key (repository secret)
    GEMINI_MODEL           model id (default: gemini-2.5-flash)
    GH_TOKEN               GITHUB_TOKEN with pull-requests: write
    GITHUB_REPOSITORY      owner/repo
    GITHUB_API_URL         API base (default: https://api.github.com)
    GITHUB_STEP_SUMMARY    step summary file
    PR_NUMBER              review only this pull request (manual dispatch)
    GEMINI_MAX_DIFF_CHARS  total diff budget (default: 120000)
    GEMINI_MAX_FILE_CHARS  per-file diff budget (default: 20000)
    GEMINI_MAX_COMMENTS    inline comment cap (default: 10)
    GEMINI_MAX_PRS_PER_RUN pull requests reviewed per run (default: 3)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_MODEL = "gemini-2.5-flash"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
REVIEW_MARKER = "**Gemini code review**"
BOT_LOGIN = "github-actions[bot]"
SUMMARY_MAX_CHARS = 600
COMMENT_MAX_CHARS = 1000

ENDORSEMENT = re.compile(
    r"\b(safe to merge|ready to merge|good to merge|lgtm|"
    r"looks good to me)\b",
    re.IGNORECASE,
)

SUMMARY_PATH = os.environ.get("GITHUB_STEP_SUMMARY", "")


class QuotaExceeded(Exception):
    """The Gemini quota rejected a request that was already retried."""


def sanitize_model_output(text: str, max_chars: int) -> str:
    """Make model output safe to post as the bot and to write to the log.

    A pull request diff can steer the model into pinging users,
    embedding links, emitting runner workflow commands (::warning::,
    ::error::) or endorsing a merge. Neutralize all of that here.
    """
    text = re.sub(r"!\[([^\]]*)\]\(([^)]*)\)", r"\1", text)  # images
    text = re.sub(r"\[([^\]]+)\]\(([^)]*)\)", r"\1 (\2)", text)  # links
    text = re.sub(r"(https?://)(?=\S)", "\u200b\\1", text)  # autolinks
    text = re.sub(r"@(?=[A-Za-z0-9])", "@\u200b", text)  # mentions
    text = text.replace("::", ":\u200b:")  # runner workflow commands
    text = ENDORSEMENT.sub("[no merge assessment: advisory review]", text)
    text = text.strip()
    if len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."
    return text


def note(text: str) -> None:
    """Record a line in the step summary and the job log."""
    print(text, flush=True)
    if SUMMARY_PATH:
        with open(SUMMARY_PATH, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")


def http_json(
    url: str, headers: dict[str, str], payload: dict | None = None, timeout: int = 60
) -> dict | str:
    """POST (with payload) or GET JSON; return the decoded response."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url, data=data, method="POST" if data is not None else "GET", headers=headers
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    if response.headers.get_content_type() == "application/json":
        return json.loads(body)
    return body


def github_headers(
    token: str, accept: str = "application/vnd.github+json"
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    }


def truncate_diff(diff: str, per_file: int, total: int) -> str:
    """Cap each file's diff and the whole diff; mark truncations."""
    chunks: list[str] = []
    current: list[str] = []
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            chunks.append("".join(current))
            current = []
        current.append(line)
    chunks.append("".join(current))
    capped: list[str] = []
    for chunk in chunks:
        if len(chunk) > per_file:
            chunk = chunk[:per_file] + "\n[... file diff truncated ...]\n"
        capped.append(chunk)
    result = "".join(capped)
    if len(result) > total:
        result = result[:total] + "\n[... pull request diff truncated ...]\n"
    return result


def added_lines(diff: str) -> dict[str, set[int]]:
    """Map each file path to the added (+) line numbers on the RIGHT side."""
    valid: dict[str, set[int]] = {}
    path: str | None = None
    new_line = 0
    hunk = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[len("+++ b/") :]
            valid.setdefault(path, set())
        elif line.startswith("+++ "):
            path = None  # /dev/null or unusual header
        elif path is not None:
            match = hunk.match(line)
            if match:
                new_line = int(match.group(1))
            elif line.startswith("+"):
                valid[path].add(new_line)
                new_line += 1
            elif line.startswith("-"):
                pass
            else:
                new_line += 1
    return valid


PROMPT = """You are reviewing a pull request diff as an advisory second reviewer.
Find only issues a human maintainer should see before merging: correctness
bugs, security problems, broken error handling, regressions, and contract
or compatibility breaks. Skip style, naming, formatting, and taste. If
nothing qualifies, return an empty findings list.

Respond with one JSON object, no prose outside it:
{
  "summary": "one or two sentences about the change as a whole",
  "findings": [
    {"path": "file/path.py", "line": 42, "severity": "high|medium|low",
     "comment": "what is wrong and why it matters"}
  ]
}
Rules: at most 10 findings; every line number must be a line added (+) by
this diff in that file; no finding without a concrete reason; no praise.

Pull request diff:
"""


def gemini_review(model: str, api_key: str, diff: str) -> dict:
    url = f"{GEMINI_BASE}/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": PROMPT + diff}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
        },
    }
    last_error: Exception | None = None
    quota = False
    for attempt in (1, 2):
        try:
            response = http_json(
                url,
                {"x-goog-api-key": api_key, "Content-Type": "application/json"},
                payload,
            )
            assert isinstance(response, dict)
            parts = response["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts).strip()
            if text.startswith("```"):
                text = re.sub(
                    r"^```(json)?\s*|\s*```$", "", text, flags=re.MULTILINE
                ).strip()
            return json.loads(text)
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code == 429 or error.code >= 500:
                quota = quota or error.code == 429
                note(
                    f"Gemini attempt {attempt} failed: HTTP {error.code}; "
                    "retrying once after 15s"
                )
                time.sleep(15)
                continue
            raise
        except (KeyError, IndexError, json.JSONDecodeError, AssertionError) as error:
            raise RuntimeError(f"unparseable Gemini response: {error}")
    if quota:
        raise QuotaExceeded(f"Gemini quota rejected the request: {last_error}")
    raise RuntimeError(f"Gemini API failed after retry: {last_error}")


def validate_findings(raw: object, valid: dict[str, set[int]], cap: int) -> list[dict]:
    """Keep only findings that anchor to an added line in the diff."""
    findings = []
    items = raw.get("findings", []) if isinstance(raw, dict) else []
    if not isinstance(items, list):
        return findings
    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        line = item.get("line")
        comment = sanitize_model_output(str(item.get("comment", "")), COMMENT_MAX_CHARS)
        severity = str(item.get("severity", "medium")).lower()
        if severity not in ("high", "medium", "low"):
            severity = "medium"
        if (
            isinstance(path, str)
            and isinstance(line, int)
            and comment
            and line in valid.get(path, set())
        ):
            findings.append(
                {"path": path, "line": line, "severity": severity, "comment": comment}
            )
        if len(findings) >= cap:
            break
    return findings


def already_reviewed(reviews: object, head_sha: str) -> bool:
    if not isinstance(reviews, list):
        return False
    for review in reviews:
        if (
            isinstance(review, dict)
            and review.get("commit_id") == head_sha
            and review.get("user", {}).get("login") == BOT_LOGIN
            and str(review.get("body", "")).startswith(REVIEW_MARKER)
        ):
            return True
    return False


def post_review(
    api: str,
    repo: str,
    number: int,
    head_sha: str,
    token: str,
    body: str,
    comments: list[dict],
) -> None:
    url = f"{api}/repos/{repo}/pulls/{number}/reviews"
    headers = github_headers(token)
    inline = [
        {
            "path": f["path"],
            "line": f["line"],
            "side": "RIGHT",
            "body": f"**[{f['severity']}]** {f['comment']}",
        }
        for f in comments
    ]
    payload = {
        "commit_id": head_sha,
        "event": "COMMENT",
        "body": body,
        "comments": inline,
    }
    try:
        http_json(url, headers, payload)
        return
    except urllib.error.HTTPError as error:
        if error.code != 422 or not inline:
            raise
    # A comment anchor was rejected: post the same review without inlines.
    listed = "\n".join(
        f"- `{f['path']}:{f['line']}` [{f['severity']}] {f['comment']}"
        for f in comments
    )
    fallback = {
        "commit_id": head_sha,
        "event": "COMMENT",
        "body": body + "\n\n" + listed,
        "comments": [],
    }
    http_json(url, headers, fallback)


def review_pr(
    api: str,
    repo: str,
    token: str,
    model: str,
    api_key: str,
    pr: dict,
    per_file: int,
    total: int,
    cap: int,
) -> str:
    """Review one pull request.

    Returns "posted", "skipped" (no Gemini call was made) or "failed"
    (a Gemini call was made but nothing was posted). Only non-skipped
    outcomes consume the per-run budget, so one failing pull request
    cannot make a run hammer the API.
    """
    number = pr["number"]
    head_sha = pr.get("head", {}).get("sha", "")
    if not head_sha:
        note(f"PR #{number}: no head sha; skipped.")
        return "skipped"
    reviews = http_json(
        f"{api}/repos/{repo}/pulls/{number}/reviews?per_page=100", github_headers(token)
    )
    if already_reviewed(reviews, head_sha):
        note(f"PR #{number}: head {head_sha[:8]} already reviewed; skipped.")
        return "skipped"
    diff = http_json(
        f"{api}/repos/{repo}/pulls/{number}",
        github_headers(token, "application/vnd.github.v3.diff"),
    )
    if not isinstance(diff, str) or not diff.strip():
        note(f"PR #{number}: empty diff; skipped.")
        return "skipped"
    diff = truncate_diff(diff, per_file, total)
    valid = added_lines(diff)
    try:
        raw = gemini_review(model, api_key, diff)
    except QuotaExceeded:
        raise
    except Exception as error:  # noqa: BLE001 - advisory: never fail
        note(f"PR #{number}: review unavailable: {error}")
        return "failed"
    summary = sanitize_model_output(
        str(raw.get("summary", "")) if isinstance(raw, dict) else "", SUMMARY_MAX_CHARS
    )
    findings = validate_findings(raw, valid, cap)
    log_summary = re.sub(r"\s+", " ", summary).strip() or "(none)"
    note(f"PR #{number}: {len(findings)} finding(s) kept; summary: {log_summary}")
    body = (
        f"{REVIEW_MARKER} (advisory, model `{model}`; not a required "
        f"check)\n\n{summary or 'See inline comments.'}"
    )
    try:
        post_review(api, repo, int(number), head_sha, token, body, findings)
    except Exception as error:  # noqa: BLE001 - advisory: never fail
        note(f"PR #{number}: could not post review: {error}")
        return "failed"
    note(f"PR #{number}: COMMENT review posted.")
    return "posted"


def main() -> int:
    note("## Gemini code review (advisory)")
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        note("No GEMINI_API_KEY secret configured; skipping.")
        return 0
    token = os.environ.get("GH_TOKEN", "").strip()
    if not token:
        note("No GH_TOKEN; skipping.")
        return 0
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        note("No GITHUB_REPOSITORY; skipping.")
        return 0
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    per_file = int(os.environ.get("GEMINI_MAX_FILE_CHARS", "20000"))
    total = int(os.environ.get("GEMINI_MAX_DIFF_CHARS", "120000"))
    cap = int(os.environ.get("GEMINI_MAX_COMMENTS", "10"))
    per_run = int(os.environ.get("GEMINI_MAX_PRS_PER_RUN", "3"))

    try:
        wanted = os.environ.get("PR_NUMBER", "").strip()
        if wanted:
            pr = http_json(f"{api}/repos/{repo}/pulls/{wanted}", github_headers(token))
            candidates = [pr] if isinstance(pr, dict) else []
        else:
            pulls = http_json(
                f"{api}/repos/{repo}/pulls?state=open&per_page=30",
                github_headers(token),
            )
            candidates = pulls if isinstance(pulls, list) else []
    except Exception as error:  # noqa: BLE001 - advisory: never fail
        note(f"Could not list pull requests ({error}); done.")
        return 0

    attempts = 0
    posted = 0
    for pr in candidates:
        if attempts >= per_run:
            note(
                f"Run budget reached ({per_run} review attempts); "
                "remaining pull requests will be picked up by the next "
                "run."
            )
            break
        if pr.get("draft"):
            note(f"PR #{pr.get('number')}: draft; skipped.")
            continue
        try:
            result = review_pr(
                api, repo, token, model, api_key, pr, per_file, total, cap
            )
        except QuotaExceeded as error:
            note(
                f"PR #{pr.get('number')}: {error}; ending this run, the "
                "next scheduled run will retry."
            )
            break
        except Exception as error:  # noqa: BLE001 - advisory: never fail
            note(f"PR #{pr.get('number')}: review unavailable: {error}")
            result = "failed"
        if result != "skipped":
            attempts += 1
        if result == "posted":
            posted += 1
    note(f"Done; {posted} review(s) posted, {attempts} attempt(s) used.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
