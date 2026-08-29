import unittest

from calculator import add, divide, evaluate_expression, multiply, subtract


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

    def test_expression_precedence(self):
        self.assertEqual(evaluate_expression("2 + 3 * 4"), 14)

    def test_expression_parentheses(self):
        self.assertEqual(evaluate_expression("(2 + 3) * 4"), 20)

    def test_expression_unary_minus(self):
        self.assertEqual(evaluate_expression("-5 + 2"), -3)

    def test_expression_decimal(self):
        self.assertAlmostEqual(evaluate_expression("1.5 * 2"), 3.0)

    def test_expression_divide_by_zero(self):
        with self.assertRaises(ZeroDivisionError):
            evaluate_expression("10 / (5 - 5)")

    def test_expression_rejects_names(self):
        with self.assertRaises(ValueError):
            evaluate_expression("open('file.txt')")

    def test_expression_rejects_power(self):
        with self.assertRaises(ValueError):
            evaluate_expression("2 ** 8")

    def test_expression_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            evaluate_expression("   ")


if __name__ == "__main__":
    unittest.main()
