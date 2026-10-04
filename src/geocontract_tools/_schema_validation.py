"""Shared JSON-Schema validation helpers for the geocontract test suite.

The Draft 2020-12 default ``format_checker`` is intentionally narrow:
it only validates ``email``, ``idn-email``, ``ipv4``, ``ipv6``,
``idn-hostname``, ``regex``, ``date``, and ``uuid``. The v2 Proposal
template uses ``format: "date-time"``, ``format: "uri"``, and
``format: "email"`` — but ``date-time`` and ``uri`` are silently
ignored without a custom format checker.

This module exposes :func:`make_format_checker`, which returns a
``FormatChecker`` that:

- delegates the standard set of formats to
  ``Draft202012Validator.FORMAT_CHECKER`` (``email``, ``ipv4``, ``ipv6``,
  ``uuid``, …),
- adds strict ``date-time`` (RFC 3339, timezone-required) and ``uri``
  (RFC 3986, scheme + netloc required) checkers, and
- raises :class:`jsonschema.exceptions.FormatError` on every failure.

Use this anywhere the v2 Proposal template is validated against an
instance document so the ``format`` keyword is actually enforced.
"""

from __future__ import annotations

import datetime as dt
import urllib.parse as up
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import FormatError


def make_format_checker() -> Any:
    """Return a ``FormatChecker`` with ``date-time`` and ``uri`` enforced.

    The returned object is a fresh ``FormatChecker`` instance built on
    top of ``Draft202012Validator.FORMAT_CHECKER``. It is safe to pass
    as the ``format_checker=`` keyword argument to any jsonschema
    ``Validator`` subclass.
    """
    fc = Draft202012Validator.FORMAT_CHECKER

    @fc.checks("date-time", raises=FormatError)
    def _date_time(value: Any) -> bool:
        # `format` only applies to string instances. When the schema
        # also allows `null` (e.g. `"type": ["null", "string"]`), the
        # non-string values are accepted by the type validator; the
        # format check must be a no-op on them.
        if not isinstance(value, str):
            return True
        # RFC 3339: date-time includes a timezone designator. Python's
        # fromisoformat accepts naive timestamps, so we explicitly
        # require a timezone offset. We also accept the 'Z' shorthand.
        normalised = value.replace("Z", "+00:00")
        try:
            parsed = dt.datetime.fromisoformat(normalised)
        except ValueError:
            return False
        if parsed.tzinfo is None:
            return False
        return True

    @fc.checks("uri", raises=FormatError)
    def _uri(value: Any) -> bool:
        # `format` only applies to string instances.
        if not isinstance(value, str):
            return True
        # RFC 3986: a URI has a non-empty scheme and netloc. We reject
        # relative references and bare paths.
        parsed = up.urlparse(value)
        return bool(parsed.scheme and parsed.netloc)

    return fc
