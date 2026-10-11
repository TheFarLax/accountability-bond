"""Deployment hygiene: the contract source must be pure ASCII.

gltest fetches a contract's schema by hex-encoding the source as ASCII, so a
single non-ASCII byte anywhere -- including in a comment or a prompt string --
makes deployment fail with a misleading "schema from all clients" error. This
guard catches it in milliseconds in direct mode instead of during a slow network
deploy. (Learned the hard way on the prior project.)
"""

from pathlib import Path

CONTRACTS = Path(__file__).parent.parent.parent / "contracts"


def test_contract_source_is_pure_ascii():
    for path in sorted(CONTRACTS.glob("*.py")):
        data = path.read_bytes()
        try:
            data.decode("ascii")
        except UnicodeDecodeError as exc:
            raise AssertionError(
                f"{path.name} contains a non-ASCII byte at offset {exc.start}; "
                "this breaks gltest deployment. Keep contract sources pure ASCII."
            )
