"""Plan a single-sheet aggregate and execute only SQL compiled by this module."""
from __future__ import annotations

import re

import pandas as pd
from pandas.api import types as dt

from .sql import run_query
from .explanations import explain_result


class UnsupportedQuestion(ValueError):
    """The question cannot be mapped to a supported aggregate safely."""


ALIASES = {
    "revenue": ("sales revenue", "sales", "销售额", "营收", "收入"),
    "profit": ("利润",), "cost": ("成本",), "quantity": ("销量", "销售数量", "数量"),
    "unit_price": ("unit price", "单价"), "unit_cost": ("unit cost", "单位成本"),
    "category": ("categories", "类别", "品类", "分类"),
    "product": ("products", "产品", "商品"), "date": ("日期",),
    "customer_id": ("customer id", "客户编号", "客户ID"),
    "stock_on_hand": ("stock on hand", "库存数量", "库存量"),
    "reorder_level": ("reorder level", "补货点"), "region": ("地区",),
    "segment": ("客户分群",), "order_id": ("order id", "订单编号"),
}
OPERATIONS = {
    "sum": ("total", "sum", "合计", "总计", "总", "汇总"),
    "avg": ("average", "mean", "avg", "平均", "平均值"),
    "min": ("minimum", "min", "lowest", "最小", "最低"),
    "max": ("maximum", "max", "highest", "最大", "最高"),
}
REFUSAL = "Unsupported question / 暂不支持此问法。Try ‘How many rows?’ or an aggregate with exact column names."
# Qualifiers outside the plan language must not disappear from a model proposal.
EXTRA_SEMANTICS = re.compile(
    r"\b(where|when|filter(?:ed)?|between|since|before|after|except|excluding|exclude|"
    r"only|with|without|for|during|from|in|last|this|per month|per year|per week|"
    r"weekly|monthly|yearly|quarterly|daily|distinct|unique|median|ratio|rate|margin|"
    r"percentage|percent|change|growth|difference|trend|compare|versus|and|or|minus|"
    r"bottom|ascending|less than|greater than|over|under|nonzero)\b|"
    r"(?:其中|筛选|仅|除了|排除|大于|小于|超过|低于|高于|去年|今年|上月|本月|上周|"
    r"今天|昨天|月份|每月|按月|每周|按周|每年|按年|季度|去重|不同|中位|比率|占比|"
    r"增长|变化|同比|环比|趋势|比较|以及|并且|最低的|倒数)|[<>=％%]|\b(?:19|20)\d{2}\b",
    re.IGNORECASE,
)


def _canonical(text):
    return re.sub(r"\s+", " ", text.strip()).casefold()


def _field(words, columns):
    """Resolve full column tokens only. Do not discard unknown qualifiers."""
    words = words.strip()
    if len(words) > 1 and words[0] == words[-1] and words[0] in ('"', '`'):
        words = words[1:-1]
    key = _canonical(words)
    direct = [col for col in columns if _canonical(col) == key]
    if len(direct) == 1:
        return direct[0]
    matches = [col for col in columns if key in
               {_canonical(a) for a in ALIASES.get(_canonical(col), ())}]
    if len(matches) == 1 and not direct:
        return matches[0]
    raise UnsupportedQuestion(REFUSAL)


def _aggregate(phrase, columns, *, implicit_sum=False):
    phrase = phrase.strip()
    if re.fullmatch(r"(?:how many rows|count(?: of)? (?:all )?rows|row count|number of rows|"
                    r"有多少行|一共有多少行|共有多少行|多少行|行数|总行数|记录数)", phrase, re.I):
        return {"operation": "count"}
    # A combined multilingual field name and operator must match the entire phrase.
    for operation, names in OPERATIONS.items():
        for name in sorted(names, key=len, reverse=True):
            if name.isascii():
                match = re.fullmatch(re.escape(name) + r"\s+(?:of\s+)?(.+)", phrase, re.I)
            else:
                match = re.fullmatch(re.escape(name) + r"(.+)", phrase)
                if not match:
                    match = re.fullmatch(r"(.+?)(?:的)?" + re.escape(name), phrase)
            if match:
                try:
                    return {"operation": operation, "metric": _field(match[1], columns)}
                except UnsupportedQuestion:
                    continue
    if implicit_sum:
        return {"operation": "sum", "metric": _field(phrase, columns)}
    raise UnsupportedQuestion(REFUSAL)


