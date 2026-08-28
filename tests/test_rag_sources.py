"""BX-12 unit acceptance tests for managed RAG source invariants."""

import math
import unittest

from services.workflow.rag_sources import (
    MAX_FILE_BYTES,
    MAX_CHUNK_CHARACTERS,
    RagSourceError,
    chunk_text,
    validate_upload,
    validate_vector,
)


class ManagedRagSourceTests(unittest.TestCase):
    def test_pdf_upload_accepts_exact_limit_and_rejects_adjacent_sizes(self):
        for size in (MAX_FILE_BYTES - 1, MAX_FILE_BYTES):
            self.assertEqual(
                validate_upload("mevzuat.pdf", "application/pdf", b"x" * size),
                ("mevzuat.pdf", "application/pdf", size),
            )
        with self.assertRaisesRegex(RagSourceError, "FILE_TOO_LARGE"):
            validate_upload("mevzuat.pdf", "application/pdf", b"x" * (MAX_FILE_BYTES + 1))

    def test_upload_rejects_empty_and_mime_suffix_mismatch(self):
        with self.assertRaisesRegex(RagSourceError, "FILE_EMPTY"):
            validate_upload("bos.pdf", "application/pdf", b"")
        with self.assertRaisesRegex(RagSourceError, "FILE_TYPE_INVALID"):
            validate_upload("yanlis.docx", "application/pdf", b"x")
        with self.assertRaisesRegex(RagSourceError, "FILE_TYPE_INVALID"):
            validate_upload("yanlis.pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"x")

    def test_chunking_preserves_every_character_and_respects_exact_limit(self):
        text = "a" * (MAX_CHUNK_CHARACTERS * 2 + 1)
        chunks = chunk_text(text)
        self.assertEqual([len(chunk) for chunk in chunks], [MAX_CHUNK_CHARACTERS, MAX_CHUNK_CHARACTERS, 1])
        self.assertEqual("".join(chunks), text)

    def test_chunking_rejects_empty_text(self):
        with self.assertRaisesRegex(RagSourceError, "TEXT_EMPTY"):
            chunk_text("")

    def test_vector_requires_1024_finite_dimensions_and_unit_norm_tolerance(self):
        exact = [1 / math.sqrt(1024)] * 1024
        self.assertEqual(validate_vector(exact), exact)
        with self.assertRaisesRegex(RagSourceError, "VECTOR_DIMENSION_INVALID"):
            validate_vector(exact[:-1])
        with self.assertRaisesRegex(RagSourceError, "VECTOR_INVALID"):
            validate_vector([float("nan")] + exact[1:])
        with self.assertRaisesRegex(RagSourceError, "VECTOR_NORM_INVALID"):
            validate_vector([0.0] * 1024)


if __name__ == "__main__":
    unittest.main()
