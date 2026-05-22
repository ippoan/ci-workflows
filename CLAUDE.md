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

##### secret-verify を併用する場合 (追加)

`gcp_secret_verify_*` input を渡して `secret-verify` job を有効化する **or
将来有効化する可能性がある** caller は、追加で `id-token: write` を
declare すること。`if:` で skip される run でも、reusable workflow の parse
時に caller permissions check が走るため、declare していないと `secret-
verify` を **使わない caller でも** `startup_failure` になる。

top-level に追加するか、`jobs.<id>:` の job-level に追加するかは reusable 次第:

#### frontend-ci.yml caller → **Option A (top-level) 推奨**

frontend-ci.yml は内部に `auto-merge` job (= `contents: write` + `pull-requests: write` 要求) を持つため、job-level で permissions を絞ると auto-merge が permission 不足で `startup_failure` する。top-level に全部宣言するのが簡単:

```yaml
# Option A: top-level
permissions:
  contents: write
  pull-requests: write
  packages: read
  id-token: write        # secret-verify (nested) で必要
```

実例: `ippoan/secrets-inventory` の `test.yml`。

#### go-ci.yml caller → **Option B (job-level) でも可**

go-ci.yml は `vet/test/build/secret-verify` の 4 job のみで auto-merge job を持たないため、job-level で `contents: read + id-token: write` だけに絞れる:

```yaml
# Option B: job-level
permissions:
  contents: read
jobs:
  ci:
    uses: ippoan/ci-workflows/.github/workflows/go-ci.yml@main
    permissions:
      contents: read
      id-token: write    # secret-verify で必要
    with: { ... }
```

実例: `ippoan/secrets-inventory-gcp` の `ci.yml`。

#### 共通注意

`if:` で skip 予定の run でも、reusable parse 時の caller permissions
check は走るため、`gcp_secret_verify_*` input を渡さない caller でも
`id-token: write` の declare が必要 (= frontend-ci.yml / go-ci.yml を
そもそも使うなら宣言必須)。

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

#### `id-token: write` 不足のケース (frontend-ci.yml / go-ci.yml)

`feat(ci): bake secret-verify into go-ci/frontend-ci` (ci-workflows#38) で
nested 内蔵された `secret-verify` job が `permissions: id-token: write`
を要求する。caller の `permissions:` (top-level or job-level) で declare
していないと、**`gcp_secret_verify_*` input を渡していない caller でも**
parse 時 check で `startup_failure` になる。

判定: PR push 直後に `name: CI` workflow run が 1 秒で `startup_failure`
で完了 (job 0 件、log 0 行) するパターン。run UI 上では空の jobs 列が出る。

修正: caller workflow の `permissions:` (top-level または `jobs.ci.permissions:`)
に `id-token: write` を追加。`if:` で skip される予定でも省略不可
(= GitHub Actions は parse 時に required permissions を計算するため)。
