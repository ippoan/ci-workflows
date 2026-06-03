#!/usr/bin/env python3
"""Validate config/release-wave-targets.yaml.

Release Wave の設定ミスを CI で早期検知する。これが無いと、設定漏れは
**実際に flip / rollback を叩いた時に handler が初めて loud fail する**
(= 本番操作の途中で気付く) ことになる。代表例:

  - consumer repo に release-wave.yml caller を足したのに targets.yaml へ
    登録し忘れ → handler の "Parse dispatch + lookup targets" が
    "<repo> is not registered" で fail (実例: ippoan/nuxt-trouble)。
  - cloudflare-workers の repo が @ippoan/* (private GitHub Packages) に
    依存しているのに targets entry へ npm_scope: '@ippoan' を書き忘れ →
    flip/rollback job の npm install が 401 Unauthorized で fail
    (実例: ippoan/nuxt-notify)。

検査:
  1. structural (offline) — 各 entry の platform と必須 field。
  2. caller↔registration (online) — org をスキャンし、release-wave.yml
     caller を持つ repo が targets.yaml に登録されているか (両方向)。
  3. npm_scope 整合 (online) — registered な cloudflare-workers repo が
     @ippoan/* dep を持つなら npm_scope: '@ippoan' を必須化。

online 検査は GITHUB_TOKEN が要る。token が無い / ONLINE=0 の時は structural
のみ実行する (= ローカルや fork PR でも最低限通る)。

env:
  CFG          targets.yaml path (default config/release-wave-targets.yaml)
  GITHUB_TOKEN online 検査用 (public repo の contents/list を読む)
  ONLINE       "0" で online 検査を skip (default "1")
  WAVE_ORGS    caller スキャン対象 org の comma 区切り (default "ippoan")

exit 1 on any error。
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request

PRIVATE_SCOPE = "@ippoan"
CALLER_PATH = ".github/workflows/release-wave.yml"
CALLER_MARKER = "release-wave-handler.yml"

CFG = os.environ.get("CFG", "config/release-wave-targets.yaml")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
ORGS = [o.strip() for o in os.environ.get("WAVE_ORGS", "ippoan").split(",") if o.strip()]
ONLINE = os.environ.get("ONLINE", "1") != "0" and bool(TOKEN)

errors: list[str] = []
warnings: list[str] = []


# ---------------------------------------------------------------------------
# pure logic (unit-testable, no network)
# ---------------------------------------------------------------------------
def validate_structure(targets: dict) -> list[str]:
    errs: list[str] = []
    if not targets:
        return [f"{CFG}: 'targets' is empty or missing"]
    for repo, e in targets.items():
        e = e or {}
        pf = e.get("platform")
        if pf not in ("cloudflare-workers", "cloudrun"):
            errs.append(f"{repo}: platform must be 'cloudflare-workers' or 'cloudrun' (got {pf!r})")
            continue
        if pf == "cloudrun":
            if not e.get("gcp_project") or not e.get("gcp_region") or not e.get("services"):
                errs.append(f"{repo}: cloudrun requires gcp_project, gcp_region and non-empty services")
        else:  # cloudflare-workers
            if not e.get("cf_account_id"):
                errs.append(f"{repo}: cloudflare-workers requires cf_account_id")
            if not e.get("cf_worker_name") and not e.get("monorepo_units"):
                errs.append(f"{repo}: cloudflare-workers requires cf_worker_name or monorepo_units")
    return errs


def collect_deps(package_json: dict) -> set[str]:
    deps: set[str] = set()
    for k in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        deps.update((package_json.get(k) or {}).keys())
    return deps


def npm_scope_violation(repo: str, entry: dict, deps: set[str]) -> str | None:
    """@ippoan/* dep を持つのに npm_scope が未設定なら error 文字列を返す。"""
    has_private = any(name.startswith(PRIVATE_SCOPE + "/") for name in deps)
    if has_private and (entry or {}).get("npm_scope") != PRIVATE_SCOPE:
        return (
            f"{repo}: depends on {PRIVATE_SCOPE}/* but entry is missing "
            f"npm_scope: '{PRIVATE_SCOPE}' (flip/rollback の npm install が 401 になる)"
        )
    return None


# ---------------------------------------------------------------------------
# GitHub API (online)
# ---------------------------------------------------------------------------
def _gh(path: str):
    req = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {TOKEN}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "validate-release-wave-targets",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_file(repo: str, path: str) -> str | None:
    """repo の path を decode して返す。404 は None。他 HTTP error は raise。"""
    try:
        data = _gh(f"/repos/{repo}/contents/{path}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    if isinstance(data, dict) and data.get("encoding") == "base64":
        return base64.b64decode(data["content"]).decode("utf-8", "replace")
    return None


def list_org_repos(org: str) -> list[str]:
    repos: list[str] = []
    page = 1
    while True:
        try:
            data = _gh(f"/orgs/{org}/repos?per_page=100&page={page}&type=public")
        except urllib.error.HTTPError as e:
            warnings.append(f"list repos for org {org}: HTTP {e.code} (skipped)")
            break
        if not data:
            break
        repos += [r["full_name"] for r in data]
        if len(data) < 100:
            break
        page += 1
    return repos


def run_online(targets: dict) -> None:
    registered = set(targets.keys())

    # 2. org をスキャンして caller を持つ repo を集める
    callers: set[str] = set()
    scanned_any = False
    for org in ORGS:
        repos = list_org_repos(org)
        if repos:
            scanned_any = True
        for repo in repos:
            try:
                txt = fetch_file(repo, CALLER_PATH)
            except Exception as ex:  # noqa: BLE001
                warnings.append(f"{repo}: fetch {CALLER_PATH} failed: {ex}")
                continue
            if txt is not None and CALLER_MARKER in txt:
                callers.add(repo)

    if scanned_any:
        for repo in sorted(callers - registered):
            errors.append(
                f"{repo}: has {CALLER_PATH} caller but is NOT registered in {CFG} "
                f"(add a targets entry)"
            )
        for repo in sorted(registered - callers):
            warnings.append(
                f"{repo}: registered in {CFG} but no {CALLER_PATH} caller found "
                f"(dead entry, or caller not yet added?)"
            )

    # 3. npm_scope 整合 (cloudflare-workers の registered repo)
    for repo, e in targets.items():
        e = e or {}
        if e.get("platform") != "cloudflare-workers":
            continue
        pkg_txt = None
        for path in ("package.json", "web/package.json"):
            try:
                pkg_txt = fetch_file(repo, path)
            except Exception as ex:  # noqa: BLE001
                warnings.append(f"{repo}: fetch {path} failed: {ex}")
                pkg_txt = None
            if pkg_txt is not None:
                break
        if pkg_txt is None:
            warnings.append(f"{repo}: no package.json found (cannot verify npm_scope)")
            continue
        try:
            pj = json.loads(pkg_txt)
        except Exception:  # noqa: BLE001
            warnings.append(f"{repo}: package.json parse failed (cannot verify npm_scope)")
            continue
        v = npm_scope_violation(repo, e, collect_deps(pj))
        if v:
            errors.append(v)


# ---------------------------------------------------------------------------
def finish() -> None:
    for w in warnings:
        print(f"::warning::{w}")
    if errors:
        for er in errors:
            print(f"::error::{er}")
        print(f"\n{len(errors)} error(s) in {CFG}", file=sys.stderr)
        sys.exit(1)
    mode = "online" if ONLINE else "structural-only"
    print(f"OK: {CFG} valid ({mode}, {len(warnings)} warning(s))")


def selftest() -> None:
    """pure logic の最小テスト (= 今回の 2 失敗を検知できることの回帰ガード)。"""
    # structural
    assert validate_structure({"r": {"platform": "x"}})
    assert not validate_structure({"r": {"platform": "cloudflare-workers", "cf_account_id": "a", "cf_worker_name": "w"}})
    assert validate_structure({"r": {"platform": "cloudflare-workers", "cf_account_id": "a"}})  # no worker/units
    assert validate_structure({"r": {"platform": "cloudrun", "gcp_project": "p"}})  # missing region/services
    # npm_scope: @ippoan dep but no scope -> violation (nuxt-notify case)
    assert npm_scope_violation("r", {}, {"@ippoan/auth-client"})
    assert npm_scope_violation("r", {"npm_scope": "@other"}, {"@ippoan/auth-client"})
    # has scope -> ok
    assert npm_scope_violation("r", {"npm_scope": "@ippoan"}, {"@ippoan/auth-client"}) is None
    # no private dep -> ok regardless
    assert npm_scope_violation("r", {}, {"vue", "nuxt"}) is None
    assert collect_deps({"dependencies": {"a": "1"}, "devDependencies": {"b": "2"}}) == {"a", "b"}
    print("selftest OK")


def main() -> None:
    if "--selftest" in sys.argv:
        selftest()
        return
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        print("PyYAML required (pip install pyyaml)", file=sys.stderr)
        sys.exit(2)
    cfg = yaml.safe_load(open(CFG, encoding="utf-8")) or {}
    targets = cfg.get("targets") or {}
    errors.extend(validate_structure(targets))
    if ONLINE:
        run_online(targets)
    else:
        warnings.append("online checks skipped (no GITHUB_TOKEN or ONLINE=0)")
    finish()


if __name__ == "__main__":
    main()
