"""
Pins the GenVM SDK version used by direct-mode tests (`direct_deploy`).

Why this exists: `direct_deploy()` with no explicit `sdk_version` asks the
`genlayer-test` package to auto-resolve "latest" from
https://github.com/genlayerlabs/genvm/releases/latest. As of writing,
that resolves to v0.3.0-rc7, whose release assets are all
platform-specific (genvm-linux-amd64.tar.xz, genvm-macos-arm64.tar.xz,
etc.) -- but the installed `genlayer-test==0.29.2` package's downloader
still requests a generic `genvm-universal.tar.xz`, an asset name that
stopped being published starting with v0.3.0-rc0. The result is a 404 and
every direct test fails before it even runs, regardless of anything in
this repo's own code.

Separately, and more importantly for correctness: this contract is
written against the pre-v0.3.0 GenVM API (`from genlayer import *`,
`class X(gl.Contract)`, `@allow_storage`) and is deployed with a runner
pinned to that same generation (see the `Depends` header in
contracts/url_reputation_oracle.py and the "Notes on the runner version"
section in the main README). Testing against a v0.3.0 SDK -- even if the
404 above were fixed -- would exercise a different, restructured API
surface than what's actually deployed on-chain.

v0.2.16 is the newest v0.2.x release, confirmed compatible with this
contract by actually running the full direct test suite against it.
Bump this once the contract itself migrates to the v0.3.0 API (see the
migration notes referenced in the main README), not before.
"""

import pytest


@pytest.fixture
def direct_deploy(direct_deploy):
    def _deploy(*args, **kwargs):
        kwargs.setdefault("sdk_version", "v0.2.16")
        return direct_deploy(*args, **kwargs)

    return _deploy
