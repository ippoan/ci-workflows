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
