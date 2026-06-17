#!/usr/bin/env python3
"""ci-shape-report: caller repo の `.github/workflows/*.yml` を parse して
`ci-dashboard.ippoan.org/webhooks/ci-shape` に POST する。

Refs ippoan/ci-dashboard#378.

入力 env:
  GITHUB_REPOSITORY    `<owner>/<repo>` (Actions の標準 env)
  GITHUB_SHA           caller の head sha (Actions の標準 env)
  CI_SHAPE_DASHBOARD   ci-dashboard origin (default = https://ci-dashboard.ippoan.org)
  CI_SHAPE_SECRET      X-CI-Shape-Secret header value (= ippoan org secret
                       RELEASE_WAVE_WEBHOOK_SECRET と同値)
"""

from __future__ import annotations

import glob
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

import yaml  # type: ignore[import-not-found]

SCHEMA_VERSION = 1


def parse_triggers(on_block: object) -> list[str]:
    """`on:` を flat な人間可読 string list に潰す。"""
    out: list[str] = []
    if isinstance(on_block, str):
        return [on_block]
    if isinstance(on_block, list):
        return [str(x) for x in on_block]
    if isinstance(on_block, dict):
        for k, v in on_block.items():
            if isinstance(v, dict):
                branches = v.get("branches")
                tags = v.get("tags")
                if branches:
                    for b in branches if isinstance(branches, list) else [branches]:
                        out.append(f"{k}:branch({b})")
                if tags:
                    for t in tags if isinstance(tags, list) else [tags]:
                        out.append(f"{k}:tag({t})")
                if not branches and not tags:
                    out.append(str(k))
            elif isinstance(v, list):
                out.append(f"{k}:{','.join(str(x) for x in v)}")
            else:
                out.append(str(k))
    return out


def parse_permissions(perms_block: object) -> dict[str, str]:
    if perms_block is None:
        return {}
    if isinstance(perms_block, str):
        return {"_all": perms_block}
    if isinstance(perms_block, dict):
        return {str(k): str(v) for k, v in perms_block.items()}
    return {}


def parse_uses(uses: str) -> dict[str, str] | None:
    """`ippoan/ci-workflows/.github/workflows/frontend-ci.yml@main` を分解。
    `./.github/workflows/foo.yml` (local reusable) は対象外として None。"""
    if not isinstance(uses, str) or "@" not in uses or uses.startswith("./"):
        return None
    target, ref = uses.rsplit("@", 1)
    parts = target.split("/")
    if len(parts) < 5 or parts[2] != ".github" or parts[3] != "workflows":
        return None
    return {
        "owner": parts[0],
        "repo": parts[1],
        "file": "/".join(parts[2:]),
        "ref": ref,
        "reusable_name": parts[-1],
    }


def is_pinned_sha(ref: str) -> bool:
    """40-char hex = full SHA pin。`v1` / `main` 等は untrusted/mutable。"""
    if len(ref) != 40:
        return False
    try:
        int(ref, 16)
        return True
    except ValueError:
        return False


def analyze_workflow_yaml(yaml_text: str, file_path: str) -> dict[str, object] | None:
    try:
        doc = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        return {
            "file": file_path,
            "parse_error": str(e)[:200],
            "deviations": ["yaml-parse-error"],
        }
    if not isinstance(doc, dict):
        return None
    name = doc.get("name") if isinstance(doc.get("name"), str) else None
    # YAML quirk: bare `on:` parses as boolean True.
    on_block = doc.get("on")
    if on_block is None and True in doc:
        on_block = doc[True]
    triggers = parse_triggers(on_block)
    top_perms = parse_permissions(doc.get("permissions"))

    jobs = doc.get("jobs") if isinstance(doc.get("jobs"), dict) else {}
    reusable_calls: list[dict[str, object]] = []
    self_jobs: list[str] = []
    job_perms_union: set[str] = set()
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        uses = job.get("uses")
        if isinstance(uses, str):
            parsed = parse_uses(uses)
            if parsed is not None:
                secrets = job.get("secrets")
                reusable_calls.append(
                    {
                        "job_id": str(job_id),
                        "target_owner": parsed["owner"],
                        "target_repo": parsed["repo"],
                        "target_file": parsed["file"],
                        "reusable_name": parsed["reusable_name"],
                        "ref": parsed["ref"],
                        "pinned_sha": is_pinned_sha(parsed["ref"]),
                        "secrets_inherit": secrets == "inherit",
                    }
                )
                continue
        self_jobs.append(str(job_id))
        job_perms = parse_permissions(job.get("permissions"))
        job_perms_union.update(job_perms.keys())

    return {
        "file": file_path,
        "name": name,
        "triggers": triggers,
        "permissions": top_perms,
        "job_permissions_union": sorted(job_perms_union),
        "reusable_calls": reusable_calls,
        "self_jobs": self_jobs,
    }


