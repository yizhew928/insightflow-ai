"""Chinese reading notes derived from executed results and their validated operation."""
from decimal import Decimal
from numbers import Integral, Real

import pandas as pd


FIELD_NAMES = {
    "revenue": "销售额", "profit": "利润", "cost": "成本", "quantity": "数量",
    "unit_price": "单价", "unit_cost": "单位成本", "category": "品类", "product": "商品",
    "date": "日期", "customer_id": "客户编号", "stock_on_hand": "库存数量",
    "reorder_level": "补货点", "region": "地区", "segment": "客户分群", "order_id": "订单编号",
}
OPERATIONS = {"sum": "合计", "avg": "平均值", "min": "最小值", "max": "最大值"}


def _missing(value):
    return pd.api.types.is_scalar(value) and pd.isna(value)


def _value(value):
    if _missing(value):
        return "空值"
    if isinstance(value, Integral) and not isinstance(value, bool):
        return format(value, ",d")
    if isinstance(value, (Real, Decimal)) and not isinstance(value, bool):
        number = Decimal(str(value))
        if number.is_finite():
            if number and not -5 <= number.adjusted() < 16:
                return format(number.normalize(), "E")
            text = format(number, ",.6f")
            return text.rstrip("0").rstrip(".") if "." in text else text
    text = str(value)
    return text if len(text) <= 80 else text[:77] + "…"


def _ranking(frame, group, metric, label):
    valid = frame.dropna(subset=[metric])
    if valid.empty:
        return [f"返回的各组均缺少可计算的{label}，无法排序。"]
    highest = valid[metric].max()
    winners = valid.loc[valid[metric] == highest, group]
    names = "、".join(f"「{_value(name)}」" for name in winners.head(3))
    if len(winners) > 3:
        names += f"等 {len(winners)} 组"
    if len(valid) == 1:
        return [f"在已返回的结果中，{names}的{label}为 {_value(highest)}。"]
    rank = "并列最高" if len(winners) > 1 else "最高"
    text = f"在已返回的结果中，{names}的{label}{rank}，为 {_value(highest)}。"
    if len(winners) == 1:
        runner_up = valid[metric][valid[metric] < highest].max()
        second = valid.loc[valid[metric] == runner_up, group]
        if len(second) == 1:
            text += f"其次是「{_value(second.iloc[0])}」，为 {_value(runner_up)}。"
        else:
            text += f"另有 {len(second)} 组并列第二，为 {_value(runner_up)}。"
    return [text]


def _question(analysis):
    result, plan = analysis["result"], analysis["plan"]
    operation, metric, group = plan["operation"], plan["metric"], plan["group_by"]
    field = FIELD_NAMES.get(metric, f"「{metric}」")
    label = "记录数" if operation == "count" else field + OPERATIONS[operation]
    if group is None:
        value = result.iat[0, 0]
        if operation == "count":
            return [f"当前工作表共有 {_value(value)} 行记录。计数包含字段为空的行。"]
        if _missing(value):
            if analysis["valid_values"] == 0:
                return [f"当前工作表没有可计算的{field}数值，{label}为空。"]
            return [f"当前工作表的{label}未得到有效数值，请核对源列。"]
        return [f"当前工作表的{label}为 {_value(value)}。",
                f"计算使用了 {analysis['source_rows']:,} 行记录中 {analysis['valid_values']:,} 个非空的{field}值。"]
    if result.empty:
        return ["当前工作表没有记录，无法比较分组。"]
    by = FIELD_NAMES.get(group, f"「{group}」")
    lines = [f"将当前工作表按{by}分组计算{label}，本次返回 {len(result):,} 组。"]
    lines.extend(_ranking(result, "group_key", "value", label))
    if len(result) == plan["limit"]:
        lines.append(f"本次最多显示 {plan['limit']} 组，排名与并列情况仅描述表中可见的组。")
    elif operation == "sum" and result["value"].notna().all() and (result["value"] >= 0).all():
        total = sum(Decimal(str(v)) for v in result["value"])
        if total.is_finite() and total > 0 and len(result) > 1:
            share = Decimal(str(result["value"].max())) / total
            lines.append(f"各组{field}加总为 {_value(total)}，最高单组占合计的 {share:.2%}。")
    return lines


def _business(template, result):
    if template == "profit":
        revenue, profit, margin = result.iloc[0][["revenue", "profit", "profit_margin"]]
        return [f"销售额合计为 {_value(revenue)}，利润合计为 {_value(profit)}。",
                "缺少有效的销售额或利润，或销售额合计为零，利润率无法计算。"
                if _missing(margin) else f"用利润合计除以销售额合计，得到利润率 {margin:.2%}。"]
    if template == "sales" and "period" not in result:
        row = result.iloc[0]
        return [f"本表共 {_value(row['records'])} 行记录，销售额合计为 {_value(row['revenue'])}。",
                "销售额合计仅计入可转为数值的销售额。"]
    if result.empty:
        return ["当前工作表没有记录，本次分析没有可解读的结果。"]
    if template == "inventory":
        flags = result["reorder_needed"]
        lines = [f"已返回 {len(result):,} 条库存记录。其中 {int(flags.sum()):,} 条的库存数量已达到或低于补货点。"]
        flagged = result.loc[flags.fillna(False)]
        if len(flagged):
            row = flagged.iloc[0]
            lines.append(f"例如「{_value(row['product'])}」库存为 {_value(row['stock_on_hand'])}，补货点为 {_value(row['reorder_level'])}。")
        if flags.isna().any():
            lines.append(f"有 {int(flags.isna().sum()):,} 条记录缺少可比较的库存数量或补货点。")
    else:
        group, by = ("period", "日期值") if template == "sales" else ("customer_id", "客户编号")
        lines = [f"按{by}汇总销售额，本次返回 {len(result):,} 个分组。"]
        lines.extend(_ranking(result, group, "revenue", "销售额合计"))
    if len(result) == 1000:
        lines.append("结果已达到 1,000 行展示上限，此处仅解读已返回的记录。")
    return lines


def explain_result(analysis) -> list[str]:
    """Return plain-text paragraphs. Renderers escape any data-derived text at display."""
    result = analysis["result"]
    if "plan" in analysis:
        return _question(analysis)
    if analysis.get("template") in ("sales", "profit", "inventory", "customers"):
        return _business(analysis["template"], result)
    if result.empty:
        return ["查询已执行，没有返回记录。"]
    if result.shape == (1, 1):
        return [f"查询返回一个值，字段「{result.columns[0]}」的结果为 {_value(result.iat[0, 0])}。"]
    lines = [f"本次查询返回 {len(result):,} 行、{len(result.columns):,} 列。"]
    numeric = result.select_dtypes(include="number")
    if len(numeric.columns):
        series = numeric.iloc[:, 0].dropna()
        if series.empty:
            lines.append(f"字段「{numeric.columns[0]}」在这些行中均为空值。")
        else:
            lines.append(f"在这些行中，字段「{series.name}」的最小值是 {_value(series.min())}，最大值是 {_value(series.max())}。")
    else:
        first = result.iloc[0, 0]
        lines.append(f"第一行中，字段「{result.columns[0]}」为「{_value(first)}」。")
    if len(result) == 1000:
        lines.append("结果已达到 1,000 行展示上限，上述描述仅覆盖返回的行。")
    return lines
