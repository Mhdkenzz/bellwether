"""A small, safe expression evaluator for config-defined formulas.

Used for segment definitions, scenario metrics and optional trait rules.
Supports arithmetic, comparisons, boolean logic, `a if c else b`, dict/attribute
access, list literals and calls to whitelisted functions. Nothing else.
"""

from __future__ import annotations

import ast
import math
import operator
from functools import lru_cache
from typing import Any, Callable, Mapping

_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: lambda a, b: a / b if b else 0.0,
    ast.FloorDiv: lambda a, b: a // b if b else 0.0,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Not: operator.not_}
_CMP = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

BASE_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "sum": sum,
    "len": len,
    "sqrt": math.sqrt,
    "log": math.log,
    "exp": math.exp,
    "clamp": lambda x, lo=0.0, hi=1.0: max(lo, min(hi, x)),
    "mean": lambda xs: (sum(xs) / len(xs)) if xs else 0.0,
}


class ExprError(ValueError):
    pass


@lru_cache(maxsize=1024)
def compile_expr(source: str) -> ast.Expression:
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as e:
        raise ExprError(f"invalid expression {source!r}: {e.msg}") from None
    for node in ast.walk(tree):
        if isinstance(node, (ast.Lambda, ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp, ast.Starred, ast.NamedExpr)):
            raise ExprError(f"{type(node).__name__} is not allowed in {source!r}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ExprError(f"private attribute access is not allowed in {source!r}")
    return tree


def evaluate(source: str, env: Mapping[str, Any], functions: Mapping[str, Callable[..., Any]] | None = None) -> Any:
    funcs = {**BASE_FUNCTIONS, **(functions or {})}
    return _eval(compile_expr(source).body, env, funcs, source)


def _eval(node: ast.AST, env: Mapping[str, Any], funcs: Mapping[str, Callable[..., Any]], src: str) -> Any:
    match node:
        case ast.Constant(value=v):
            return v
        case ast.Name(id=name):
            if name in env:
                return env[name]
            if name in ("True", "False", "None"):
                return {"True": True, "False": False, "None": None}[name]
            raise ExprError(f"unknown name {name!r} in {src!r}")
        case ast.BinOp(left=l, op=op, right=r):
            return _BIN[type(op)](_eval(l, env, funcs, src), _eval(r, env, funcs, src))
        case ast.UnaryOp(op=op, operand=o):
            return _UNARY[type(op)](_eval(o, env, funcs, src))
        case ast.BoolOp(op=ast.And(), values=vals):
            result: Any = True
            for v in vals:
                result = _eval(v, env, funcs, src)
                if not result:
                    return result
            return result
        case ast.BoolOp(op=ast.Or(), values=vals):
            result = False
            for v in vals:
                result = _eval(v, env, funcs, src)
                if result:
                    return result
            return result
        case ast.Compare(left=l, ops=ops, comparators=comps):
            left = _eval(l, env, funcs, src)
            for op, comp in zip(ops, comps):
                right = _eval(comp, env, funcs, src)
                if not _CMP[type(op)](left, right):
                    return False
                left = right
            return True
        case ast.IfExp(test=t, body=b, orelse=o):
            return _eval(b, env, funcs, src) if _eval(t, env, funcs, src) else _eval(o, env, funcs, src)
        case ast.Attribute(value=v, attr=attr):
            obj = _eval(v, env, funcs, src)
            if isinstance(obj, Mapping):
                if attr not in obj:
                    raise ExprError(f"no key {attr!r} in {src!r}")
                return obj[attr]
            raise ExprError(f"attribute access on {type(obj).__name__} is not allowed in {src!r}")
        case ast.Subscript(value=v, slice=s):
            obj = _eval(v, env, funcs, src)
            key = _eval(s, env, funcs, src)
            if isinstance(obj, (Mapping, list, tuple)):
                return obj[key]
            raise ExprError(f"indexing {type(obj).__name__} is not allowed in {src!r}")
        case ast.List(elts=elts) | ast.Tuple(elts=elts):
            return [_eval(e, env, funcs, src) for e in elts]
        case ast.Call(func=ast.Name(id=fname), args=args, keywords=kws):
            if fname not in funcs:
                raise ExprError(f"unknown function {fname!r} in {src!r}")
            return funcs[fname](
                *[_eval(a, env, funcs, src) for a in args],
                **{k.arg: _eval(k.value, env, funcs, src) for k in kws if k.arg},
            )
    raise ExprError(f"{type(node).__name__} is not allowed in {src!r}")