def _rules(question, columns):
    words = re.sub(r"[?？。.!！]+$", "", question.strip()).strip()
    words = re.sub(r"^(?:what is (?:the )?|show (?:me )?(?:the )?)", "", words, flags=re.I)
    words = re.sub(r"(?:是多少|是什么)$", "", words).strip()
    rank = re.fullmatch(r"top\s+(\d{1,3})\s+(.+?)\s+by\s+(.+)", words, re.I)
    if rank:
        return {**_aggregate(rank[3], columns, implicit_sum=True),
                "group_by": _field(rank[2], columns), "limit": int(rank[1])}
    rank_zh = re.fullmatch(r"按(.+?)(?:排名)?前\s*(\d{1,3})\s*(?:个|名)?(?:的)?(.+)", words)
    if rank_zh:
        return {**_aggregate(rank_zh[1], columns, implicit_sum=True),
                "group_by": _field(rank_zh[3], columns), "limit": int(rank_zh[2])}
    grouped = re.fullmatch(r"(.+?)\s+by\s+(.+)", words, re.I)
    if grouped:
        return {**_aggregate(grouped[1], columns, implicit_sum=True),
                "group_by": _field(grouped[2], columns)}
    grouped = re.fullmatch(r"按(.+?)(?:分组)?(?:统计|汇总|计算)(.+)", words)
    if grouped:
        return {**_aggregate(grouped[2], columns, implicit_sum=True),
                "group_by": _field(grouped[1], columns)}
    return _aggregate(words, columns)


def _checked_plan(frame, plan):
    if not isinstance(plan, dict) or set(plan) - {"operation", "metric", "group_by", "limit"}:
        raise UnsupportedQuestion(REFUSAL)
    op = plan.get("operation")
    if not isinstance(op, str) or op not in (*OPERATIONS, "count"):
        raise UnsupportedQuestion(REFUSAL)
    metric, group = plan.get("metric"), plan.get("group_by")
    if op == "count":
        if metric is not None:
            raise UnsupportedQuestion("Row count takes no metric column.")
    else:
        if not isinstance(metric, str) or metric not in frame.columns:
            raise UnsupportedQuestion("The selected metric does not exist on this sheet.")
        dtype = frame[metric].dtype
        if not (dt.is_integer_dtype(dtype) or dt.is_float_dtype(dtype)):
            raise UnsupportedQuestion("The selected metric must be a numeric column.")
    if group is not None and (not isinstance(group, str) or group not in frame.columns):
        raise UnsupportedQuestion("The grouping column does not exist on this sheet.")
    limit = plan.get("limit")
    if limit is not None and (group is None or type(limit) is not int or not 1 <= limit <= 100):
        raise UnsupportedQuestion("Ranking needs a grouping column and a limit of 1–100.")
    return op, metric, group, limit if limit is not None else (100 if group is not None else None)


def _quoted(name):
    # All identifiers must already be exact, validated frame columns.
    return '"' + name.replace('"', '""') + '"'


def ask(frame, question, planner=None):
    """Execute a rules or model-planned analysis. Planner receives column names and dtypes only."""
    if not isinstance(question, str) or not 0 < len(question.strip()) <= 500:
        raise UnsupportedQuestion("Enter a question of 1–500 characters.")
    columns = list(frame.columns)
    if not all(isinstance(c, str) and c and '\0' not in c for c in columns):
        raise UnsupportedQuestion("Columns must have non-empty text names.")
    if len({_canonical(c) for c in columns}) != len(columns):
        raise UnsupportedQuestion("Column names must be distinct, including case and spacing.")
    try:
        rules = _rules(question, columns)
    except UnsupportedQuestion:
        rules = None
    if planner is None:
        if rules is None:
            raise UnsupportedQuestion(REFUSAL)
        spec = _checked_plan(frame, rules)
        mode = "Local rules"
    else:
        if rules is None and EXTRA_SEMANTICS.search(question):
            raise UnsupportedQuestion(REFUSAL)
        schema = {col: str(dtype) for col, dtype in frame.dtypes.items()}
        spec = _checked_plan(frame, planner(question, schema))
        if rules is not None and spec != _checked_plan(frame, rules):
            raise UnsupportedQuestion("The proposed interpretation disagrees with the explicit question.")
        mode = "Language model"
    op, metric, group, limit = spec
    aggregate = "COUNT(*)" if op == "count" else f"{op.upper()}({_quoted(metric)})"
    notes = [f"Computed {aggregate} on the selected sheet. " +
             ("Row count includes every row." if op == "count" else "Blank metric values are excluded.")]
    if group is None:
        sql = f"SELECT {aggregate} AS value FROM data"
    else:
        sql = (f"SELECT {_quoted(group)} AS group_key, {aggregate} AS value FROM data "
               f"GROUP BY 1 ORDER BY 2 DESC NULLS LAST, 1 ASC NULLS LAST LIMIT {limit}")
        notes.append(f"Grouped by {group}, including a blank group if present. Showing up to "
                     f"{limit} groups by decreasing value; ties use ascending group order.")
    result = run_query({"data": frame}, sql)
    analysis = {"title": question.strip(), "sql": sql, "result": result,
                "formulas": notes, "mode": mode, "source_rows": len(frame),
                "plan": {"operation": op, "metric": metric, "group_by": group, "limit": limit}}
    if metric is not None:
        analysis["valid_values"] = int(frame[metric].count())
    analysis["explanation"] = explain_result(analysis)
    return analysis
