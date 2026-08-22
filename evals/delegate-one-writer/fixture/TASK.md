# Task

Implement `canonicalize_label(value: str) -> str` in `label.py`.

The function must:

1. trim surrounding whitespace;
2. lowercase ASCII letters;
3. preserve ASCII letters and digits;
4. replace each non-empty run of other characters with one hyphen;
5. remove leading and trailing hyphens;
6. raise `ValueError` when no ASCII letter or digit remains.

Keep the implementation dependency-free and make the existing tests pass.
