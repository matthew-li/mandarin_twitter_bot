from datetime import date
from datetime import datetime
from settings import DATE_FORMAT
from utils import random_dates_in_range
import unittest

"""A test module for utils.py."""


class TestRandomDatesInRange(unittest.TestCase):
    """A class for testing random_dates_in_range."""

    def setUp(self):
        """Set up test data."""
        today = datetime.today()
        self.start = datetime(today.year, 1, 1).date()
        self.end = datetime(today.year, 12, 31).date()

    def test_bad_input_types(self):
        """Test that an error is raised if an input has an incorrect
        type."""
        good_start, good_end, good_k = self.start, self.end, 1
        bad_start, bad_end, bad_k = str(), int(), list()
        arg_sets = [
            (bad_start, good_end, good_k),
            (good_start, bad_end, good_k),
            (good_start, good_end, bad_k),
        ]
        for arg_set in arg_sets:
            with self.assertRaises(TypeError):
                random_dates_in_range(arg_set[0], arg_set[1], arg_set[2])

    def test_bad_date_order(self):
        """Test that an error is raised if the end date is less than or
        equal to the start date."""
        arg_sets = [
            (self.end, self.start, 1),
            (self.start, self.start, 1),
        ]
        for arg_set in arg_sets:
            with self.assertRaises(ValueError):
                random_dates_in_range(arg_set[0], arg_set[1], arg_set[2])

    def test_non_positive_k(self):
        """Test that an error is raised if the input k is
        non-positive."""
        arg_sets = [
            (self.start, self.end, -1),
            (self.start, self.end, 0),
        ]
        for arg_set in arg_sets:
            with self.assertRaises(ValueError):
                random_dates_in_range(arg_set[0], arg_set[1], arg_set[2])

    def test_dates_in_range(self):
        """Test that the generated dates are in the range
        [start, end)."""
        start = datetime.strptime("2020-01-01", DATE_FORMAT).date()
        end = datetime.strptime("2020-12-31", DATE_FORMAT).date()
        k = 5
        random_dates = random_dates_in_range(start, end, k)
        self.assertEqual(len(random_dates), k)
        for random_date in random_dates:
            self.assertTrue(isinstance(random_date, date))
            self.assertTrue(start <= random_date < end)

    def test_at_most_k(self):
        """Test that, if the range between two dates is smaller than k,
        the generated dates comprise the entire range."""
        start = self.start
        end = datetime(start.year, start.month + 1, 1).date()
        num_days = (end - start).days
        k = num_days + 1
        random_dates = sorted(random_dates_in_range(start, end, k))
        self.assertEqual(len(random_dates), num_days)
        for i in range(num_days):
            expected_date = datetime(start.year, start.month, 1 + i).date()
            actual_date = random_dates[i]
            self.assertEqual(expected_date, actual_date)
        self.assertNotEqual(random_dates[-1], end)

    def test_dates_unique(self):
        """Test that the generated dates are unique."""
        k = 100
        random_dates = random_dates_in_range(self.start, self.end, k)
        self.assertEqual(len(random_dates), k)
        self.assertEqual(len(set(random_dates)), k)


if __name__ == "__main__":
    unittest.main()
