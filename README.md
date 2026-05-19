# ci-workflows

Shared GitHub Actions reusable workflows for ippoan + ohishi-exp projects.

## Usage

Create `.github/workflows/test.yml` in your project:

```yaml
name: CI
on:
  push:
    branches: [main]
    tags: ['v*']
  pull_request:
    branches: [main]

permissions:
  contents: read
  packages: read

jobs:
  ci:
    uses: ippoan/ci-workflows/.github/workflows/frontend-ci.yml@main
    with:
      project_type: nuxt  # or "worker"
      has_tests: true
    secrets: inherit
```

### Cross-org (ohishi-exp etc.)

`secrets: inherit` は **同一 org 内でのみ動作**する。cross-org の場合は明示的に渡す:

```yaml
    secrets:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

## Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `project_type` | `nuxt` | `nuxt` or `worker` — typecheck/deploy コマンドを自動設定 |
| `working_directory` | `.` | Working directory for npm commands |
| `node_version` | `24` | Node.js version |
| `install_command` | `npm ci` | Install command |
| `has_tests` | `true` | Run test job |
| `has_integration` | `false` | Run integration test job |
| `has_deploy` | `true` | Run deploy jobs |
| `typecheck_command` | auto | nuxt=`nuxi typecheck`, worker=`tsc --noEmit` (override 可) |
| `pre_install_script` | | Script before npm install |
| `post_install_script` | | Script after npm install |
| `use_auth_client_dev` | `false` | Use auth-client dev action |
| `test_command` | `npx vitest run --coverage ...` | Test command |
| `deploy_staging_script` | auto | nuxt=`build+deploy`, worker=`deploy only` (override 可) |
| `deploy_release_script` | auto | Same as staging but without `--env staging` |
| `integration_compose_file` | `docker-compose.test.yml` | Docker Compose file |
| `integration_test_command` | `npx vitest run` | Integration test command |
| `integration_env` | | Space-separated KEY=VALUE pairs |
| `npm_scope` | | npm scope for GitHub Packages |
| `cache_dependency_path` | | Path to package-lock.json |

## Jobs

| Job | Condition | Description |
|-----|-----------|-------------|
| pr-limit | PR only | 1 PR per author limit + **auto-merge 有効化** |
| branch-protection | PR only | branch protection / auto-merge 設定を検証 |
| test | `has_tests=true` | vitest + coverage + Job Summary |
| typecheck | always | Type checking |
| integration-test | `has_integration=true` | Docker Compose + live tests |
| deploy-staging | PR, after checks pass | Cloudflare Workers staging |
| deploy-release | v* tag push | Cloudflare Workers production |

## Auto-merge

PR の required checks が全 pass すると**自動で squash merge** される。

仕組み:
1. `pr-limit` ジョブが `gh pr merge --auto --squash` を実行
2. 全 required checks pass 後に GitHub が自動 merge

前提条件 (branch-protection ジョブで検証):
- Branch protection が有効
- Required status checks に `ci /` 系チェックが設定済み
- `enforce_admins` が有効
- Force push / branch deletion が禁止
- **Allow auto-merge** がリポジトリ設定で有効

## Features

- **Coverage 100% enforcement**: `scripts/check_coverage_100.mjs` or `npx check-coverage-100` があれば自動実行
- **Job Summary**: Test results + coverage table + 100% file tracking
- **coverage-final.json fallback**: `coverage-summary.json` と `coverage-final.json` 両対応
- **Tag-based deploy**: deploy-release は v* タグ push 時のみ (caller に `tags: ['v*']` を追加)
- **project_type**: `nuxt` / `worker` で typecheck/deploy コマンドを自動切替

## Notes

- `wrangler.toml` / `wrangler.jsonc` に `account_id` が必要
- cross-org では `secrets: inherit` が動かないため、明示的に secrets を渡す
- `@ippoan/test-utils` パッケージで mock/live テストヘルパーを共有可能

## `branch-protection.yml`

Reusable workflow that **applies** branch protection via the GitHub Branches API
(`PUT /repos/{owner}/{repo}/branches/{branch}/protection`). See the file header
for the full input list and a copy-pasteable caller snippet.

```yaml
# .github/workflows/branch-protection.yml in the consumer repo
name: branch-protection
on:
  workflow_dispatch:
  push:
    branches: [main]

permissions:
  contents: read
  administration: write

jobs:
  apply:
    uses: ippoan/ci-workflows/.github/workflows/branch-protection.yml@main
    with:
      branch: main
      required_checks: |
        ci / rustfmt
        ci / clippy
        ci / cargo test
