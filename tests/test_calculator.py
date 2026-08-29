import unittest

from calculator import add, divide, multiply, subtract


class CalculatorTests(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(7, 5), 12)

    def test_subtract(self):
        self.assertEqual(subtract(10, 3), 7)

    def test_multiply(self):
        self.assertEqual(multiply(6, 8), 48)

    def test_divide(self):
        self.assertEqual(divide(10, 2), 5)

    def test_decimal_values(self):
        self.assertAlmostEqual(add(0.1, 0.2), 0.3)

    def test_divide_by_zero(self):
        with self.assertRaises(ZeroDivisionError):
            divide(1, 0)


if __name__ == "__main__":
    unittest.main()
