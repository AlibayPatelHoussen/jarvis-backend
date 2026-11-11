"""
tools/calculator.py
===================
Calculatrice sécurisée pour Jarvis.

Pourquoi ast et pas eval() ?
eval() exécute n'importe quel code Python.
ast.parse() analyse la syntaxe sans l'exécuter.
On vérifie ensuite que l'expression ne contient
que des opérations mathématiques autorisées.

Opérations supportées :
- Addition       : 2 + 3
- Soustraction   : 10 - 4
- Multiplication : 3 * 7
- Division       : 15 / 3
- Puissance      : 2 ** 8
- Modulo         : 10 % 3
- Parenthèses    : (2 + 3) * 4
"""

import ast
import math
import operator


# Opérations binaires autorisées
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}

# Opérations unaires autorisées (-x, +x)
SAFE_UNARY = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


class CalculatorError(Exception):
    """Erreur spécifique à la calculatrice."""
    pass


class Calculator:
    """
    Calculatrice sécurisée basée sur ast.

    Usage :
        calc = Calculator()
        result = calc.evaluate("2 + 3 * 4")
        print(result)  # 14.0
    """

    def evaluate(self, expression: str) -> float:
        """
        Évalue une expression mathématique.

        Args:
            expression : Expression en string ("2 + 3 * 4")

        Returns:
            Résultat en float

        Raises:
            CalculatorError : Si l'expression est invalide
                              ou contient du code dangereux
        """
        expression = expression.strip()
        if not expression:
            raise CalculatorError("Expression vide.")

        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError:
            raise CalculatorError(
                f"Expression invalide : '{expression}'"
            )

        try:
            result = self._eval_node(tree.body)
        except OverflowError:
            raise CalculatorError("Résultat trop grand.")
        except RecursionError:
            raise CalculatorError("Expression trop complexe.")

        # Ex : (-8) ** (1/3) donne un nombre complexe en Python
        if isinstance(result, complex):
            raise CalculatorError("Résultat non réel (nombre complexe).")
        # Ex : 1e308 * 10 donne l'infini sans lever d'erreur
        if not math.isfinite(result):
            raise CalculatorError("Résultat trop grand.")
        return result

    def _eval_node(self, node: ast.AST) -> float:
        """
        Évalue récursivement un nœud AST.

        Seuls les types de nœuds mathématiques
        sont autorisés. Tout autre type lève une erreur.
        """
        # Nombre (3, 3.14, etc.)
        if isinstance(node, ast.Constant):
            # bool est une sous-classe de int : True + 1 serait accepté
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return float(node.value)
            raise CalculatorError(
                f"Type non autorisé : {type(node.value)}"
            )

        # Opération binaire (a + b, a * b, etc.)
        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in SAFE_OPERATORS:
                raise CalculatorError(
                    f"Opérateur non autorisé : {op_type.__name__}"
                )
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)

            # Vérifier la division par zéro (/, // et %)
            if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
                raise CalculatorError("Division par zéro impossible.")

            return SAFE_OPERATORS[op_type](left, right)

        # Opération unaire (-x, +x)
        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in SAFE_UNARY:
                raise CalculatorError(
                    f"Opérateur unaire non autorisé : {op_type.__name__}"
                )
            operand = self._eval_node(node.operand)
            return SAFE_UNARY[op_type](operand)

        raise CalculatorError(
            f"Expression non autorisée : {type(node).__name__}"
        )

    def format_result(self, result: float) -> str:
        """
        Formate le résultat pour l'affichage.

        Supprime le .0 si le résultat est un entier.
        Ex: 6.0 → "6", 3.14 → "3.14"
        """
        if not math.isfinite(result):
            return str(result)
        if result == int(result):
            return str(int(result))
        return str(round(result, 10))
