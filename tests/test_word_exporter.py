# -*- coding: utf-8 -*-

import unittest

from docx import Document

from dataflow_edu.export.data_loader import QuestionRecord
from dataflow_edu.export.word_exporter import _HEADINGS, _add_question_answer


class WordExporterTest(unittest.TestCase):
    def test_blank_answer_section_repeats_full_question_without_ellipsis(self):
        question = (
            "Explain the data governance, privacy protection, and platform "
            "responsibility principles that should be followed when building "
            "an intelligent question bank for an education scenario."
        )
        rec = QuestionRecord(question=question, answer="reference answer")
        doc = Document()

        _add_question_answer(
            doc,
            "essay-1",
            rec,
            labels=_HEADINGS["zh"],
            include_question_repeat=True,
        )

        repeated_question = doc.paragraphs[0].text
        self.assertEqual(repeated_question, f"essay-1. {question}")
        self.assertFalse(repeated_question.endswith("..."))
        self.assertFalse(repeated_question.endswith("\u2026"))


if __name__ == "__main__":
    unittest.main()
