---
name: ci-workflows-map
generated-from: ci-workflows:cfdbf26d8a5ada4b768815578e41a2af27ed5629
paths: [.github/workflows/]
description: ippoan/ci-workflows (ippoan/ohishi-exp org 共通の GitHub Actions reusable workflow 集) の構造ナビゲーション。frontend-ci / go-ci / lib-ci / rust-ci / cloud-run-deploy / auto-merge / branch-protection / release-wave-handler / tag-release 等の reusable workflow を種別ごとに索引化し、caller 必須 permissions・startup_failure・auto-merge dual-step・coverage 100% gate 等の gotcha を 1 枚にまとめる。トリガー:「ci-workflows」「reusable workflow」「frontend-ci」「go-ci」「auto-merge」「branch-protection」「startup_failure」「cloud-run-deploy」「release-wave-handler」「secret-verify」「tag-release」等。
---

# ci-workflows-map — ippoan/ci-workflows 構造ナビゲーション

ippoan + ohishi-exp org 共通の **GitHub Actions reusable workflow 集**。各 consumer repo は
`.github/workflows/<name>.yml` から `uses: ippoan/ci-workflows/.github/workflows/<file>@main`
で 10〜20 行 caller を書いて呼ぶ。本体は `.github/workflows/` に集約 (本 repo 自身の CI は
`ci.yml` の actionlint)。

> ここは索引 (pointer)。各 workflow の input 全量 / 正確な job DAG は repo 側 (file header と
> CLAUDE.md) が正。frontmatter の `generated-from` が現在の repo tree-sha とズレたら
> session-start hook が再生成を促す → その時 tree-sha を更新する。

## 区画 (reusable workflow、種別ごと)

### 言語別 CI pipeline (caller の主役)

| workflow | 対象 | job 構成 / 備考 |
|---|---|---|
| `frontend-ci.yml` | Nuxt / Cloudflare Worker | typecheck/test/integration/deploy + 内蔵 disable→auto-merge dual-step。`project_type` で nuxt/worker 切替 |
| `go-ci.yml` | Go (Cloud Run) | `vet`/`test`/`build` + opt-in `secret-verify`。`coverage_100.toml` 検出で 100% gate。auto-merge は embed せず caller 側で組む |
| `lib-ci.yml` | `@ippoan/*` Node lib | `typecheck`/`lint`(auto)/`test`。lockfile 有無で `npm ci`/`install` fallback |
| `rust-ci.yml` | Rust | Rust CI |
| `android-ci.yml` | Android (Gradle) | Android CI |
| `shell-ci.yml` | shell script | Shell CI (shellcheck 等) |

### deploy / release

| workflow | 役割 |
|---|---|
| `cloud-run-deploy.yml` | Cloud Run へ AR remote-repo (pull-through cache) 経由 digest-pinned deploy |
| `tag-release.yml` | `workflow_dispatch` で `v{semver}` 正式タグ採番 (`TAG_RELEASE_PAT` 要) |
| `dev-tag-release.yml` | `push:main` で `{prefix}{N}` 開発タグ採番 (default `dev-N`) |
| `rust-binary-release.yml` | Rust binary を GitHub Release に (tag に `-` 含めば prerelease) |
| `lib-publish.yml` | `@ippoan/*` lib を GitHub Packages に publish (publish 前 typecheck+test gate) |
| `propagate-package.yml` | publish 後に consumer repo の依存を自動更新 |

### merge / branch protection / drift

| workflow | 役割 |
|---|---|
| `auto-merge.yml` | CI 完走後に `gh pr merge --auto` で enable (frontend/lib は内蔵、go/その他は caller から) |
| `branch-protection.yml` | Branches API で branch protection を **apply** (preset 適用) |
| `branch-protection-drift-check.yml` | 設定 drift を検知 |
| `check-dep-version.yml` | 依存バージョン整合チェック |
| `snapshot-check.yml` | snapshot 整合チェック |
| `cf-access-verify.yml` | Cloudflare Access 設定 verify |
| `secret-verify-gcp.yml` | GCP Secret Manager に必要 secret が存在するか verify (go-ci/frontend-ci に内製化済、単体 caller も維持) |

### release wave (ci-dashboard#137 連携)

