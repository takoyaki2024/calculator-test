"""Desktop calculator using Tkinter."""

import tkinter as tk
from tkinter import messagebox

from calculator import evaluate_expression


class CalculatorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Calculator")
        self.root.resizable(False, False)

        self.expression = tk.StringVar()
        self.result = tk.StringVar(value="Result: -")

        entry = tk.Entry(root, textvariable=self.expression, width=28, font=("TkDefaultFont", 14))
        entry.grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 6))
        entry.focus_set()
        entry.bind("<Return>", lambda _event: self.calculate())

        buttons = [
            ("7", "7"), ("8", "8"), ("9", "9"), ("÷", "/"),
            ("4", "4"), ("5", "5"), ("6", "6"), ("×", "*"),
            ("1", "1"), ("2", "2"), ("3", "3"), ("-", "-"),
            ("0", "0"), (".", "."), ("+", "+"), ("(", "("),
            (")", ")"),
        ]

        for index, (label, value) in enumerate(buttons):
            row = 1 + index // 4
            column = index % 4
            tk.Button(root, text=label, width=6, command=lambda text=value: self.append(text)).grid(
                row=row, column=column, padx=3, pady=3
            )

        action_row = 1 + (len(buttons) + 3) // 4
        tk.Button(root, text="Clear", width=10, command=self.clear).grid(
            row=action_row, column=0, columnspan=2, padx=3, pady=6
        )
        tk.Button(root, text="=", width=10, command=self.calculate).grid(
            row=action_row, column=2, columnspan=2, padx=3, pady=6
        )

        tk.Label(root, textvariable=self.result, font=("TkDefaultFont", 12, "bold")).grid(
            row=action_row + 1, column=0, columnspan=4, padx=8, pady=(4, 8)
        )

        tk.Label(root, text="History").grid(row=action_row + 2, column=0, columnspan=4)
        self.history = tk.Listbox(root, width=34, height=6)
        self.history.grid(row=action_row + 3, column=0, columnspan=4, padx=10, pady=(4, 10))

    def append(self, text: str) -> None:
        self.expression.set(self.expression.get() + text)

    def clear(self) -> None:
        self.expression.set("")
        self.result.set("Result: -")

    def calculate(self) -> None:
        expression = self.expression.get()
        try:
            value = evaluate_expression(expression)
        except ValueError:
            messagebox.showerror("Invalid input", "Please enter a valid arithmetic expression.")
            return
        except ZeroDivisionError:
            messagebox.showerror("Calculation error", "Cannot divide by zero.")
            return

        formatted = f"{value:g}"
        self.result.set(f"Result: {formatted}")
        self.history.insert(0, f"{expression} = {formatted}")
        if self.history.size() > 10:
            self.history.delete(10, tk.END)


def main() -> None:
    root = tk.Tk()
    CalculatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
