"""Bezpieczny ewaluator wyrażeń matematycznych (bez eval) dla Nova Calculator."""
from __future__ import annotations

import ast
import math
import operator

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow,
        ast.FloorDiv: operator.floordiv}
_UN = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class CalcError(ValueError):
    pass


class Engine:
    def __init__(self) -> None:
        self.degrees = True
        self.ans = 0.0

    # funkcje dostępne w trybie naukowym
    def _funcs(self):
        conv = math.radians if self.degrees else (lambda x: x)
        inv = math.degrees if self.degrees else (lambda x: x)
        return {
            "sin": lambda x: math.sin(conv(x)), "cos": lambda x: math.cos(conv(x)),
            "tan": lambda x: math.tan(conv(x)), "asin": lambda x: inv(math.asin(x)),
            "acos": lambda x: inv(math.acos(x)), "atan": lambda x: inv(math.atan(x)),
            "sqrt": math.sqrt, "ln": math.log, "log": math.log10, "abs": abs,
            "exp": math.exp, "fact": self._fact, "round": round,
        }

    @staticmethod
    def _fact(x):
        if x < 0 or x != int(x) or x > 170:
            raise CalcError("factorial domain")
        return math.factorial(int(x))

    def normalize(self, expr: str) -> str:
        e = expr.strip()
        for a, b in (("×", "*"), ("÷", "/"), ("−", "-"), ("π", "pi"), ("√", "sqrt"),
                     ("^", "**"), (",", "."), ("mod", "%")):
            e = e.replace(a, b)
        # procenty: 50% -> (50/100)
        out, num = "", ""
        for ch in e:
            if ch == "%" and num:
                out += f"({num}/100)"
                num = ""
            elif ch.isdigit() or ch == ".":
                num += ch
            else:
                out += num + ch
                num = ""
        e = out + num
        # n! -> fact(n)
        while "!" in e:
            i = e.index("!")
            j = i - 1
            if j >= 0 and e[j] == ")":
                depth = 0
                while j >= 0:
                    depth += e[j] == ")"
                    depth -= e[j] == "("
                    if depth == 0:
                        break
                    j -= 1
            else:
                while j >= 0 and (e[j].isdigit() or e[j] == "."):
                    j -= 1
                j += 1
            e = e[:j] + "fact(" + e[j:i] + ")" + e[i + 1:]
        return e

    def evaluate(self, expr: str) -> float:
        src = self.normalize(expr)
        if not src:
            raise CalcError("empty")
        try:
            tree = ast.parse(src, mode="eval")
        except SyntaxError as exc:
            raise CalcError("syntax") from exc
        value = self._eval(tree.body)
        if isinstance(value, complex) or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
            raise CalcError("domain")
        self.ans = value
        return value

    def _eval(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            left, right = self._eval(node.left), self._eval(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 10000:
                raise CalcError("too large")
            try:
                return _BIN[type(node.op)](left, right)
            except ZeroDivisionError as exc:
                raise CalcError("division by zero") from exc
            except OverflowError as exc:
                raise CalcError("overflow") from exc
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UN:
            return _UN[type(node.op)](self._eval(node.operand))
        if isinstance(node, ast.Name):
            consts = {"pi": math.pi, "e": math.e, "ans": self.ans, "tau": math.tau}
            if node.id in consts:
                return consts[node.id]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            fn = self._funcs().get(node.func.id)
            if fn and len(node.args) == 1:
                try:
                    return fn(self._eval(node.args[0]))
                except (ValueError, OverflowError) as exc:
                    raise CalcError("domain") from exc
        raise CalcError("unsupported")


def fmt(value: float) -> str:
    if isinstance(value, int) or (isinstance(value, float) and value.is_integer() and abs(value) < 1e15):
        return f"{int(value):,}".replace(",", " ")
    text = f"{value:.12g}"
    return text.replace("e+", "×10^").replace("e-", "×10^-")