```

**`workflow_dispatch` belongs on the caller, not the reusable.** The
reusable is `workflow_call` only on purpose: a workflow file that exposes
`workflow_dispatch` is incorrectly matched against push events by GitHub
([actions/runner#4001](https://github.com/actions/runner/issues/4001))
and emits a phantom 0-job failure on every push to any branch.
Consumers that want ad-hoc manual application get it by listing
`workflow_dispatch` on their *caller* workflow, which is the standard
pattern and avoids the bug because the caller has a real job (`uses:`)
that the push evaluator can match. ci-workflows itself self-applies via
`branch-protection-self.yml` (push-only, no dispatch).

Paired with `branch-protection-drift-check.yml` below for closed-loop IaC:

1. Caller defines `.github/branch-protection.yml` (spec).
2. `branch-protection.yml` reads the spec values and applies them.
3. `branch-protection-drift-check.yml` validates spec entries against the
   actual CI check-runs on the target ref.

## `branch-protection-drift-check.yml`

Reusable workflow that detects drift between a repo's declared branch
protection spec and the actual check-runs produced by CI. Catches the
class of bug where renaming a CI job (e.g. moving to a reusable workflow,
changing the 2-tier `ci / rustfmt` to 3-tier `ci / ci / rustfmt`) silently
leaves the protection rule referencing phantom checks that block all
future merges.

```yaml
# .github/workflows/branch-protection-drift.yml in the consumer repo
name: branch-protection-drift
on:
  pull_request:
    branches: [main]
    paths:
      - '.github/branch-protection.yml'
      - '.github/workflows/**'
  push:
    branches: [main]
  schedule:
    - cron: '17 9 * * 1'  # weekly Monday sanity check

jobs:
  drift:
    uses: ippoan/ci-workflows/.github/workflows/branch-protection-drift-check.yml@main
    permissions:
      contents: read
      checks: read
```

Spec file format (`.github/branch-protection.yml`):

```yaml
branch: main
required_checks:
  - "ci / ci / rustfmt"
  - "ci / ci / clippy"
  - "ci / ci / cargo test"
  - "ci / ci / cargo build --release"
```

| Input | Default | Description |
|-------|---------|-------------|
| `spec_path` | `.github/branch-protection.yml` | Spec file path in caller repo |
| `head_ref` | `main` | Git ref whose check-runs are the source of truth |
| `fail_on_extra` | `false` | Fail when CI produces checks not in spec (default: warn) |

Failure modes the drift check distinguishes:

| Condition | Outcome | Meaning |
|-----------|---------|---------|
| Spec entry missing from ref's check-runs entirely | **fail** | Phantom check — protection rule blocks all PRs |
| Spec entry ran on ref but did not succeed | warn | CI health issue, not drift |
| Check ran successfully but not in spec | warn (or fail with `fail_on_extra`) | Optional check not declared as required |
| All spec entries succeeded on ref | pass | Spec and CI agree |

The job emits a Job Summary table so the failure is self-documenting in the
Actions UI without needing to read the raw logs.

## `snapshot-check.yml`

`ippoan/ippoan-dev-plans` で管理している plan Issue と consumer repo の `manifests/production.snapshot.json` の整合性を CI で検証する reusable workflow。

```yaml
jobs:
  snapshot-check:
    uses: ippoan/ci-workflows/.github/workflows/snapshot-check.yml@main
    secrets:
      PAT: ${{ secrets.GHCR_NPM_PAT }}  # read:packages + repo (Issues read)
```

| Input | Default | Description |
|-------|---------|-------------|
| `node_version` | `22` | Node.js version |
| `working_directory` | `.` | `package.json` + `dev-plans.config.js` 配置先 |
| `install_command` | `npm ci` | Install command |
| `npm_scope` | `@ippoan` | npm scope for GitHub Packages registry |

consumer repo に必要なもの:
- `package.json` の devDependencies に `@ippoan/dev-plans-snapshot`
- ルートに `.npmrc` (`@ippoan:registry=https://npm.pkg.github.com`)
- ルートに `dev-plans.config.js` (`scopeLabels` / `grepPatterns` / `sourceDirs`)
- `manifests/production.snapshot.json` (commit 済み)

## `shell-ci.yml`

Shell-script repo (例: `yhonda-ohishi/claude-hooks`) 向け reusable workflow。

1. **shellcheck**: 全 `*.sh` を lint
2. **test** (optional): 任意の bash テストランナーを実行 (stdin-pipe hook test 等)

```yaml
name: test
on: [push, pull_request]
permissions:
  contents: read
  issues: read
jobs:
  ci:
    uses: ippoan/ci-workflows/.github/workflows/shell-ci.yml@main
    with:
      test_script: tests/test-foo.sh        # optional, omit to skip test job
      test_needs_gh: true                   # gh CLI を使うテストの場合
      shellcheck_opts: "-e SC1091 -e SC2155"
      ignore_paths: "tests"                 # newline-separated
```

| Input | Default | Description |
|-------|---------|-------------|
| `scandir` | `.` | shellcheck 走査 root |
| `severity` | `warning` | shellcheck severity (error\|warning\|info\|style) |
| `ignore_paths` | `''` | 無視 path (newline-separated) |
| `ignore_names` | `''` | 無視 file 名 (newline-separated) |
| `shellcheck_opts` | `''` | `SHELLCHECK_OPTS` env (例: `-e SC2086`) |
| `test_script` | `''` | repo-relative テストランナー。空なら test job を skip |
| `test_needs_gh` | `false` | true で `GH_TOKEN=${{ secrets.GITHUB_TOKEN }}` を export |
| `test_runs_on` | `ubuntu-latest` | test job の runner label |

`secrets: inherit` は不要 (`GITHUB_TOKEN` は workflow_call で permissions block 経由)。
