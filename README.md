# ci-workflows

Shared GitHub Actions reusable workflows for ippoan + ohishi-exp projects.

## Usage

Create `.github/workflows/test.yml` in your project:

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read
  packages: read

jobs:
  ci:
    uses: ippoan/ci-workflows/.github/workflows/frontend-ci.yml@main
    with:
      has_tests: true
      typecheck_command: 'npx nuxi typecheck'
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
| `working_directory` | `.` | Working directory for npm commands |
| `node_version` | `24` | Node.js version |
| `install_command` | `npm ci` | Install command |
| `has_tests` | `true` | Run test job |
| `has_integration` | `false` | Run integration test job |
| `has_deploy` | `true` | Run deploy jobs |
| `typecheck_command` | `npx nuxi typecheck` | Type check command |
| `pre_install_script` | | Script before npm install |
| `post_install_script` | | Script after npm install |
| `use_auth_client_dev` | `false` | Use auth-client dev action |
| `test_command` | `npx vitest run --coverage ...` | Test command |
| `deploy_staging_script` | `npm run build && npx wrangler deploy --env staging` | Staging deploy script |
| `deploy_release_script` | `npm run build && npx wrangler deploy` | Release deploy script |
| `integration_compose_file` | `docker-compose.test.yml` | Docker Compose file |
| `integration_test_command` | `npx vitest run` | Integration test command |
| `integration_env` | | Space-separated KEY=VALUE pairs |
| `npm_scope` | | npm scope for GitHub Packages |
| `cache_dependency_path` | | Path to package-lock.json |

## Jobs

| Job | Condition | Description |
|-----|-----------|-------------|
| pr-limit | PR only | 1 PR per author limit |
| test | `has_tests=true` | vitest + coverage + Job Summary |
| typecheck | always | Type checking |
| integration-test | `has_integration=true` | Docker Compose + live tests |
| deploy-staging | PR, after test+typecheck pass | Cloudflare Workers staging |
| deploy-release | v* tag push | Cloudflare Workers production |

## Features

- **Coverage 100% enforcement**: If `scripts/check_coverage_100.mjs` exists, runs it automatically
- **Job Summary**: Test results + coverage table + 100% file tracking
- **coverage-final.json fallback**: Works with both `coverage-summary.json` and `coverage-final.json`
- **Tag-based deploy**: deploy-release は v* タグ push 時のみ実行（caller に `tags: ['v*']` を追加すること）

## Notes

- `wrangler.toml` に `account_id` が必要（CI で Cloudflare アカウントを特定するため）
- cross-org では `secrets: inherit` が動かないため、明示的に secrets を渡す
