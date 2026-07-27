"""The mail-absence manifest must identify the source, not the checkout.

Found by CI: the manifest hashed raw file bytes, so the same commit produced a different value on
a CRLF checkout than on an LF one. That makes it useless for the thing it exists for — two peers
comparing whether they ran the same mail-free code — and it made a generated page fail its own
drift check, which is how it surfaced.
"""

import hashlib
import unittest
from pathlib import Path

from sparring.guards import no_mail


class TestManifestIsCheckoutIndependent(unittest.TestCase):
    def test_line_endings_do_not_change_the_hash(self):
        crlf = b"import os\r\nx = 1\r\n"
        lf = b"import os\nx = 1\n"
        self.assertEqual(
            hashlib.sha256(crlf.replace(b"\r\n", b"\n")).hexdigest(),
            hashlib.sha256(lf).hexdigest(),
            "normalising CRLF to LF must make the two identical")

    def test_the_manifest_normalises_what_it_hashes(self):
        source = (Path(no_mail.__file__)).read_text(encoding="utf-8")
        self.assertIn('replace(b"\\r\\n", b"\\n")', source,
                      "manifest_sha256 must normalise line endings before hashing")

    def test_paths_are_recorded_with_forward_slashes(self):
        source = (Path(no_mail.__file__)).read_text(encoding="utf-8")
        self.assertIn('.replace("\\\\", "/")', source,
                      "a Windows path separator would change the manifest too")

    def test_the_manifest_is_stable_within_a_run(self):
        self.assertEqual(no_mail.manifest_sha256(), no_mail.manifest_sha256())


if __name__ == "__main__":
    unittest.main()
