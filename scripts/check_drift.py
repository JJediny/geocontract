#!/usr/bin/env python3
"""Check that the bundle and mise pins agree (plan §11 item 3).

portolan-skills/pins.toml is the canonical record of the upstream versions
the skills describe. mise.toml pins the same versions for the local tasks
under [env]. Neither is authoritative alone: the skills describe workflows
for the versions in pins.toml, and our tasks execute the versions in
mise.toml. When the two files disagree, a documented command runs against
an untested tool version — exactly the failure mode the repo norms forbid.

Run manually with `mise run drift-check`. CI runs it as part of
`mise run ci`.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINS = ROOT / "portolan-skills" / "pins.toml"
MISE = ROOT / "mise.toml"


def load_mise_env() -> dict[str, str]:
    """Extract the pinned values from mise.toml, wherever they appear."""
    text = MISE.read_text()
    env: dict[str, str] = {}
    for key in ("RASHID_SPEC", "PORTOLAN_CLI_SPEC", "PORTOLAN_SCHEMA_URI"):
        m = re.search(rf'(?m)^{key} = "(.*)"$', text)
        if m:
            env[key] = m.group(1)
    return env


def expect(cond: bool, msg: str, failures: list[str]) -> None:
    if not cond:
        failures.append(msg)


def main() -> int:
    failures: list[str] = []
    if not PINS.exists():
        print(f"error: {PINS} not found. Is the portolan-skills submodule initialized?")
        return 1
    pins = tomllib.loads(PINS.read_text())

    env = load_mise_env()

    rashid = pins.get("rashid", {}).get("version")
    rashid_spec = env.get("RASHID_SPEC", "")
    expect(
        bool(rashid) and rashid_spec.startswith(f"rashid>={rashid},"),
        f"rashid pin drift: pins.toml has {rashid!r}, mise.toml RASHID_SPEC is {rashid_spec!r}",
        failures,
    )

    cli = pins.get("portolan-cli", {}).get("version")
    cli_spec = env.get("PORTOLAN_CLI_SPEC", "")
    expect(
        bool(cli) and cli_spec == f"portolan-cli=={cli}",
        f"portolan-cli pin drift: pins.toml has {cli!r}, mise.toml PORTOLAN_CLI_SPEC is {cli_spec!r}",
        failures,
    )

    spec_tag = pins.get("portolan-spec", {}).get("tag")
    schema_uri = env.get("PORTOLAN_SCHEMA_URI", "")
    expect(
        bool(spec_tag) and schema_uri.endswith(f"portolan/{spec_tag}/schema.json"),
        f"portolan-spec pin drift: pins.toml has {spec_tag!r}, mise.toml PORTOLAN_SCHEMA_URI is {schema_uri!r}",
        failures,
    )

    # The submodule must sit at the tag pins.toml records. Only warn on a
    # dirty detached state so a CI checkout without tags does not fail.
    try:
        import subprocess

        described = subprocess.run(
            ["git", "describe", "--tags", "--exact-match"],
            cwd=ROOT / "portolan-spec",
            capture_output=True,
            text=True,
            check=False,
        )
        actual = described.stdout.strip()
        if described.returncode == 0 and actual and actual != spec_tag:
            failures.append(
                f"portolan-spec submodule sits at {actual!r}, pins.toml records {spec_tag!r}"
            )
        elif described.returncode != 0:
            print(
                "warning: portolan-spec submodule has no exact tag; skipping submodule-tag check",
                file=sys.stderr,
            )
    except FileNotFoundError:
        print("warning: git unavailable; skipping submodule-tag check", file=sys.stderr)

    if failures:
        print("drift detected:")
        for f in failures:
            print(f"  - {f}")
        print("move the pin in portolan-skills/pins.toml and mise.toml [env] in the same change")
        return 1

    print(
        f"OK  pins agree: rashid {rashid}, portolan-cli {cli}, portolan-spec {spec_tag}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
