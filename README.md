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
