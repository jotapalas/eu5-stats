"""docs/metrics.md must match the metric catalogue and the frontend labels (`make docs` regenerates it)."""
from __future__ import annotations

import pytest

from tools import metrics_doc


@pytest.fixture(scope="module")
def built():
    if not (metrics_doc.I18N.exists() and metrics_doc.FORMAT.exists()):
        pytest.skip("frontend/src not available (mount it in the api container)")
    return metrics_doc.build()


def test_every_metric_documented(built):
    _, problems = built
    assert problems == []


def test_metrics_doc_up_to_date(built):
    text, _ = built
    if not metrics_doc.DOC.parent.exists():
        pytest.skip("docs/ not available (mount it in the api container)")
    assert metrics_doc.DOC.exists() and metrics_doc.DOC.read_text(encoding="utf-8") == text, \
        "docs/metrics.md is out of date; run `make docs`"


def test_ts_parsers():
    src = 'export const A: Record<string, string> = {\n  x: "X",\n  // c\n  y: "Y",\n};\n' \
          'export const S = new Set(["p", "q"]);'
    assert metrics_doc.ts_record(src, "A") == {"x": "X", "y": "Y"}
    assert metrics_doc.ts_set(src, "S") == {"p", "q"}
