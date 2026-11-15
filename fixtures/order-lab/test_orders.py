import unittest

from api import order_response
from service import normalize_status


class OrderContract(unittest.TestCase):
    def test_null(self) -> None:
        self.assertEqual(normalize_status(None), "pending")
        self.assertEqual(order_response(None), {"status": "pending"})

    def test_valid_statuses(self) -> None:
        for value in ("pending", "paid", "cancelled"):
            self.assertEqual(normalize_status(value.upper()), value)
            self.assertEqual(order_response(value.upper()), {"status": value})

    def test_invalid(self) -> None:
        for value in ("unknown", "", "refunded"):
            with self.assertRaises(ValueError):
                normalize_status(value)
            with self.assertRaises(ValueError):
                order_response(value)
