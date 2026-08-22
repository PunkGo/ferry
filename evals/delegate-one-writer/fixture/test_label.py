import unittest

from label import canonicalize_label


class CanonicalizeLabelTests(unittest.TestCase):
    def test_trims_and_lowercases_ascii(self) -> None:
        self.assertEqual(canonicalize_label("  Release Candidate  "), "release-candidate")

    def test_collapses_separator_runs(self) -> None:
        self.assertEqual(canonicalize_label("alpha_ / beta"), "alpha-beta")
        self.assertEqual(canonicalize_label("alphaé中beta"), "alpha-beta")

    def test_removes_edge_separators(self) -> None:
        self.assertEqual(canonicalize_label("---Ready!!"), "ready")

    def test_rejects_an_empty_result(self) -> None:
        with self.assertRaises(ValueError):
            canonicalize_label(" / _ - ")
        with self.assertRaises(ValueError):
            canonicalize_label("é中")


if __name__ == "__main__":
    unittest.main()
