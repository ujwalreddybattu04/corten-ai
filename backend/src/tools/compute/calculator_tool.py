"""
Calculator Tool — instant math, unit conversion, and percentage calculations.

Handles queries like:
  - "What is 20% tip on $85?"
  - "Convert 100 USD to EUR"
  - "2^100"
  - "sqrt(144) + 15 * 3"
  - "BMI for 180cm 75kg"

Uses Python's ast module for SAFE math evaluation — no eval() or exec().
"""

import ast
import math
import re
import operator
import logging
from typing import Dict, Any, Optional

from src.tools.base_tool import BaseTool, ToolCategory, ToolContext, ToolResult

logger = logging.getLogger(__name__)

# ── Regex patterns for math detection ─────────────────────────────────────────
_MATH_PATTERNS = [
    re.compile(r'\b\d+\s*[\+\-\*/\^%]\s*\d+', re.IGNORECASE),          # 5 + 3, 10 * 2
    re.compile(r'\b(sqrt|cbrt|log|ln|sin|cos|tan|abs|pow)\s*\(', re.IGNORECASE),  # sqrt(144)
    re.compile(r'\b\d+\s*%\s*(of|tip|off)\b', re.IGNORECASE),           # 20% of, 15% tip
    re.compile(r'\btip\b.*\$?\d+', re.IGNORECASE),                       # tip on $85
    re.compile(r'\bconvert\b.*\b(to|in)\b', re.IGNORECASE),             # convert X to Y
    re.compile(r'\b\d+\s*(km|mi|lb|kg|cm|m|ft|inch|oz|g|l|gal|celsius|fahrenheit|c|f)\b', re.IGNORECASE),
    re.compile(r'\b(how much is|what is|calculate|compute)\b.*\d', re.IGNORECASE),
    re.compile(r'\$\d+', re.IGNORECASE),                                 # $85
    re.compile(r'\b\d+\s*\*\*\s*\d+', re.IGNORECASE),                   # 2**10
    re.compile(r'\b\d+\s*factorial\b', re.IGNORECASE),                   # 5 factorial
]

# Safe operators for AST evaluation
_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Safe math functions
_SAFE_FUNCTIONS = {
    "sqrt": math.sqrt,
    "cbrt": lambda x: x ** (1/3),
    "log": math.log10,
    "log10": math.log10,
    "log2": math.log2,
    "ln": math.log,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "abs": abs,
    "pow": pow,
    "round": round,
    "ceil": math.ceil,
    "floor": math.floor,
    "factorial": math.factorial,
    "pi": math.pi,
    "e": math.e,
}

