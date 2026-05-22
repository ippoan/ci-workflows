# ci-workflows

ippoan org 共通の GitHub Actions reusable workflows。

## Reusable Workflows

### frontend-ci.yml

フロントエンド (Nuxt / Cloudflare Workers) 向け CI/CD パイプライン。

#### Caller 側の必須 permissions

**重要**: caller ワークフロー (`test.yml` 等) に以下の permissions を設定すること。
不足すると `startup_failure` になり、ジョブが起動せずエラーメッセージも出ない。

```yaml
permissions:
  contents: write        # auto-merge で必要
  pull-requests: write   # pr-limit, auto-merge で必要
  packages: read         # npm_scope 使用時に必要
```

#### Caller テンプレート (Worker)

```yaml
name: CI

on:
  push:
    branches: [main]
    tags: ['v*']
  pull_request:
    branches: [main]

permissions:
  contents: write
  pull-requests: write
  packages: read

jobs:
  ci:
    uses: ippoan/ci-workflows/.github/workflows/frontend-ci.yml@main
    with:
      install_command: 'npm install'
      typecheck_command: 'npx tsc --noEmit'
      # has_integration: true          # 統合テストあり
      # post_install_script: |         # wrangler types 等
      #   npx wrangler types
      # deploy_staging_script: 'npx wrangler deploy --env staging --var VERSION:${{ github.sha }}'
      # deploy_release_script: 'npx wrangler deploy --var VERSION:${{ github.ref_name }}'
      # npm_scope: '@ippoan'           # GitHub Packages 使用時
    secrets: inherit
```

#### Caller テンプレート (Nuxt)

```yaml
name: CI

on:
  push:
    branches: [main]
    tags: ['v*']
  pull_request:
    branches: [main]

permissions:
  contents: write
  pull-requests: write
  packages: read

jobs:
  ci:
    uses: ippoan/ci-workflows/.github/workflows/frontend-ci.yml@main
    with:
      project_type: 'nuxt'
      working_directory: 'web'
      # cache_dependency_path: 'web/package-lock.json'
      # post_install_script: 'npx nuxt prepare'
      # deploy_staging_script: 'npx wrangler deploy --env staging'
      # deploy_release_script: 'npx wrangler deploy'
      # npm_scope: '@ippoan'
    secrets: inherit
```

#### 主な inputs

| input | デフォルト | 説明 |
|-------|-----------|------|
| `project_type` | `nuxt` | `nuxt` or `worker` |
| `working_directory` | `.` | npm コマンドの作業ディレクトリ |
| `install_command` | `npm ci` | 依存インストールコマンド |
| `has_tests` | `true` | Vitest 実行するか |
| `has_integration` | `false` | 統合テスト実行するか |
| `has_deploy` | `true` | デプロイジョブ実行するか |
| `npm_scope` | `''` | GitHub Packages スコープ |
| `post_install_script` | `''` | install 後のスクリプト |
| `deploy_staging_script` | `''` | staging デプロイスクリプト |
| `deploy_release_script` | `''` | リリースデプロイスクリプト |
| `npm_publish_directory` | `''` | npm パッケージディレクトリ (設定時に publish 有効) |
| `npm_publish_name` | `''` | npm パッケージ名 (propagation 用、例: `@ippoan/auth-client`) |
| `npm_publish_propagate_repos` | `''` | publish 後に自動更新する対象リポジトリ (カンマ区切り) |
| `npm_publish_propagate_dirs` | `''` | 対象リポジトリの working directory (カンマ区切り) |

### go-ci.yml

Go 向け CI pipeline。`vet` / `test` / `build` の 3 job + (opt-in) `secret-verify` で構成される。status check 名は caller の job id (例: `ci`) + ' / ' + reusable job name で、`ci / vet`, `ci / test`, `ci / build`, `ci / secret-verify` の 4 つに pin される (auth-worker の `ippoan-go-default` branch-protection preset 参照)。

#### Caller テンプレート (Go on Cloud Run、secret-verify あり)

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

jobs:
  ci:
    uses: ippoan/ci-workflows/.github/workflows/go-ci.yml@main
    with:
      gcp_secret_verify_project: cloudsql-sv
      gcp_secret_verify_provider: ${{ vars.GCP_WIF_PROVIDER }}
      gcp_secret_verify_sa: ${{ vars.GCP_WIF_SERVICE_ACCOUNT_STAGING }}
```

3 つの verify input を全部空にすると `secret-verify` job は skip され、`vet/test/build` だけが status check に出る (= 既存 caller への backward compat)。

### Secret verify を frontend-ci.yml / go-ci.yml の中に取り込む経緯

旧 pattern: 各 caller repo が `.github/workflows/secret-verify.yml` を別 file で持ち、`ippoan/ci-workflows/.github/workflows/secret-verify-gcp.yml@main` を直接呼んでいた。問題:

1. caller 毎の boilerplate (40 行前後) が必要
2. status check の DAG が `ci / *` と `verify / *` の 2 並列 chain になり、branch protection の required-check 構成が複雑化
3. typecheck / build がまだ赤い commit で Secret Manager を叩いて gcloud quota を浪費

これを 2026-05 の `feat(ci): bake secret-verify into go-ci/frontend-ci` (PR #XX) で reusable 内に **直列に内製化**。caller は `gcp_secret_verify_*` 3 input を渡すだけで `ci / secret-verify` 段が serial で動く。`secret-verify-gcp.yml` 単体 caller も維持されるので柔軟な構成は残せる。

### tag-release.yml / dev-tag-release.yml

リリースタグ自動採番の reusable 2 種:

| reusable | 想定 trigger | タグ形式 | 用途 |
|---|---|---|---|
| `tag-release.yml` | `workflow_dispatch` (手動 / ci-dashboard) | `v{major}.{minor}.{patch}` semver | 正式リリース。手動 |
| `dev-tag-release.yml` | `push: branches: [main]` | `{prefix}{N}` カウンタ (default `dev-N`) | 開発リリース。自動 |

両方とも `secrets.TAG_RELEASE_PAT` (tag push 後の release workflow 連鎖発火に必要な PAT) を要求する。

#### dev-tag-release.yml caller 例

```yaml
name: Dev Release

on:
  push:
    branches: [main]
    paths:
      - 'src/**'
      - 'Cargo.toml'
      - 'Cargo.lock'
      - 'build.rs'

permissions:
  contents: write

jobs:
  dev-release:
    uses: ippoan/ci-workflows/.github/workflows/dev-tag-release.yml@main
    secrets:
      TAG_RELEASE_PAT: ${{ secrets.TAG_RELEASE_PAT }}
```

caller の release.yml は `on: push: tags: ["v*", "dev-*"]` のように **両方を受ける**ようにする。`rust-binary-release.yml` は tag に `-` が含まれていれば自動で prerelease 扱いにするので `dev-N` は `releases/latest` API に出ない (= stable consumer は影響無し)。

dev チャネルを使いたい consumer (install スクリプト等) は `releases?per_page=100` を叩いて `dev-*` の最大 N を解決する。

## よくあるトラブル

### startup_failure

caller の `permissions` が不足している。上記の必須 permissions を確認すること。
GitHub は reusable workflow のジョブが要求する権限が caller で許可されていない場合、
ジョブを起動せず `startup_failure` を返す。エラーメッセージは表示されない。