| workflow | 役割 |
|---|---|
| `release-wave-handler.yml` | `repository_dispatch` (flip/rollback 等) を受け platform 別 deploy → ci-dashboard webhook に shared secret 付き POST。設定は `config/release-wave-targets.yaml` 集約。cloudrun flip は revision tag を渡さず release-wave-gcp が `latestReadyRevision` を flip (#248)。platform は cloudflare-workers / cloudrun / **github-release** (#179 — GitHub Releases 配布 repo。flip = `gh release edit <tag> --latest` で staged Release を昇格しフリート自動更新を開始。alc-gw が使用) |
| `validate-release-wave-targets.yml` | PR で `config/release-wave-targets.yaml` を編集した時に schema / 整合を検証 |

### 本 repo 自身用 (`-self` 接尾)

`ci.yml` (actionlint) / `auto-merge-self.yml` / `branch-protection-self.yml` — ci-workflows 自身の CI。

## その他の区画

| パス | 中身 |
|---|---|
| `config/release-wave-targets.yaml` | wave 参加 repo の platform / service / preview hostname。新規参加 = yaml entry 追加 + repo に caller 1 file |
| `scripts/cloud-run/deploy.sh` `extract_secrets.py` | cloud-run-deploy.yml が呼ぶ補助 script |
| `.github/actions/{pr-limit,report-backend-deploy,report-frontend-compat}/action.yml` | composite action (PR 数制限 / deploy・compat レポート) |

## entrypoint / 使い方

- 自身が実行 entrypoint を持つのは `-self` 系と `ci.yml` のみ。他は **caller repo から `workflow_call` で呼ばれる**のが起点。
- consumer は `/ci-init` skill か CLAUDE.md の caller テンプレートを使う。

## gotcha (CLAUDE.md / README 由来)

- **caller の `permissions` 不足 → `startup_failure`** (job 0 件・log 0 行で 1 秒終了、空 jobs 列)。GitHub は reusable が要求する権限を caller で許可してないとエラー文も出さず起動拒否する。
  - frontend-ci/lib-ci: 内蔵 auto-merge のため **top-level (Option A)** に `contents: write` + `pull-requests: write` (+ `packages: read`) 必須。
  - go-ci: auto-merge 無いので job-level (Option B) `contents: read` + `id-token: write` でも可。
  - **`secret-verify` を使わない caller でも `id-token: write` の declare 必須** (`if:` skip 予定でも parse 時の permissions check が走る、ci-workflows#38)。
- **auto-merge は dual-step**: CI 開始時に `disable-auto-merge` で強制 disable (緩い branch protection での誤 merge 防止) → 完走後に再 enable。go-ci.yml も 2026-05 以降 `disable-auto-merge` を内蔵し `pull-requests: write` を必須化 (breaking change)。
- **coverage 100% gate (go-ci)**: working_directory に `coverage_100.toml` があれば、registered file の (exclude_funcs 以外の) 全 function が 100% であることを fail-gate。section 名は relative path、`go tool cover -func` と suffix match。
- **`has_integration: true` にしたら `compat_backend_repo` 必須** (未設定だと API Integration job が loud fail。backend 不要なら `'none'` で opt-out)。
- `npm_publish_directory` は comma-separated で複数 package を 1 CI で publish (dev = `0.0.<PR>-dev.<SHA>` 共通、release = tag 共通の lock-step)。
- cross-org (ohishi-exp) では `secrets: inherit` が効かないので明示渡し。
- release-wave-handler は `client_payload.*` を **untrusted** 扱い (checkout ref に使う前に正規表現で ref injection 検証)。

## CCoW / CI から見た立ち位置

- ippoan の全 repo の CI/deploy/merge/release の **共通土台**。各 repo map の「CI は ci-workflows の <x>.yml」という記述はここを指す。
- 親 issue `ippoan/ci-dashboard#137` (Release Wave) の Phase 4 executor 配線元 (`release-wave-handler.yml` + `config/release-wave-targets.yaml`)。release-wave-gcp / rust-alc-api 等を束ねる。

## 関連 skill

- `ci-init` — consumer repo に `test.yml` caller を生成 (本 repo の reusable を使う)
- `auto-merge-401` / `gh-actions-phantom-permission` — auto-merge.yml / permission scope 由来の既知 CI fail のトラブルシュート
- `ci-cache-patterns` / `coverage-check` / `coverage-test-patterns` — Rust CI cache / coverage gate 補助
- `release-wave-gcp-map` / `secrets-inventory-gcp-map` — go-ci.yml + cloud-run-deploy.yml + secret-verify の consumer 実例
- `repo-map` / `cross-repo-symbol-index` — この per-repo map の運用方針 (generated-from 鮮度 hook)

## CLAUDE.md から移設 (2026-07-06)

## Reusable Workflows

### frontend-ci.yml

フロントエンド (Nuxt / Cloudflare Workers) 向け CI/CD パイプライン。

#### Caller 側の必須 permissions

**重要**: caller ワークフロー (`test.yml` 等) に以下の permissions を設定すること。
不足すると `startup_failure` になり、ジョブが起動せずエラーメッセージも出ない。

```yaml
permissions:
  contents: write        # auto-merge で必要
  pull-requests: write   # pr-limit, disable-auto-merge, auto-merge で必要
  packages: read         # npm_scope 使用時に必要
```

frontend-ci.yml は内蔵で **`disable-auto-merge` job** を持ち、CI 開始時に PR の auto-merge を強制 disable する (= branch protection が緩い repo での誤 merge 防止)。CI 完走後は内蔵の `auto-merge` job が再 enable する dual-step pattern。go-ci.yml も同じ `disable-auto-merge` job を内蔵 (= `pull-requests: write` 必須化、これは 2026-05 以降の breaking change)。

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
| `has_integration` | `false` | 統合テスト実行するか。**`true` にしたら `compat_backend_repo` が必須** — 未設定だと `API Integration` job が loud fail する (Release Wave compatibility edge の配線忘れ防止)。backend を相手にしない統合テストは `compat_backend_repo: 'none'` で opt-out |
| `has_deploy` | `true` | デプロイジョブ実行するか |
| `fast_fail` | `true` | test / typecheck / integration-test の fail 時に run 全体を cancel (赤 run の feedback 高速化、green run には無影響)。cancel は CI App token (要 Actions:write) で行い、無ければ warning のみで劣化 |
| `npm_scope` | `''` | GitHub Packages スコープ |
| `post_install_script` | `''` | install 後のスクリプト |
| `deploy_staging_script` | `''` | staging デプロイスクリプト |
| `staging_build_secret_name` | `''` | Deploy to staging に caller secret を 1 つ env として渡す opt-in (staging 専用、release には配線しない)。`staging_build_env_name` とペアで使う |
| `staging_build_env_name` | `''` | 上記 secret を export する環境変数名 (`[A-Za-z_][A-Za-z0-9_]*`) |
| `staging_no_traffic` | `false` | staging deploy を `deploy-staging-upload` (build/upload、needs 無しで test 群と並列) + `deploy-staging-flip` (`wrangler versions deploy <id>@100% --env staging`、test 群 + upload が全部 green になった瞬間に自動 flip、人の承認は挟まない) の2 job に分ける。`false` (default) は従来どおり単一 job で build 後に即 100% deploy (test 群完了を待ってから build するので upload/flip の分割自体が発生しない) |
| `deploy_release_script` | `''` | リリースデプロイスクリプト |
| `npm_publish_directory` | `''` | npm パッケージディレクトリ (設定時に publish 有効)。**comma-separated 対応** — `'packages/auth-client,packages/auth-client-worker'` のように複数 path 指定で全 package を 1 回の CI で publish。dev publish 版は全 package が `0.0.<PR>-dev.<SHA>` 共通、release tag publish は tag バージョン共通 (lock-step、独立 versioning 不可) |
| `npm_publish_name` | `''` | npm パッケージ名 (propagation 用、例: `@ippoan/auth-client`) |
| `npm_publish_propagate_repos` | `''` | publish 後に自動更新する対象リポジトリ (カンマ区切り) |
| `npm_publish_propagate_dirs` | `''` | 対象リポジトリの working directory (カンマ区切り) |

**propagate は変更ゲート付き** (`propagate-gate` job、Refs #177): release tag push 時に
「npm_publish_name の package dir が **直前の release tag から変更されている時だけ**」
propagate を実行する。monorepo lock-step publish (tag ごとに全 package が publish される)
でも、対象 package 未変更のリリースで consumer 9 repo に bump PR が乱発されない。
バージョンは gate が tag から `^X.Y.Z` を確定して渡す (npm view 解決を省く)。
認証は auto-merge と同じ **GitHub App (CI_APP_ID / CI_APP_PRIVATE_KEY org secret) を優先**、
`PROPAGATE_PAT` は後方互換フォールバック (詳細は propagate-package.yml のヘッダコメント)。

### go-ci.yml

Go 向け CI pipeline。`vet` / `test` / `build` の 3 job + (opt-in) `secret-verify` で構成される。status check 名は caller の job id (例: `ci`) + ' / ' + reusable job name で、`ci / vet`, `ci / test`, `ci / build`, `ci / secret-verify` の 4 つに pin される (auth-worker の `ippoan-go-default` branch-protection preset 参照)。

#### Coverage 100% gate (opt-in、auto-detect)

caller repo の **`coverage_100.toml`** が working_directory に存在すれば、`test` job が `go test ... -coverprofile=cover.out` を生成し、`go tool cover -func` 出力と toml を突合して **registered file の (exclude_funcs 以外の) 全 function が 100% カバレッジ** であることを CI で gate する。1 つでも違反すれば fail (warning ではない)。

`coverage_100.toml` の最小例:

```toml
[main.go]
# log.Fatal を含む env validation / ListenAndServe bootstrap を逃がす
exclude_funcs = ["main", "mustEnv"]

[cloudrun.go]
exclude_funcs = ["newLiveCloudRun"]
```

- section 名 (`[<file>]`) は **working_directory からの相対パス** で書く (例: `main.go` / `sub/foo.go`)。`go tool cover -func` の module-fullpath とは suffix match で照合される
- `exclude_funcs` は 100% 要求から除外する function 名のリスト。bootstrap / ADC 取得 / `log.Fatal` 等の untestable な path 用
- ファイルが存在しなければ既存挙動 (plain `go test`) — backward compat
- gate は `staging = 本番運用` repo (例: `release-wave-gcp`、`secrets-inventory-gcp`) で導入する想定。registered file の coverage 退化は staging 反映 (= 本番反映) ブロック扱い

#### Caller テンプレート (Go on Cloud Run、secret-verify あり)

```yaml
name: CI

on:
  pull_request:
    branches: [main]

# go-ci.yml は内部に `disable-auto-merge` job を持ち `pull-requests: write`
# を要求する。secret-verify を併用する場合は `id-token: write` も追加。
permissions:
  contents: read
  pull-requests: write
  id-token: write

jobs:
  ci:
    uses: ippoan/ci-workflows/.github/workflows/go-ci.yml@main
    with:
      gcp_secret_verify_project: cloudsql-sv
      gcp_secret_verify_provider: ${{ vars.GCP_WIF_PROVIDER }}
      gcp_secret_verify_sa: ${{ vars.GCP_WIF_SERVICE_ACCOUNT_STAGING }}
```

3 つの verify input を全部空にすると `secret-verify` job は skip され、`vet/test/build` だけが status check に出る (= 既存 caller への backward compat)。

> **caller 側で CI 完走後に auto-merge を enable したい場合**: caller workflow に `auto-merge` job を追加し `ippoan/ci-workflows/.github/workflows/auto-merge.yml@main` を呼ぶ (= frontend-ci.yml と同じ pattern を caller で組み立てる)。go-ci.yml には `auto-merge` job は embed されていない (= build / deploy job は caller 固有のため、caller の `needs:` から組む方が柔軟)。実例: `ippoan/secrets-inventory-gcp` の `ci.yml`。

### lib-ci.yml

Node.js library (e.g. `@ippoan/mcp-cf-workers`) 向け CI pipeline。`typecheck` / `lint` (auto-detect) / `test` の 3 job で構成され、status check 名は caller の job id (例: `ci`) + ` / ` + reusable job name で `ci / typecheck` / `ci / lint` / `ci / test`。auth-worker の `ippoan-lib-default` branch-protection preset は `ci / typecheck` + `ci / test` を required にピン留めしている (lint は auto-skip され得るため required から除外)。

lockfile policy: `package-lock.json` が commit されていれば `npm ci`、無ければ `npm install --no-audit --no-fund` で auto-fallback。 brand-new repo (lockfile 未 commit) でも CI が green になる。

#### Caller permissions (Option A 推奨)

frontend-ci.yml と同じく `disable-auto-merge` (CI 開始時) + `auto-merge` (CI 完走後) を内蔵する dual-step pattern なので、caller 側で `contents: write` + `pull-requests: write` を declare する必要がある:

```yaml
# Option A: top-level (Recommended)
permissions:
  contents: write
  pull-requests: write
  packages: read       # @ippoan/* GitHub Packages dep install
```

#### Caller テンプレート (Node lib)

```yaml
name: ci
on:
  pull_request: {}
  push:
    branches: [main]

permissions:
  contents: write
  pull-requests: write
  packages: read

jobs:
  ci:
    uses: ippoan/ci-workflows/.github/workflows/lib-ci.yml@main
    with:
      node_version: '20'
      # run_lint: 'true'   # eslint config が必須化された後で
      # package_path: 'packages/foo'  # monorepo の subpath
    secrets: inherit
```

#### 主な inputs

| input | デフォルト | 説明 |
|-------|-----------|------|
| `node_version` | `'20'` | actions/setup-node の node-version |
| `package_path` | `'.'` | npm コマンドの作業 directory |
| `run_lint` | `'auto'` | `auto` (eslint config / lint script を検出) \| `true` \| `false` |
| `coverage` | `true` | `test:coverage` script があれば npm test の代わりに実行 |

### lib-publish.yml

`@ippoan/*` 系 Node.js library を GitHub Packages に publish する reusable。tag push (`v*`) または release published で caller から呼ぶ。 publish 前に `npm run typecheck` + `npm test` を gate として走らせる (`run_tests: false` で skip 可、緊急 republish 用)。

```yaml
# Caller (.github/workflows/publish.yml)
name: publish
on:
  push:
    tags: ['v*']
jobs:
  publish:
    permissions:
      contents: read
      packages: write
    uses: ippoan/ci-workflows/.github/workflows/lib-publish.yml@main
    with:
      node_version: '20'
    secrets:
      NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

`NODE_AUTH_TOKEN` は同 org 内 publish なら `${{ secrets.GITHUB_TOKEN }}` で足りる。 npmjs.org publish に切り替える場合は granular npm access token を caller secret として渡す + `registry_url: 'https://registry.npmjs.org'` も合わせて override。

### rust-dep-check.yml

Rust の依存グラフ監視 reusable。`dep-check` 1 job で以下を実行する
(Refs ippoan/rust-alc-api の `docs/ci-performance.md`「依存グラフ削減」):

- **cargo-deny `check bans`** — 同一 crate の複数バージョン共存を警告/失敗。
  設定は caller repo の `deny.toml` (`[bans] multiple-versions = "warn"` 等) が
  SoT。**deny.toml が無い repo は notice のみで skip** (段階導入可能)
- **cargo-machete** — 未使用依存の検出 (text ベース・コンパイル不要で数秒)。
  `machete_enforce: 'warn'` (default) は `::warning::` のみで job は緑、
  `'fail'` で job fail。proc-macro / build script 経由のみの利用は false
  positive になるため caller の `Cargo.toml` に
  `[package.metadata.cargo-machete] ignored = ["crate-name"]` で除外する

```yaml
# Caller (bespoke ci.yml の 1 job として)
  dep-check:
    uses: ippoan/ci-workflows/.github/workflows/rust-dep-check.yml@main
    # with:
    #   working_directory: '.'
    #   machete_enforce: 'warn'   # warn | fail
```

実例: `ippoan/rust-alc-api` の `ci.yml` (rust-s3 の旧 hyper スタック二重等、
既知重複の解消追跡に使用)。

### auto-merge.yml

CI 完走後に `gh pr merge --auto --squash` を queue する reusable。frontend-ci.yml / lib-ci.yml には embed 済み、go-ci.yml caller や bespoke ci.yml の repo は caller 側で `needs:` を組んで呼ぶ。

#### caller-composed の鉄則: deploy 系 job を `needs` に含める

auto-merge job が deploy (staging cutover) の完了を待たずに merge を queue すると、merge → branch 削除で**走行中の deploy が cancel され、deploy 失敗が無音化する** (ippoan/rust-alc-api#391 で 2 回実害、同#405)。caller 側で auto-merge.yml を直接呼ぶ場合は deploy 系 job を必ず `needs` に含める:

```yaml
auto-merge:
  needs: [ci, build-image, deploy-staging]
  if: >-
    always() && github.event_name == 'pull_request' &&
    needs.ci.result == 'success' &&
    (needs.deploy-staging.result == 'success' || needs.deploy-staging.result == 'skipped')
  uses: ippoan/ci-workflows/.github/workflows/auto-merge.yml@main
  secrets: inherit
```

#### クロス org caller は `secrets: inherit` 不可 (明示渡し必須)

**`secrets: inherit` は reusable が caller と同一 org / enterprise にある時しか
secret を渡さない。** この reusable は `ippoan/ci-workflows` にあるので、
**別 org の caller (例: `ohishi-exp/*`) が `secrets: inherit` を使うと
`CI_APP_ID` / `CI_APP_PRIVATE_KEY` が空になり** `missing GitHub App
credentials` で fail する (= 何度も踏んだ罠。`Require App token` step の
`::error` にも明記済み)。クロス org caller は named secret を明示的に渡す:

```yaml
auto-merge:
  uses: ippoan/ci-workflows/.github/workflows/auto-merge.yml@main
  secrets:
    CI_APP_ID: ${{ secrets.CI_APP_ID }}
    CI_APP_PRIVATE_KEY: ${{ secrets.CI_APP_PRIVATE_KEY }}
```

同 org (ippoan) の caller は従来どおり `secrets: inherit` で良い。CI_APP_*
は caller org に org (or repo) secret として存在し、当該 repo に visible で
ある必要がある (= App を org に install + `Organization permissions →
Secrets: Read and write`、secret は `secrets-inventory` MCP の `sync_from_gcp`
`gh_org` で GCP から投入できる。Refs ippoan/secrets-inventory-gcp#51)。

#### deploy gate 静的検査 (配線漏れの loud fail)

`needs:` は caller の DAG なので reusable 側から配線はできないが、**配線漏れの検出は auto-merge.yml に内蔵されている** (`verify_deploy_gate` input, default `true`)。job 実行時に caller workflow YAML を checkout して静的検査し、job id / name に `deploy` を含む job が auto-merge job の needs (推移的閉包) に含まれていなければ `::error` + fail する。

- **tag push 限定の deploy job は自動除外** (`if` に `refs/tags` を含み `pull_request` を含まない job は PR run で走らず merge と並走しないため)
- 誤検知する job は `deploy_gate_ignore: 'job-id1,job-id2'` (comma 区切り) で除外
- **nested 呼び出し (frontend-ci.yml / lib-ci.yml 経由) は検査 skip** — embedded pipeline 側で `deploy-staging` を needs 済み。top-level に独自 deploy job がある場合は warning のみ (needs では gate 不能 → branch protection required checks で守る)
- 別 workflow file の deploy job は対象外 (needs で gate しようがない)
- `verify_deploy_gate: false` で検査ごと無効化可


### Secret verify を frontend-ci.yml / go-ci.yml の中に取り込む経緯

旧 pattern: 各 caller repo が `.github/workflows/secret-verify.yml` を別 file で持ち、`ippoan/ci-workflows/.github/workflows/secret-verify-gcp.yml@main` を直接呼んでいた。問題:

1. caller 毎の boilerplate (40 行前後) が必要
2. status check の DAG が `ci / *` と `verify / *` の 2 並列 chain になり、branch protection の required-check 構成が複雑化
3. typecheck / build がまだ赤い commit で Secret Manager を叩いて gcloud quota を浪費

これを 2026-05 の `feat(ci): bake secret-verify into go-ci/frontend-ci` (PR #XX) で reusable 内に **直列に内製化**。caller は `gcp_secret_verify_*` 3 input を渡すだけで `ci / secret-verify` 段が動く。`secret-verify-gcp.yml` 単体 caller も維持されるので柔軟な構成は残せる。

> **2026-07 更新**: frontend-ci.yml の `secret-verify` は **test/typecheck/integration と並列**に変更した (needs を撤去)。直列だと毎 PR ~30s の wall time を deploy-staging / auto-merge の手前に足していたため。上記 3. (赤 commit で Secret Manager を叩く quota 浪費) は verify が数 call であることから許容した。「deploy 前に test と secret-verify の両方が green」というガードは deploy-staging / auto-merge job の needs + result 条件が引き続き担保する。go-ci.yml の secret-verify は従来どおり (caller が DAG を組むため)。
>
> 同時に `test` / `typecheck` / `integration-test` の `needs: [pr-limit]` も撤去した。`pr-limit` (同一 author の他 PR の merge conflict チェック、今回の diff とは無関係な metadata check) が test 群を待たせる理由が無く、deploy-staging / auto-merge の `needs` にも `pr-limit` は含まれていない (元々 merge gate ではなかった) ため、純粋な視覚上の直列 (~7s) を解消して全 job を run 開始と同時に並列実行するようにした。
>
> **さらに staging deploy に `staging_no_traffic` (default `false`、opt-in) を追加**し、`true` の時だけ build/upload と flip を別 job に分ける。従来は `deploy-staging` が test 群の完了を待ってから build していたため、build (nuxt で ~30〜60s) が並列化の恩恵を受けられずクリティカルパスに残っていた。
>
> **`needs:` は input で条件分岐できない (job scheduling は静的 DAG)** ため、`false`/`true` を同一 job の分岐だけで両立させることはできない。3 job constant で持つ:
> - `deploy-staging-immediate` — `false` (default) 専用。**従来の `deploy-staging` と全く同じ** (needs: test 群、test 完了を待ってから build して即 100% deploy)。既存 20+ caller はこの job がそのまま動くので無停止・no-op
> - `deploy-staging-upload` — `true` 専用。needs 無し、run 開始と同時に test 群と並列実行。`wrangler deploy` → `wrangler versions upload` (no-traffic、release_no_traffic と同じ置換) で build+upload だけ済ませる (traffic は動かないので test 結果を待たずに実行して安全)
> - `deploy-staging-flip` — `true` 専用。needs: upload + test 群全部。全部 green になった瞬間に `wrangler versions deploy <id>@100% --env staging --yes` で自動 flip する。**人の承認 (GitHub Environment required reviewer 等) は挟まない** — gate は既存の test/typecheck/... の green 条件のみ
>
> `true` の時はクリティカルパスが `test群完了 + build時間` (直列) から `max(test群, build)+flip時間` (並列) に短縮される。`auto-merge` の `needs` はこの3 job 全部を含み、非活性側は `skipped` として扱う。
>
> **2026-07 の実装ミスと即時修正の記録**: 初版 PR (#159) では `deploy-staging-upload` 1 job だけで `false`/`true` 両方を賄おうとし、**`needs` を丸ごと削除した結果 `false` (default = 全 caller) でも test 完了を待たずに即 100% deploy してしまう重大な回帰**が発生した (自動セキュリティレビューが検出、merge から数分で発覚・#160 で修正)。「build/upload 自体は無害」という判断は `staging_no_traffic=true` の no-traffic upload に限った話で、`false` の実体 (即 `wrangler deploy`) には適用できないことを見落としていた。同種の「安全な最適化のつもりで gate を丸ごと外す」変更をする時は、**gate 対象のコマンドが input 次第で変わる場合、job を分けずに `if:` だけで済まそうとしない**こと。

### release-wave-handler.yml

ippoan/ci-dashboard#137 Phase 4b で導入した reusable workflow。各 release-wave 参加 repo が `.github/workflows/release-wave.yml` という 10 行 caller で呼ぶ。`repository_dispatch` で ci-dashboard が送る 3 event (`release-wave-stage` / `-flip` / `-rollback`) を受けて platform 別の deploy 操作を行い、結果を `https://ci-dashboard.ippoan.org/webhooks/release-wave/*` に shared secret (`RELEASE_WAVE_WEBHOOK_SECRET`) 付き curl で POST する。

設定は `config/release-wave-targets.yaml` に集約。新規 repo を wave に参加させる際は **この yaml に entry 追加 + repo に caller 1 file 追加**の 2 step だけ。

#### Caller テンプレート

```yaml
# <repo>/.github/workflows/release-wave.yml
name: Release Wave

on:
  repository_dispatch:
    types:
      - release-wave-stage
      - release-wave-flip
      - release-wave-rollback
      - release-wave-traffic-rollback   # frontend 単独 rollback (cloudflare-workers)
      - release-wave-backend-rollback    # backend 単独 rollback (cloudrun)

permissions:
  contents: write     # tag push
  id-token: write     # GCP WIF (cloudrun の場合)

jobs:
  handler:
    uses: ippoan/ci-workflows/.github/workflows/release-wave-handler.yml@main
    secrets: inherit
```

#### Caller 側に必要な secrets

- `RELEASE_WAVE_WEBHOOK_SECRET` (org secret、ci-dashboard の Secrets Store と同値)
- `CLOUDFLARE_API_TOKEN` (cloudflare-workers platform の場合)
- `RELEASE_WAVE_GCP_API_KEY` (cloudrun platform、release-wave-gcp Cloud Run service の認証 key)

#### Cloud Run path (Phase 4c)

cloudrun platform の repo (e.g. `ippoan/rust-alc-api`) で:

- **Stage**: tag push のみ実施。実 deploy は repo の `deploy.yml` に任せる
  (= `--no-traffic --tag pending-<sanitized>` オプション付きで revision を
  落とす必要あり、Phase 5 で各 repo deploy.yml に追加する)。
  reusable は `release-wave-gcp /cloudrun/stage-check` を 30s 間隔で
  20 分 poll し、`terminalCondition.state == "CONDITION_SUCCEEDED"` を待つ。
- **Flip**: `services[]` 全てに対して matrix で並列に
  `release-wave-gcp /cloudrun/flip-traffic` を叩く。`to_revision_tag` は
  `pending-<sanitized target_tag>` を生成 (lowercase + dot → hyphen)。
- **Rollback**: `services[]` 並列で `/cloudrun/rollback`。戻し先 revision
  は `client_payload.rollback_target[<service>]` から取得 (ci-dashboard
  側 dispatcher 実装時に各 service 別の flip_from_revision を載せる)。
- **Backend rollback** (`release-wave-backend-rollback`, Refs ippoan/ci-dashboard#197):
  /release-wave の「Backend rollback」ボタンから任意の過去 revision へ即 100%。
  戻し先は `client_payload.rollback_target[<service>]`、無ければ単一値
  `client_payload.rollback_revision` に fallback。wave 非依存 (callback 無し)。

frontend (cloudflare-workers) には `release-wave-traffic-rollback`
(Refs ippoan/ci-dashboard#196) が対応し、`previewed_version_id` を
`wrangler versions deploy <id>@100%` で即 100% に戻す。

reusable input `release_wave_gcp_base_url` で release-wave-gcp の URL を
上書き可能 (default は staging)。

#### Security notes

`github.event.client_payload.*` (= ci-dashboard から送られる任意 JSON) は **untrusted** として扱い、`wave_id` / `target_tag` / `head_sha` を `actions/checkout` の `ref:` に使う前に正規表現で形式検証する。ref injection 防止は本 reusable の dispatch job 内で済ませてある。

### catalog-extract.yml

`ippoan/cap-catalog` 連携の reusable (Refs ippoan/cap-catalog#3)。caller repo のソースコードを言語別に解析して、cap-catalog の `symbols` テーブルに投入できる正規化 JSONL を artifact として出力する。

#### dispatcher (本 reusable) と extractor (cap-catalog#4/#5/#6) の分離

本 file は **dispatcher のみ** — 入力検証 / cache setup / artifact 検証・upload。各言語の実体 (rustdoc JSON → JSONL 変換等) は `ippoan/cap-catalog#4/#5/#6` で順次追加する。現状は extractor 未実装で empty JSONL を upload する。

#### Cache 設計 (rust-flickr#28-#32 / rust-alc-api#427 pattern)

`rust-alc-api` で確立した「shared-key 統合 + 非対称 save-if」を本 reusable にも持ち込む:

- **shared-key**: default `<caller-repo>-catalog-<language>`。caller の `shared_key` input で override 可。release reusable と key 衝突しないよう suffix で分離。
- **`save-if: github.event_name == 'push' && refs/heads/main` のみ** (= 非対称 save-if)。PR run は restore のみ、中途半端な target/ が main の cache を上書きしない。
- **Rust**: `Swatinem/rust-cache@v2` (target/) + `mozilla-actions/sccache-action@v0.0.9` (compiler input) の 2 段。`cache-targets: false` で rust-cache と sccache の責務を分ける。
- **TS/JS**: **cache 無し** (`actions/setup-node@v4` を cache 指定なしで実行)。extractor 未実装で npm install しないため、cache を持たせると working_directory/workflow 名を含まない npm cache key (lockfile hash のみ) が同 repo の test.yml / preview-deploy.yml と衝突し、ほぼ空の cache で汚染してしまっていた (実害: ohishi-exp/nuxt-dtako-admin#134)。extractor が npm install するようになったら復活を検討する。
- **Go**: `actions/setup-go@v5` 内蔵 `cache: true` (`cache-dependency-path` は `<working_directory>/go.sum` 固定)。

#### Caller テンプレート

```yaml
# <repo>/.github/workflows/cap-catalog-extract.yml
name: cap-catalog extract
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
permissions:
  contents: read
jobs:
  extract:
    uses: ippoan/ci-workflows/.github/workflows/catalog-extract.yml@main
    with:
      language: rust
      # working_directory: '.'
      # shared_key: ''             # default は <repo>-catalog-<lang>
      # rust_toolchain: 'nightly'  # rustdoc --output-format json は nightly 必須
```

#### 主な inputs

| input | デフォルト | 説明 |
|---|---|---|
| `language` | (required) | `rust` \| `ts` \| `js` \| `go` の 4 値、白リスト検証 |
| `working_directory` | `.` | source root (extractor の cwd) |
| `output_artifact_name` | `catalog-extract` | upload する artifact 名 (cap-catalog builder が pull する key) |
| `artifact_retention_days` | `7` | builder の pull window。長すぎると stale 取り込み risk |
| `shared_key` | (auto: `<repo>-catalog-<language>`) | rust-cache の `shared-key`。複数の language を同 repo で扱う時に `language` 別 cache に分離する |
| `rust_toolchain` | `nightly` | `dtolnay/rust-toolchain@master` の channel |
| `node_version` | `'20'` | `actions/setup-node` の `node-version` |
| `go_version` | `'1.24'` | `actions/setup-go` の `go-version` |

#### JSONL schema (extractor が emit する 1 行 contract)

```json
{
  "repo": "ippoan/auth-worker",
  "language": "rust",
  "kind": "fn",
  "name": "createAuthFetch",
  "fq_path": "auth-client::createAuthFetch",
  "signature": "(opts: Opts) => Fetch",
  "doc": "Wraps fetch with auth-worker JWT refresh.",
  "file": "packages/auth-client/src/fetch.ts",
  "line": 42,
  "commit_sha": "abc123",
  "features": ["auth-fetch"]
}
```

`repo / language / kind / name / fq_path` は **required**。validate step で必須 field 不在 / 不正 language を loud fail させる (= extractor バグの早期検出)。

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

### skills-check.yml

`<repo>-map` skill が code に追従しているかを **PR diff** で検査する reusable (Refs ippoan/claude-skills#58 / ippoan/claude-hooks#18 / ci-workflows#118)。従来 claude-hooks の `session-start-skill-coverage.sh` (SessionStart 警告) が担っていた stale 判定は CCoW に無視され機能していなかったため、判定を CI に移して PR 上で機械的に warn/fail させる。

#### Job: map-check

caller repo の `.claude/skills/*/SKILL.md` のうち frontmatter に `generated-from: <repo>:<commit-sha>` + `paths: [src/, proto/]` を持つ map を読み、PR の変更ファイルと `paths` を突き合わせる。**`paths` 下に変更があるのに その map (SKILL.md) が同 PR で更新されていない** 場合に warn (= map 更新漏れ)。

- map が 1 つも無い repo は「uncovered」を 1 行通知するだけ (fail しない)
- 旧形式 (`generated-from` が tree-sha のみ / `paths` 無し、複数 repo の横断 map) は **移行期間中スキップ** (claude-hooks#18 Q1)
- `enforce` input: `warn` (default、`::warning::` + Step Summary のみ、CI は緑) / `fail` (更新漏れで job fail、pilot 用。PR3 で rust-flickr → rust-alc-api の順に切替予定)

#### Caller テンプレート

```yaml
name: skills-check
on:
  pull_request:
    types: [opened, synchronize, reopened]
permissions:
  contents: read
jobs:
  skills-check:
    uses: ippoan/ci-workflows/.github/workflows/skills-check.yml@main
    # with:
    #   enforce: warn          # warn (default) | fail
    #   skills_dir: .claude/skills
```

#### Job 2: dependency-check (dependency_check=true、default)

PR で `Cargo.toml` / `package.json` に**新規追加された依存**を、`standards_repo`（default `ippoan/claude-skills`）の `knowledge/standards/libs/` を sparse checkout して突き合わせる。

- **未掲載** → warn（deny しない。実験は止めず、未掲載のまま定着することだけ防ぐ）
- **deprecated 掲載**の依存を新規追加 → `::error`、`enforce=fail` なら job fail

base/head の manifest を JSON / TOML として parse し依存 set の差分を取るため、`scripts` 変更等の false-positive は出ない（Python stdlib: `json` + `tomllib`）。`dependency_check: false` で無効化、`standards_repo` / `standards_ref` で参照先を変更可。

> dependency-check は `pull_request` event でのみ走る（base sha が要るため）。standards_repo が private な場合は caller の checkout token に read 権限が要る（public なら不要）。

#### Job 3: caller-perms-check（id-token silent trap の loud-fail）

`frontend-ci.yml` / `go-ci.yml` は内蔵 secret-verify が **parse 時に `id-token: write` を要求**する。caller がこれを未宣言だと **無音の startup_failure**（job も check も出ず、PR が必須 check 未充足で永久に詰まる）になる — これが最も気付きにくい silent trap（旧 caller / dormant repo で頻発）。

startup_failure 自体は当該 workflow の job 起動前なので捕捉できないが、skills-check は **id-token 不要で別 run として必ず走る**ため、ここで caller repo の `.github/workflows/*.yml` を静的検査し、frontend-ci/go-ci を呼ぶのに `id-token: write` が無い caller を見つけたら **`::error` + job fail で loud に通知**する。これにより「無音で詰まる」が「明確なエラーで止まる」に変わる。

修正は caller の `permissions:`（top-level か `jobs.<id>`）に `id-token: write` を 1 行足すだけ。

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