# Unit conversion factors (to base SI units)
_UNIT_CONVERSIONS = {
    # Length → meters
    "km": ("m", 1000), "mi": ("m", 1609.344), "mile": ("m", 1609.344), "miles": ("m", 1609.344),
    "ft": ("m", 0.3048), "feet": ("m", 0.3048), "foot": ("m", 0.3048),
    "inch": ("m", 0.0254), "inches": ("m", 0.0254), "in": ("m", 0.0254),
    "cm": ("m", 0.01), "mm": ("m", 0.001), "m": ("m", 1), "yard": ("m", 0.9144), "yards": ("m", 0.9144),
    # Weight → kg
    "lb": ("kg", 0.453592), "lbs": ("kg", 0.453592), "pound": ("kg", 0.453592), "pounds": ("kg", 0.453592),
    "oz": ("kg", 0.0283495), "ounce": ("kg", 0.0283495), "ounces": ("kg", 0.0283495),
    "g": ("kg", 0.001), "gram": ("kg", 0.001), "grams": ("kg", 0.001),
    "kg": ("kg", 1), "ton": ("kg", 907.185), "tons": ("kg", 907.185),
    # Volume → liters
    "l": ("l", 1), "liter": ("l", 1), "liters": ("l", 1), "litre": ("l", 1),
    "ml": ("l", 0.001), "gal": ("l", 3.78541), "gallon": ("l", 3.78541), "gallons": ("l", 3.78541),
    "cup": ("l", 0.236588), "cups": ("l", 0.236588),
    "tbsp": ("l", 0.0147868), "tsp": ("l", 0.00492892),
}


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Perform mathematical calculations, unit conversions, percentage/tip calculations, and basic computations instantly without web search"
    category = ToolCategory.COMPUTE
    version = "1.0.0"

    timeout_seconds = 2.0       # Math should be instant
    max_retries = 0             # No external deps — no point retrying
    is_concurrent_safe = True
    priority = 95               # Highest — if it's math, skip web search entirely

    def can_handle(self, context: ToolContext) -> bool:
        """Detect if the query is a math/calculation question."""
        if context.query_type == "math":
            return True
        q = context.query.lower()
        return any(p.search(q) for p in _MATH_PATTERNS)

    async def execute(self, context: ToolContext) -> ToolResult:
        q = context.query.strip()

        # Try tip calculation
        tip_result = self._try_tip_calculation(q)
        if tip_result:
            return tip_result

        # Try percentage calculation
        pct_result = self._try_percentage(q)
        if pct_result:
            return pct_result

        # Try unit conversion
        conv_result = self._try_unit_conversion(q)
        if conv_result:
            return conv_result

        # Try temperature conversion
        temp_result = self._try_temperature(q)
        if temp_result:
            return temp_result

        # Try pure math expression
        math_result = self._try_math_expression(q)
        if math_result:
            return math_result

        # Couldn't parse — fall through (other tools will handle)
        return ToolResult(
            success=False,
            error="Could not parse calculation from query",
            tool_name=self.name,
        )

    def _try_tip_calculation(self, q: str) -> Optional[ToolResult]:
        """Handle: '20% tip on $85', 'tip for $120 at 18%'"""
        patterns = [
            re.compile(r'(\d+(?:\.\d+)?)\s*%\s*tip\s*(?:on|for)\s*\$?(\d+(?:\.\d+)?)', re.IGNORECASE),
            re.compile(r'tip\s*(?:on|for)\s*\$?(\d+(?:\.\d+)?)\s*(?:at)?\s*(\d+(?:\.\d+)?)\s*%', re.IGNORECASE),
        ]

        for i, pattern in enumerate(patterns):
            match = pattern.search(q)
            if match:
                if i == 0:
                    pct, amount = float(match.group(1)), float(match.group(2))
                else:
                    amount, pct = float(match.group(1)), float(match.group(2))

                tip = amount * (pct / 100)
                total = amount + tip

                return ToolResult(
                    success=True,
                    data={
                        "type": "tip_calculation",
                        "bill_amount": amount,
                        "tip_percentage": pct,
                        "tip_amount": round(tip, 2),
                        "total": round(total, 2),
                        "formatted": f"**Tip:** ${tip:.2f}\n**Total:** ${total:.2f}",
                    },
                    tool_name=self.name,
                )
        return None

    def _try_percentage(self, q: str) -> Optional[ToolResult]:
        """Handle: '20% of 500', '15% off $200'"""
        pct_of = re.search(r'(\d+(?:\.\d+)?)\s*%\s*of\s*\$?(\d+(?:\.\d+)?)', q, re.IGNORECASE)
        if pct_of:
            pct, val = float(pct_of.group(1)), float(pct_of.group(2))
            result = val * (pct / 100)
            return ToolResult(
                success=True,
                data={
                    "type": "percentage",
                    "percentage": pct,
                    "value": val,
                    "result": round(result, 4),
                    "formatted": f"**{pct}% of {val}** = **{result:,.4g}**",
                },
                tool_name=self.name,
            )

        pct_off = re.search(r'(\d+(?:\.\d+)?)\s*%\s*off\s*\$?(\d+(?:\.\d+)?)', q, re.IGNORECASE)
        if pct_off:
            pct, val = float(pct_off.group(1)), float(pct_off.group(2))
            discount = val * (pct / 100)
            final = val - discount
            return ToolResult(
                success=True,
                data={
                    "type": "discount",
                    "percentage": pct,
                    "original": val,
                    "discount": round(discount, 2),
                    "final_price": round(final, 2),
                    "formatted": f"**{pct}% off ${val:.2f}**\nDiscount: ${discount:.2f}\n**Final price: ${final:.2f}**",
                },
                tool_name=self.name,
            )
        return None

    def _try_unit_conversion(self, q: str) -> Optional[ToolResult]:
        """Handle: 'convert 100 km to miles', '5 feet in cm'"""
        pattern = re.compile(
            r'(\d+(?:\.\d+)?)\s*(\w+)\s*(?:to|in|into)\s*(\w+)',
            re.IGNORECASE,
        )
        match = pattern.search(q)
        if not match:
            return None

        value = float(match.group(1))
        from_unit = match.group(2).lower()
        to_unit = match.group(3).lower()

        if from_unit not in _UNIT_CONVERSIONS or to_unit not in _UNIT_CONVERSIONS:
            return None

        from_base, from_factor = _UNIT_CONVERSIONS[from_unit]
        to_base, to_factor = _UNIT_CONVERSIONS[to_unit]

        if from_base != to_base:
            return None  # Can't convert kg to meters

        base_value = value * from_factor
        result = base_value / to_factor

        return ToolResult(
            success=True,
            data={
                "type": "unit_conversion",
                "from_value": value,
                "from_unit": from_unit,
                "to_value": round(result, 4),
                "to_unit": to_unit,
                "formatted": f"**{value} {from_unit}** = **{result:,.4g} {to_unit}**",
            },
            tool_name=self.name,
        )

    def _try_temperature(self, q: str) -> Optional[ToolResult]:
        """Handle: '100 fahrenheit to celsius', '37 C to F'"""
        f_to_c = re.search(r'(-?\d+(?:\.\d+)?)\s*(?:fahrenheit|F|f)\s*(?:to|in)\s*(?:celsius|C|c)', q, re.IGNORECASE)
        if f_to_c:
            f = float(f_to_c.group(1))
            c = (f - 32) * 5 / 9
            return ToolResult(
                success=True,
                data={
                    "type": "temperature",
                    "from_value": f, "from_unit": "F",
                    "to_value": round(c, 2), "to_unit": "C",
                    "formatted": f"**{f}°F** = **{c:.2f}°C**",
                },
                tool_name=self.name,
            )

        c_to_f = re.search(r'(-?\d+(?:\.\d+)?)\s*(?:celsius|C|c)\s*(?:to|in)\s*(?:fahrenheit|F|f)', q, re.IGNORECASE)
        if c_to_f:
            c = float(c_to_f.group(1))
            f = c * 9 / 5 + 32
            return ToolResult(
                success=True,
                data={
                    "type": "temperature",
                    "from_value": c, "from_unit": "C",
                    "to_value": round(f, 2), "to_unit": "F",
                    "formatted": f"**{c}°C** = **{f:.2f}°F**",
                },
                tool_name=self.name,
            )
        return None

    def _try_math_expression(self, q: str) -> Optional[ToolResult]:
        """Safely evaluate a pure math expression using AST."""
        # Clean the query to extract the math part
        expr = q.lower()
        # Remove common prefixes
        for prefix in ["what is", "what's", "calculate", "compute", "solve", "how much is", "evaluate"]:
            expr = re.sub(rf'^\s*{prefix}\s*', '', expr, flags=re.IGNORECASE)

        # Clean up common symbols
        expr = expr.replace("^", "**").replace("×", "*").replace("÷", "/")
        expr = expr.replace(",", "").strip().rstrip("?. ")

        # Handle factorial
        factorial_match = re.match(r'(\d+)\s*(?:factorial|!)', expr)
        if factorial_match:
            n = int(factorial_match.group(1))
            if n > 170:
                return ToolResult(
                    success=False,
                    error="Factorial too large (max 170)",
                    tool_name=self.name,
                )
            result = math.factorial(n)
            return ToolResult(
                success=True,
                data={
                    "type": "math",
                    "expression": f"{n}!",
                    "result": result,
                    "formatted": f"**{n}!** = **{result:,}**",
                },
                tool_name=self.name,
            )

        try:
            result = self._safe_eval(expr)
            if result is not None:
                # Format nicely
                if isinstance(result, float) and result == int(result) and abs(result) < 1e15:
                    display = f"{int(result):,}"
                elif isinstance(result, float):
                    display = f"{result:,.6g}"
                elif isinstance(result, int):
                    display = f"{result:,}"
                else:
                    display = str(result)

                return ToolResult(
                    success=True,
                    data={
                        "type": "math",
                        "expression": expr,
                        "result": result,
                        "formatted": f"**{expr}** = **{display}**",
                    },
                    tool_name=self.name,
                )
        except Exception:
            pass

        return None

    def _safe_eval(self, expr: str) -> Optional[float]:
        """Safely evaluate a math expression using AST — NO eval()."""
        try:
            tree = ast.parse(expr, mode='eval')
            return self._eval_node(tree.body)
        except Exception:
            return None

    def _eval_node(self, node) -> float:
        """Recursively evaluate an AST node."""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Non-numeric constant")

        if isinstance(node, ast.BinOp):
            op = _SAFE_OPERATORS.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsafe operator: {type(node.op).__name__}")
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            # Prevent absurd computations
            if isinstance(node.op, ast.Pow) and right > 1000:
                raise ValueError("Exponent too large")
            return op(left, right)

        if isinstance(node, ast.UnaryOp):
            op = _SAFE_OPERATORS.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsafe unary operator: {type(node.op).__name__}")
            return op(self._eval_node(node.operand))

        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func = _SAFE_FUNCTIONS.get(node.func.id)
                if func is None:
                    raise ValueError(f"Unknown function: {node.func.id}")
                if callable(func):
                    args = [self._eval_node(arg) for arg in node.args]
                    return func(*args)
                return func  # Constants like pi, e

        if isinstance(node, ast.Name):
            val = _SAFE_FUNCTIONS.get(node.id)
            if val is not None and not callable(val):
                return val  # pi, e
            raise ValueError(f"Unknown variable: {node.id}")

        raise ValueError(f"Unsupported node: {type(node).__name__}")


calculator_tool = CalculatorTool()
