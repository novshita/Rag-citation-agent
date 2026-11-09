"""Checks on the static web UI that don't need a browser."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).parent.parent / "src" / "rag" / "web"


def test_the_page_links_only_to_files_that_exist():
    html = (WEB / "index.html").read_text()
    for path in re.findall(r'(?:href|src)="/static/([^"]+)"', html):
        assert (WEB / path).is_file(), path


def test_every_javascript_import_resolves():
    for js in WEB.glob("*.js"):
        for target in re.findall(r'from\s+"\./([^"]+)"', js.read_text()):
            assert (WEB / target).is_file(), f"{js.name} imports missing {target}"


def test_server_text_is_never_inserted_as_html():
    """Document passages come from outside; they must only ever be set as text."""
    source = (WEB / "app.js").read_text()
    uses = [line.strip() for line in source.splitlines() if "innerHTML" in line and not line.strip().startswith("//")]
    assert uses == ["svg.innerHTML = ICONS[name] || \"\";"]      # only the fixed icon set
    assert "insertAdjacentHTML" not in source and "document.write" not in source


def test_the_page_has_the_basics_for_accessibility_and_sharing():
    html = (WEB / "index.html").read_text()
    assert '<html lang="en">' in html and 'name="viewport"' in html and 'name="description"' in html
    assert "<title>RAG Citation Agent</title>" in html


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_javascript_unit_tests_pass():
    result = subprocess.run(
        ["node", "--test", "tests/js/format.test.mjs"],
        cwd=Path(__file__).parent.parent, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
