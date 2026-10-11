"""Parity guard: the JudgeProbe must reuse production's prompt + fencing verbatim.

The probe copies `_JUDGE_TASK`, `_DATA_BEGIN`, `_DATA_END` and the prompt-assembly
and consensus logic from contracts/accountability_bond.py. Because GenLayer
contracts are one-class-per-file and cannot import each other, that copy cannot
be shared at runtime -- so this test asserts the shared pieces are byte-identical
between the two source files, catching any silent drift.

This is a plain-text check on the source files; it needs no GenVM runtime.
"""

import re
from pathlib import Path

CONTRACTS = Path(__file__).parent.parent.parent / "contracts"
PROD = (CONTRACTS / "accountability_bond.py").read_text()
PROBE = (CONTRACTS / "judge_probe.py").read_text()


def _extract(src, name):
    m = re.search(name + r' = """(.*?)"""', src, re.S)
    assert m, "could not find %s" % name
    return m.group(1)


def _extract_assign(src, name):
    m = re.search(re.escape(name) + r' = (".*?")\n', src, re.S)
    assert m, "could not find %s" % name
    return m.group(1)


def test_judge_task_is_identical():
    assert _extract(PROD, "_JUDGE_TASK") == _extract(PROBE, "_JUDGE_TASK")


def test_fencing_markers_are_identical():
    assert _extract_assign(PROD, "_DATA_BEGIN") == _extract_assign(PROBE, "_DATA_BEGIN")
    assert _extract_assign(PROD, "_DATA_END") == _extract_assign(PROBE, "_DATA_END")


def test_prompt_assembly_is_identical():
    """The exact '+'-concatenation that builds the prompt must match."""
    frag = (
        '_JUDGE_TASK\n'
        '                + "\\n\\nPROMISE:\\n" + promise'
    )
    # normalise local var name (promise vs promise_l) before comparing structure
    def norm(s):
        return re.sub(r"promise(_l)?|criteria(_l)?|text", "X", s)
    prod_asm = re.search(r'prompt = \((.*?)\)\n', PROD, re.S).group(1)
    probe_asm = re.search(r'prompt = \((.*?)\)\n', PROBE, re.S).group(1)
    assert norm(prod_asm) == norm(probe_asm)


def test_consensus_validate_logic_is_identical():
    """The validator body (agree only on the boolean) must match once comments
    and whitespace are stripped. Production carries explanatory comments the
    probe omits; the executable logic must be identical."""
    def grab(src):
        m = re.search(r'def validate\(leaders_res\) -> bool:(.*?)\n\n', src, re.S)
        return m.group(1)
    def norm(s):
        # drop full-line and trailing comments, then collapse whitespace
        no_comments = "\n".join(
            re.sub(r"#.*$", "", line) for line in s.splitlines()
        )
        return re.sub(r"\s+", " ", no_comments).strip()
    assert norm(grab(PROD)) == norm(grab(PROBE))


def test_probe_has_no_financial_surface():
    """The probe must declare no payable method and move no value. Check the
    executable surface (decorators, storage fields, transfer calls), not prose
    comments -- the module docstring legitimately mentions these words to say it
    has none of them."""
    assert "@gl.public.write.payable" not in PROBE
    assert ".payable" not in PROBE
    assert "emit_transfer" not in PROBE
    assert "balance_held:" not in PROBE
    assert "claimable:" not in PROBE
    assert "u256" not in PROBE  # no value arithmetic at all
