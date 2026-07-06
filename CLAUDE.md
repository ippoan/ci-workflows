# ci-workflows

ippoan / ohishi-exp org 共通の **GitHub Actions reusable workflows** 集。本体は
`.github/workflows/`、consumer は `uses: ippoan/ci-workflows/.github/workflows/<file>@main`
で 10〜20 行 caller を書いて呼ぶ。本 repo 自身の CI は `ci.yml` (actionlint)。

各 reusable の input 全量・caller テンプレート・job DAG・導入経緯・トラブルシュートは
**`ci-workflows-map` skill** (`.claude/skills/ci-workflows-map/SKILL.md`) を参照。

## 不変則 (必ず守る — map は lazy load なので規範はここに残す)

- **caller の `permissions` 不足 → `startup_failure`** (job 0 件・log 0 行で 1 秒終了、
  エラー文も出ない)。frontend-ci / lib-ci は内蔵 auto-merge のため top-level に
  `contents: write` + `pull-requests: write` (+ npm_scope 時 `packages: read`) 必須。
- **frontend-ci / go-ci を呼ぶ caller は `id-token: write` を declare 必須**。
  `gcp_secret_verify_*` を渡さない・`if:` skip 予定でも省略不可 (parse 時の permissions
  check が走るため、未宣言 = 無音 startup_failure)。
- **auto-merge は dual-step** (CI 開始時に disable → 完走後に re-enable)。caller で
  auto-merge.yml を直接呼ぶ場合は **deploy 系 job を必ず `needs` に含める**
  (merge → branch 削除で走行中 deploy が無音 cancel される)。
- **cross-org (ohishi-exp) caller は `secrets: inherit` 不可** — `CI_APP_ID` /
  `CI_APP_PRIVATE_KEY` を named secret で明示渡し。
- **`has_integration: true` にしたら `compat_backend_repo` 必須** (未設定は loud fail、
  backend 不要なら `'none'` で opt-out)。
- **release-wave-handler の `client_payload.*` は untrusted** — checkout ref に使う前に
  正規表現で形式検証する (ref injection 防止)。
- **coverage 100% gate (go-ci)**: `coverage_100.toml` があれば registered file の
  (exclude_funcs 以外) 全 function が 100% であることを fail-gate。
- **「安全な最適化のつもりで gate を丸ごと外す」変更をしない** (input 次第で gate 対象
  コマンドが変わる時は `if:` だけで済まさず job を分ける。staging_no_traffic #159 の回帰教訓)。
