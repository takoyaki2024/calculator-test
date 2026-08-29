"""Simple desktop calculator using Tkinter."""

import tkinter as tk
from tkinter import messagebox

from calculator import add, divide, multiply, subtract


class CalculatorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Calculator")
        self.root.resizable(False, False)

        self.first = tk.StringVar()
        self.second = tk.StringVar()
        self.result = tk.StringVar(value="Result: -")

        tk.Label(root, text="First number").grid(row=0, column=0, padx=8, pady=8, sticky="e")
        tk.Entry(root, textvariable=self.first, width=18).grid(row=0, column=1, columnspan=3, padx=8, pady=8)
        tk.Label(root, text="Second number").grid(row=1, column=0, padx=8, pady=8, sticky="e")
        tk.Entry(root, textvariable=self.second, width=18).grid(row=1, column=1, columnspan=3, padx=8, pady=8)

        operations = [("+", add), ("-", subtract), ("×", multiply), ("÷", divide)]
        for column, (label, operation) in enumerate(operations):
            tk.Button(root, text=label, width=6, command=lambda op=operation: self.calculate(op)).grid(
                row=2, column=column, padx=4, pady=8
            )

        tk.Label(root, textvariable=self.result, font=("TkDefaultFont", 12, "bold")).grid(
            row=3, column=0, columnspan=4, padx=8, pady=12
        )

    def calculate(self, operation) -> None:
        try:
            a = float(self.first.get())
            b = float(self.second.get())
            value = operation(a, b)
            self.result.set(f"Result: {value:g}")
        except ValueError:
            messagebox.showerror("Invalid input", "Please enter valid numbers.")
        except ZeroDivisionError:
            messagebox.showerror("Calculation error", "Cannot divide by zero.")


def main() -> None:
    root = tk.Tk()
    CalculatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
