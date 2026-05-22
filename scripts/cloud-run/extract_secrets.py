#!/usr/bin/env python3
"""Extract GCP Secret Manager names from a Cloud Run deploy workflow.

Walks every job's `with:` block looking for `update_secrets` /
`set_secrets` strings. The cloud-run-deploy.yml reusable accepts these
in the gcloud-native format:

    ENV1=SECRET1[:VERSION],ENV2=SECRET2[:VERSION]

We split on comma, take the right-hand side of `=`, then strip the
optional `:VERSION` suffix. The remaining token is the GCP Secret
Manager secret name.

GitHub Actions expressions (``${{ ... }}``) in the secret slot are
skipped with a stderr warning rather than emitted as-is — a literal
``${{ vars.X }}`` is never a real secret name in GCP, and emitting it
would always fail the downstream `gcloud secrets list` comparison with
a misleading "missing secret" error.

Output is one name per line, sorted and de-duplicated. Empty when no
`update_secrets` / `set_secrets` is declared anywhere.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

try:
    import yaml
except ImportError:
    print(
        "error: PyYAML is required. Install with: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(1)


SECRETS_KEYS = ("update_secrets", "set_secrets")


def _iter_jobs(data: object) -> Iterable[dict]:
    if not isinstance(data, dict):
        return
    jobs = data.get("jobs")
    if not isinstance(jobs, dict):
        return
    for job in jobs.values():
        if isinstance(job, dict):
            yield job


def _parse_secret_pairs(value: str) -> Iterable[str]:
    # Tolerate both inline ",..." and YAML block scalars where the user
    # split pairs across lines.
    for line in value.splitlines():
        for pair in line.split(","):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            _, secret_part = pair.split("=", 1)
            name = secret_part.split(":", 1)[0].strip()
            if not name:
                continue
            if "${{" in name:
                print(
                    f"warning: skipping GitHub expression in secret slot: {name!r}",
                    file=sys.stderr,
                )
                continue
            yield name


def extract_secrets(workflow_path: Path) -> list[str]:
    with workflow_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    found: set[str] = set()
    for job in _iter_jobs(data):
        with_block = job.get("with") or {}
        if not isinstance(with_block, dict):
            continue
        for key in SECRETS_KEYS:
            val = with_block.get(key)
            if not isinstance(val, str):
                continue
            found.update(_parse_secret_pairs(val))
    return sorted(found)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "usage: extract_secrets.py <workflow-yaml>",
            file=sys.stderr,
        )
        return 2
    path = Path(argv[1])
    if not path.exists():
        print(f"error: workflow not found: {path}", file=sys.stderr)
        return 1
    try:
        names = extract_secrets(path)
    except yaml.YAMLError as e:
        print(f"error: failed to parse {path}: {e}", file=sys.stderr)
        return 1
    for name in names:
        print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
