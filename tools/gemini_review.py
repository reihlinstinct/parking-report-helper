#!/usr/bin/env python3
"""Post an advisory Gemini review with inline comments on a pull request.

Run by .github/workflows/gemini-review-reusable.yml on pull_request events.
The review event is always COMMENT: advisory only, never a merge gate and
never REQUEST_CHANGES. Every expected failure (no API key, quota exhausted,
Gemini or GitHub API error) is written to the job step summary and the
process exits 0, so this job can never block a merge.

Only the pull request diff of a public repository is sent to the Gemini
API; the reusable workflow refuses to run on private repositories.

Environment:
    GEMINI_API_KEY         AI Studio key (repository secret; absent on forks)
    GEMINI_MODEL           model id (default: gemini-2.5-flash)
    GH_TOKEN               GITHUB_TOKEN with pull-requests: write
    GITHUB_REPOSITORY      owner/repo
    GITHUB_API_URL         API base (default: https://api.github.com)
    GITHUB_EVENT_PATH      pull_request event payload
    GITHUB_STEP_SUMMARY    step summary file
    GEMINI_MAX_DIFF_CHARS  total diff budget (default: 120000)
    GEMINI_MAX_FILE_CHARS  per-file diff budget (default: 20000)
    GEMINI_MAX_COMMENTS    inline comment cap (default: 10)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

DEFAULT_MODEL = "gemini-2.5-flash"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

SUMMARY_PATH = os.environ.get("GITHUB_STEP_SUMMARY", "")


def note(text: str) -> None:
    """Record a line in the step summary and the job log."""
    print(text, flush=True)
    if SUMMARY_PATH:
        with open(SUMMARY_PATH, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")


def http_json(url: str, headers: dict[str, str], payload: dict,
              timeout: int = 60) -> dict:
    """POST JSON and return the decoded response, raising on HTTP errors."""
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def load_event() -> dict:
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as handle:
        return json.load(handle)


def git_diff(base_sha: str, head_sha: str) -> str:
    out = subprocess.run(
        ["git", "diff", "--find-renames", base_sha, head_sha],
        check=True, capture_output=True, text=True)
    return out.stdout


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
            path = line[len("+++ b/"):]
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
    for attempt in (1, 2):
        try:
            response = http_json(url, {"x-goog-api-key": api_key}, payload)
            parts = response["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(json)?\s*|\s*```$", "", text,
                              flags=re.MULTILINE).strip()
            return json.loads(text)
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code == 429 or error.code >= 500:
                note(f"Gemini attempt {attempt} failed: HTTP {error.code}; "
                     "retrying once after 15s")
                time.sleep(15)
                continue
            raise
        except (KeyError, IndexError, json.JSONDecodeError) as error:
            raise RuntimeError(f"unparseable Gemini response: {error}")
    raise RuntimeError(f"Gemini API failed after retry: {last_error}")


def validate_findings(raw: object, valid: dict[str, set[int]],
                      cap: int) -> list[dict]:
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
        comment = str(item.get("comment", "")).strip()
        severity = str(item.get("severity", "medium")).lower()
        if severity not in ("high", "medium", "low"):
            severity = "medium"
        if (isinstance(path, str) and isinstance(line, int) and comment
                and line in valid.get(path, set())):
            findings.append({"path": path, "line": line,
                             "severity": severity, "comment": comment})
        if len(findings) >= cap:
            break
    return findings


def post_review(repo: str, number: int, head_sha: str, token: str,
                body: str, comments: list[dict]) -> None:
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    url = f"{api}/repos/{repo}/pulls/{number}/reviews"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    inline = [{"path": f["path"], "line": f["line"], "side": "RIGHT",
               "body": f"**[{f['severity']}]** {f['comment']}"}
              for f in comments]
    payload = {"commit_id": head_sha, "event": "COMMENT", "body": body,
               "comments": inline}
    try:
        http_json(url, headers, payload)
        return
    except urllib.error.HTTPError as error:
        if error.code != 422 or not inline:
            raise
    # A comment anchor was rejected: post the same review without inlines.
    listed = "\n".join(
        f"- `{f['path']}:{f['line']}` [{f['severity']}] {f['comment']}"
        for f in comments)
    fallback = {"commit_id": head_sha, "event": "COMMENT",
                "body": body + "\n\n" + listed, "comments": []}
    http_json(url, headers, fallback)


def main() -> int:
    note("## Gemini code review (advisory)")
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        note("No GEMINI_API_KEY available (fork pull request or missing "
             "secret); skipping the review.")
        return 0
    event = load_event()
    pr = event.get("pull_request", {})
    number = pr.get("number") or event.get("number")
    head_sha = pr.get("head", {}).get("sha", "")
    base_sha = pr.get("base", {}).get("sha", "")
    if not (number and head_sha and base_sha):
        note("Event payload is missing pull request fields; skipping.")
        return 0
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL).strip() \
        or DEFAULT_MODEL
    per_file = int(os.environ.get("GEMINI_MAX_FILE_CHARS", "20000"))
    total = int(os.environ.get("GEMINI_MAX_DIFF_CHARS", "120000"))
    cap = int(os.environ.get("GEMINI_MAX_COMMENTS", "10"))

    diff = truncate_diff(git_diff(base_sha, head_sha), per_file, total)
    if not diff.strip():
        note("Empty diff; nothing to review.")
        return 0
    valid = added_lines(diff)

    try:
        raw = gemini_review(model, api_key, diff)
    except Exception as error:  # noqa: BLE001 - advisory: never fail the job
        note(f"Gemini review unavailable: {error}")
        return 0

    summary = str(raw.get("summary", "")).strip() if isinstance(raw, dict) \
        else ""
    findings = validate_findings(raw, valid, cap)
    note(f"Model: {model}; findings kept: {len(findings)} "
         f"(added lines in diff: {sum(len(v) for v in valid.values())})")
    if summary:
        note(f"Summary: {summary}")

    body = ("**Gemini code review** (advisory, model `%s`; not a required "
            "check)\n\n%s" % (model, summary or "See inline comments."))
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        note("No GH_TOKEN; findings were not posted.")
        return 0
    try:
        post_review(os.environ["GITHUB_REPOSITORY"], int(number), head_sha,
                    token, body, findings)
    except urllib.error.HTTPError as error:
        note(f"Could not post the review (HTTP {error.code}); this is "
             "expected on fork pull requests, where the token is read-only.")
        return 0
    except Exception as error:  # noqa: BLE001
        note(f"Could not post the review: {error}")
        return 0
    note("Review posted as a COMMENT review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
