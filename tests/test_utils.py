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
        try:
            random_dates_in_range(bad_start, good_end, good_k)
            random_dates_in_range(good_start, bad_end, good_k)
            random_dates_in_range(good_start, good_end, bad_k)
        except TypeError:
            pass
        else:
            self.fail("A TypeError should have been raised.")

    def test_bad_date_order(self):
        """Test that an error is raised if the end date is less than or
        equal to the start date."""
        try:
            random_dates_in_range(self.end, self.start, 1)
            random_dates_in_range(self.start, self.start, 1)
        except ValueError:
            pass
        else:
            self.fail("A ValueError should have been raised.")

    def test_non_positive_k(self):
        """Test that an error is raised if the input k is
        non-positive."""
        try:
            random_dates_in_range(self.start, self.end, -1)
            random_dates_in_range(self.start, self.end, 0)
        except ValueError:
            pass
        else:
            self.fail("A ValueError should have been raised.")

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