def detect_deviations(workflow: dict[str, object]) -> list[str]:
    """silent trap を loud にする逸脱フラグ。"""
    flags: list[str] = []
    if workflow.get("parse_error"):
        # already attached
        return list(workflow.get("deviations") or [])

    reusable_calls = workflow.get("reusable_calls", [])
    if not isinstance(reusable_calls, list):
        return flags

    top_perms = workflow.get("permissions") if isinstance(workflow.get("permissions"), dict) else {}
    job_perms_union = workflow.get("job_permissions_union") or []
    declared_perms: set[str] = set()
    if isinstance(top_perms, dict):
        declared_perms.update(top_perms.keys())
    if isinstance(job_perms_union, list):
        declared_perms.update(job_perms_union)

    has_secret_verify_caller = False
    has_cross_org_inherit = False

    for call in reusable_calls:
        if not isinstance(call, dict):
            continue
        if call.get("pinned_sha") is False:
            ref = str(call.get("ref", ""))
            if ref in ("main", "master"):
                flags.append("unpinned-ref-main")
            elif ref:
                flags.append(f"unpinned-ref:{ref}")
        name = call.get("reusable_name")
        if name in {"frontend-ci.yml", "go-ci.yml", "lib-ci.yml"}:
            has_secret_verify_caller = True
        if name == "auto-merge.yml" and call.get("secrets_inherit"):
            has_cross_org_inherit = True

    if has_secret_verify_caller and "id-token" not in declared_perms:
        flags.append("missing-id-token-write")
    if has_cross_org_inherit:
        flags.append("auto-merge-secrets-inherit")

    # dedupe
    seen: set[str] = set()
    deduped: list[str] = []
    for f in flags:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    return deduped


def build_payload(owner: str, repo: str) -> dict[str, object]:
    files = sorted(glob.glob(".github/workflows/*.yml") + glob.glob(".github/workflows/*.yaml"))
    workflows: list[dict[str, object]] = []
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            workflows.append({"file": path, "fetch_error": True, "deviations": [f"read-error:{e}"[:80]]})
            continue
        analyzed = analyze_workflow_yaml(text, path)
        if analyzed is None:
            continue
        analyzed["deviations"] = detect_deviations(analyzed)
        workflows.append(analyzed)

    return {
        "schema_version": SCHEMA_VERSION,
        "owner": owner,
        "repo": repo,
        "head_sha": os.environ.get("GITHUB_SHA", "")[:40],
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "workflows": workflows,
    }


def post(payload: dict[str, object], dashboard: str, secret: str) -> int:
    url = dashboard.rstrip("/") + "/webhooks/ci-shape"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        method="POST",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-CI-Shape-Secret": secret,
            "User-Agent": "ci-shape-report",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"POST {url} -> {resp.status}", file=sys.stderr)
            print(resp.read().decode("utf-8", errors="replace"), file=sys.stderr)
            return 0
    except urllib.error.HTTPError as e:
        print(f"POST {url} -> {e.code}", file=sys.stderr)
        print(e.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"POST {url} failed: {e.reason}", file=sys.stderr)
        return 1


def main() -> int:
    repo_full = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in repo_full:
        print("GITHUB_REPOSITORY required (owner/repo)", file=sys.stderr)
        return 2
    owner, repo = repo_full.split("/", 1)
    dashboard = os.environ.get("CI_SHAPE_DASHBOARD", "https://ci-dashboard.ippoan.org")
    secret = os.environ.get("CI_SHAPE_SECRET", "")
    if not secret:
        print("CI_SHAPE_SECRET is empty", file=sys.stderr)
        return 2
    payload = build_payload(owner, repo)
    summary = {
        "workflow_count": len(payload["workflows"]),
        "deviation_count": sum(
            len((w.get("deviations") if isinstance(w, dict) else []) or [])
            for w in payload["workflows"]
        ),
    }
    print(f"summary: {summary}", file=sys.stderr)
    return post(payload, dashboard, secret)


if __name__ == "__main__":
    sys.exit(main())
