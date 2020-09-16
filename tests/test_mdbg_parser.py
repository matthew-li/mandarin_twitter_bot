from bs4 import BeautifulSoup
from bs4 import element
from mdbg_parser import MDBGParser
import unittest

"""A test module for mdbg_parser.py."""


class TestMDBGParser(unittest.TestCase):
    """A class for testing MDBGParser."""

    def test_bad_input_type(self):
        """Test that an error is raised if the input has an incorrect
        type."""
        try:
            MDBGParser(1, pinyin=None)
            MDBGParser("", pinyin=[])
        except TypeError:
            pass
        else:
            self.fail(f"A TypeError should have been raised.")

    def test_instantiation(self):
        """Test that the expected variables are set during
        instantiation."""
        simplified = "你好"
        mdbg_parser = MDBGParser(simplified)
        self.assertEqual(mdbg_parser.simplified, simplified)
        self.assertIsNone(mdbg_parser.pinyin)
        self.assertIsInstance(mdbg_parser.definitions, list)
        self.assertFalse(mdbg_parser.definitions)

        pinyin = "nǐhǎo"
        mdbg_parser = MDBGParser(simplified, pinyin=pinyin)
        self.assertEqual(mdbg_parser.simplified, simplified)
        self.assertEqual(mdbg_parser.pinyin, pinyin)
        self.assertIsInstance(mdbg_parser.definitions, list)
        self.assertFalse(mdbg_parser.definitions)

    def test_get_search_results(self):
        """Test that a sample search returns a parsable HTML
        response."""
        simplified = "你好"
        pinyin = "nǐhǎo"
        mdbg_parser = MDBGParser(simplified, pinyin=pinyin)
        search_results = mdbg_parser.get_search_results(mdbg_parser.simplified)
        self.assertIn("</html>".encode("utf-8"), search_results)
        soup = BeautifulSoup(search_results, "html.parser")
        html = soup.find("html")
        self.assertIsInstance(html, element.Tag)

    def test_run(self):
        """Test that the run method stores the results of the search in
        the instance."""
        simplified = "你好"
        initial_pinyin = "nihao"
        mdbg_parser = MDBGParser(simplified, pinyin=initial_pinyin)
        self.assertEqual(mdbg_parser.simplified, simplified)
        self.assertEqual(mdbg_parser.pinyin, initial_pinyin)

        # If the pinyin differ, the one retrieved from the dictionary should
        # replace the original.
        expected_pinyin = "nǐhǎo"
        mdbg_parser.run()
        self.assertEqual(mdbg_parser.simplified, simplified)
        self.assertEqual(mdbg_parser.pinyin, expected_pinyin)
        self.assertIsInstance(mdbg_parser.definitions, list)
        self.assertTrue(mdbg_parser.definitions)
        for definition in mdbg_parser.definitions:
            self.assertIsInstance(definition, str)
            self.assertTrue(definition)


if __name__ == "__main__":
    unittest.main()
