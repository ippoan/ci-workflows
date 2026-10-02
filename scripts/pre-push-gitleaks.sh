#!/usr/bin/env bash
# git pre-push hook: push される commit 範囲を gitleaks でスキャンし、秘密情報が
# あれば push を拒否する。標準の pre-push stdin (local_ref local_sha remote_ref
# remote_sha を 1 行ずつ) を読む。
#
# auto-merge.yml の `Secret Scan (gitleaks)` と同じ config/gitleaks.toml を使う。
# あちらは push の後 (public repo では公開済み) にしか走らないので、公開前に
# 止められるのはこの hook だけ。
#
# 配線 (マシンごと。global の core.hooksPath 配下の pre-push から):
#   printf '%s\n' "$input" | <ci-workflows の checkout>/scripts/pre-push-gitleaks.sh "$@" || exit $?
#
# 終了コード:
#   0  検出なし / gitleaks 未導入 (stderr に 1 行出して続行)
#   1  検出あり、またはスキャン自体が失敗 (どちらかは文言で区別する)
#
# gitleaks は auto-merge.yml / gitleaks.yml の GITLEAKS_VERSION に揃えること。
# 誤検知の除外は CI と同じ: 行内 `gitleaks:allow` か repo 直下の .gitleaksignore。
set -u

CIW="${CI_WORKFLOWS_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
CONFIG="$CIW/config/gitleaks.toml"
GITLEAKS="${GITLEAKS_BIN:-gitleaks}"

input=$(cat)
if ! command -v "$GITLEAKS" >/dev/null 2>&1; then
  echo "⚠ [gitleaks] 未導入のため push 前の秘密情報スキャンを飛ばしました (push は続行)" >&2
  exit 0
fi
if [ ! -f "$CONFIG" ]; then
  echo "✗ [gitleaks] config が見つかりません: $CONFIG (検出ではありません)" >&2
  exit 1
fi

top=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$top" || exit 0

Z=0000000000000000000000000000000000000000
report=$(mktemp)
trap 'rm -f "$report"' EXIT
failed=0
while read -r _local_ref local_sha _remote_ref remote_sha; do
  [ -n "${local_sha:-}" ] || continue
  [ "$local_sha" = "$Z" ] && continue # branch deletion
  # 既存 branch は remote の先端からの差分。新規 branch と、remote の先端を
  # 手元に持っていない場合は「どの remote にもまだ無い commit」を見る。
  if [ "$remote_sha" != "$Z" ] && git cat-file -e "${remote_sha}^{commit}" 2>/dev/null; then
    log_opts="${remote_sha}..${local_sha}"
  else
    log_opts="${local_sha} --not --remotes"
  fi
  rc=0
  out=$("$GITLEAKS" git . --log-opts="$log_opts" -c "$CONFIG" \
    --redact=100 --no-banner --exit-code 1 \
    --report-format json -r "$report" 2>&1) || rc=$?
  [ "$rc" -eq 0 ] && continue
  failed=1
  if [ "$rc" -ne 1 ] || [ ! -s "$report" ]; then
    {
      echo "✗ [gitleaks] スキャン自体が失敗しました (exit $rc)。検出ではありません:"
      printf '%s\n' "$out" | tail -5 | sed 's/^/    /'
    } >&2
    continue
  fi
  {
    echo "✗ [gitleaks] push する commit に秘密情報らしき値があります — push を止めました:"
    # 値は --redact で伏せてある。場所とルールだけを出す。
    jq -r '.[] | "  - \(.File):\(.StartLine) (\(.RuleID)) commit \(.Commit[0:7])  fingerprint \(.Fingerprint)"' "$report"
    echo "  まだ公開されていません。本物なら値を消した commit に作り直してから push してください"
    echo "  (commit を上に積むだけでは履歴に残ります)。"
    echo "  誤検知なら該当行に 'gitleaks:allow' を付けるか、fingerprint を repo 直下の"
    echo "  .gitleaksignore に 1 行ずつ足してください。"
  } >&2
done <<<"$input"
exit "$failed"
