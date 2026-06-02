#!/usr/bin/env node
// cross-repo symbol index generator — ctags JSON → ingest payload → POST。
//
// caller repo の CI が test 後 (依存ビルド済み) に universal-ctags で symbol を
// 抽出 (NDJSON)、このスクリプトが ci-dashboard の D1 schema 形に整形して
// POST /internal/symbol-index へ投入する。
//
// 設計: ippoan/claude-skills の cross-repo-symbol-index skill。
// 投入先 schema / endpoint: ippoan/ci-dashboard src/symbol-index.ts。
//
// v1 engine は universal-ctags (toolchain 不要・多言語・start/end 行が取れる)。
// 意味的な参照グラフ (links) が要るようになったら LSP に格上げする。
//
// env:
//   SYMBOL_TAGS_FILE   ctags --output-format=json の NDJSON ファイル (default tags.json)
//   SYMBOL_REPO        index に記録する短い repo 名 (e.g. rust-alc-api)
//   SYMBOL_SRC_HASH    鮮度キー (git rev-parse HEAD:. 等)
//   SYMBOL_INGEST_URL  ci-dashboard の ingest endpoint
//   SYMBOL_INGEST_SECRET  Bearer secret
//   SYMBOL_DRY_RUN     "1" なら POST せず payload を stdout に出すだけ
//
// import せず単体実行可能。mapping (tagsToSymbols/normalizeKind) は test 用に export。

import { readFileSync } from "node:fs";

// ctags の kind 名 → search_symbols の kind 語彙に正規化。未知は raw を通す。
const KIND_MAP = {
  function: "function", func: "function", method: "function", subroutine: "function",
  class: "class",
  struct: "struct",
  interface: "interface",
  trait: "trait",
  enum: "enum", enumerator: "enum",
  typedef: "type", type: "type", alias: "type",
  module: "mod", namespace: "mod", package: "mod",
};

export function normalizeKind(raw) {
  if (typeof raw !== "string") return "symbol";
  return KIND_MAP[raw.toLowerCase()] ?? raw.toLowerCase();
}

/**
 * ctags --output-format=json の NDJSON を symbol 配列へ。
 * 各 tag: { _type:"tag", name, path, line, end?, kind, signature? }
 * `_type !== "tag"` の pseudo-tag や line 欠落は捨てる。
 */
export function tagsToSymbols(ndjson) {
  const out = [];
  for (const line of ndjson.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    let t;
    try {
      t = JSON.parse(trimmed);
    } catch {
      continue;
    }
    if (t._type !== "tag") continue;
    if (typeof t.name !== "string" || typeof t.path !== "string") continue;
    const start = Number(t.line);
    if (!Number.isInteger(start)) continue;
    const end = Number.isInteger(Number(t.end)) ? Number(t.end) : start;
    out.push({
      name: t.name,
      kind: normalizeKind(t.kind),
      file_path: t.path.replace(/^\.\//, ""),
      start_line: start,
      end_line: end,
      signature: typeof t.signature === "string" ? t.signature : null,
    });
  }
  return out;
}

async function main() {
  const file = process.env.SYMBOL_TAGS_FILE || "tags.json";
  const repo = process.env.SYMBOL_REPO;
  const srcHash = process.env.SYMBOL_SRC_HASH;
  if (!repo || !srcHash) {
    console.error("SYMBOL_REPO and SYMBOL_SRC_HASH are required");
    process.exit(2);
  }
  const symbols = tagsToSymbols(readFileSync(file, "utf8"));
  const payload = { repo, src_hash: srcHash, head_sha: process.env.GITHUB_SHA, symbols };
  console.error(`[symbol-index] ${repo}: ${symbols.length} symbols (src_hash ${srcHash.slice(0, 12)})`);

  if (process.env.SYMBOL_DRY_RUN === "1") {
    process.stdout.write(JSON.stringify(payload));
    return;
  }

  const url = process.env.SYMBOL_INGEST_URL;
  const secret = process.env.SYMBOL_INGEST_SECRET;
  if (!url || !secret) {
    console.error("SYMBOL_INGEST_URL and SYMBOL_INGEST_SECRET are required (or set SYMBOL_DRY_RUN=1)");
    process.exit(2);
  }
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${secret}` },
    body: JSON.stringify(payload),
  });
  const text = await res.text();
  if (!res.ok) {
    console.error(`[symbol-index] ingest failed ${res.status}: ${text}`);
    process.exit(1);
  }
  console.error(`[symbol-index] ingested: ${text}`);
}

// 直接実行時のみ main を走らせる (import 時は mapping だけ使える)。
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
