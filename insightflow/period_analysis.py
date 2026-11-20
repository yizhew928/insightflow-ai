"""Same-period sales comparisons over the selected sheet, with executable SQL evidence."""
from datetime import date, timedelta
import json

import duckdb
import pandas as pd


# Inclusive starting month and number of months.
PERIODS = {"H1": (1, 6), "H2": (7, 6), "FY": (1, 12),
           "Q1": (1, 3), "Q2": (4, 3), "Q3": (7, 3), "Q4": (10, 3)}
CONTRIBUTION_FIELDS = ["name", "prev_revenue", "curr_revenue", "delta_revenue",
                       "prev_profit", "curr_profit", "delta_profit"]


def _windows(year, period):
    if type(year) is not int or not 2 <= year <= 9998:
        raise ValueError("比较年份应为 2–9998 之间的整数。")
    if not isinstance(period, str) or period not in PERIODS:
        raise ValueError("请选择 H1、H2、FY 或 Q1–Q4。")
    start, length = PERIODS[period]
    windows = {}
    for key, y in (("previous", year - 1), ("current", year)):
        end = start + length
        windows[key] = (date(y, start, 1), date(y + (end - 1) // 12, (end - 1) % 12 + 1, 1),
                        [f"{y:04d}-{m:02d}" for m in range(start, end)])
    return windows


def _check_columns(frame, group_by):
    if group_by not in ("product", "category"):
        raise ValueError("贡献拆解只支持 product 或 category。")
    fields = ["date", "revenue", "profit", group_by]
    missing = [field for field in fields if list(frame.columns).count(field) != 1]
    if missing:
        raise ValueError("需要唯一且已映射的列：" + "、".join(missing))
    return frame.loc[:, fields]


def _validate_values(conn, group_by):
    # Use decimal money throughout the SQL pipeline; never round unsupported source amounts
    # or reinterpret numeric Excel serials as calendar dates. Blanks make the total unknown.
    numeric_pattern = r"[+-]?(?:[0-9]+(?:\.[0-9]{1,6})?|\.[0-9]{1,6})"
    checks = [
        ("date", """TRY_CAST("date" AS DATE) IS NULL OR
         NOT regexp_full_match(trim(CAST("date" AS VARCHAR)), '[0-9]{4}-[0-9]{2}-[0-9]{2}([ T][0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?)?')"""),
        (group_by, f'"{group_by}" IS NULL OR length(trim(CAST("{group_by}" AS VARCHAR))) = 0'),
    ]
    for col in ("revenue", "profit"):
        checks.append((col, f"""TRY_CAST("{col}" AS DECIMAL(30,6)) IS NULL OR
          NOT regexp_full_match(trim(CAST("{col}" AS VARCHAR)), '{numeric_pattern}')"""))
    sql = "SELECT " + ", ".join(f"COUNT(*) FILTER (WHERE {invalid})" for _, invalid in checks) + " FROM data"
    counts = conn.execute(sql).fetchone()
    issues = [f"{col}（{count} 行）" for (col, _), count in zip(checks, counts) if count]
    if issues:
        raise ValueError("字段存在空值或无效值：" + "、".join(issues)
                         + "。日期使用 YYYY-MM-DD；金额需为有限十进制数，最多六位小数。")


def _query(windows, group_by, selected_product):
    period_rows = ",\n    ".join(
        f"('{key}', DATE '{start.isoformat()}', DATE '{end.isoformat()}')"
        for key, (start, end, _) in windows.items())
    fields = ["rows", "months", "revenue", "profit", "margin", "company_margin", "revenue_share", "profit_share"]
    selected = ",\n       ".join(f"p.{col} AS prev_{col}, c.{col} AS curr_{col}" for col in fields)
    restriction = "" if selected_product is None else "\n  AND (c.is_total = 1 OR c.name = ?)"
    return f"""WITH periods(bucket, starts, ends) AS (VALUES
    {period_rows}
), scoped AS (
    SELECT w.bucket, CAST(d."{group_by}" AS VARCHAR) AS name, CAST(d."date" AS DATE) AS day,
           CAST(d.revenue AS DECIMAL(30,6)) AS revenue, CAST(d.profit AS DECIMAL(30,6)) AS profit
    FROM data d JOIN periods w ON CAST(d."date" AS DATE) >= w.starts AND CAST(d."date" AS DATE) < w.ends
), stats AS (
    SELECT bucket, GROUPING(name) AS is_total, name, COUNT(*) AS rows,
           LIST(DISTINCT strftime(day, '%Y-%m') ORDER BY strftime(day, '%Y-%m')) AS months,
           SUM(revenue) AS revenue, SUM(profit) AS profit
    FROM scoped GROUP BY GROUPING SETS ((bucket), (bucket, name))
), entities AS (
    SELECT DISTINCT 0 AS is_total, name FROM scoped
    UNION ALL SELECT 1, NULL
), aligned AS (
    SELECT e.is_total, e.name, w.bucket, COALESCE(s.rows, 0) AS rows, s.months,
           CASE WHEN totals.rows > 0 THEN COALESCE(s.revenue, 0) END AS revenue,
           CASE WHEN totals.rows > 0 THEN COALESCE(s.profit, 0) END AS profit,
           totals.revenue AS company_revenue, totals.profit AS company_profit
    FROM entities e CROSS JOIN periods w
    LEFT JOIN stats s ON s.bucket = w.bucket AND s.is_total = e.is_total
                      AND s.name IS NOT DISTINCT FROM e.name
    LEFT JOIN stats totals ON totals.bucket = w.bucket AND totals.is_total = 1
), measures AS (
    SELECT *, CASE WHEN revenue > 0 THEN profit / revenue END AS margin,
           CASE WHEN company_revenue > 0 THEN company_profit / company_revenue END AS company_margin,
           CASE WHEN company_revenue > 0 THEN revenue / company_revenue END AS revenue_share,
           CASE WHEN company_profit > 0 THEN profit / company_profit END AS profit_share
    FROM aligned
)
SELECT c.name, c.is_total, {selected},
       c.revenue - p.revenue AS delta_revenue, c.profit - p.profit AS delta_profit,
       CASE WHEN p.revenue > 0 THEN (c.revenue - p.revenue) / p.revenue END AS revenue_growth,
       CASE WHEN p.profit > 0 THEN (c.profit - p.profit) / p.profit END AS profit_growth,
       100 * (c.margin - p.margin) AS margin_pp
FROM measures c JOIN measures p ON c.is_total = p.is_total AND c.name IS NOT DISTINCT FROM p.name
WHERE c.bucket = 'current' AND p.bucket = 'previous'{restriction}
ORDER BY c.is_total DESC, delta_revenue DESC NULLS LAST, c.name ASC"""


def _number(value):
    return None if value is None else float(value)


def _summary(record, prefix):
    return {
        "rows": record[prefix + "rows"], "months": record[prefix + "months"] or [],
        **{key: _number(record[prefix + key]) for key in
           ("revenue", "profit", "margin", "company_margin", "revenue_share", "profit_share")}
    }


def _analyze(frame, year, period, group_by, product):
    windows = _windows(year, period)
    source = _check_columns(frame, group_by)
    query = _query(windows, group_by, product)
    params = [] if product is None else [product]
    with duckdb.connect(":memory:", config={"enable_external_access":"false", "threads":"2",
                                            "memory_limit":"512MB"}) as conn:
        conn.register("data", source)
        _validate_values(conn, group_by)
        cursor = conn.execute(query, params)
        names = [desc[0] for desc in cursor.description]
        records = [dict(zip(names, row)) for row in cursor.fetchall()]

    total = records[0]
    selected = total
    if product is not None:
        if len(records) < 2:
            raise ValueError("所选商品在这两个期间均无记录：" + product)
        selected = records[1]

    warnings = []
    output = {"year":year, "period":period, "group_by":group_by, "warnings":warnings,
              "sql":query, "sql_params":params, "product":product}
    if params:
        output["sql"] = "-- 绑定参数 ? = " + json.dumps(params[0], ensure_ascii=False) + "\n" + query
    for key, prefix in (("previous", "prev_"), ("current", "curr_")):
        start, end, expected = windows[key]
        label = f"{start.isoformat()} 至 {(end - timedelta(days=1)).isoformat()}"
        company = _summary(total, prefix)
        summary = _summary(selected, prefix)
        summary["company_months"] = company["months"]
        output[key], output[key + "_label"] = summary, label
        missing = [month for month in expected if month not in company["months"]]
        if len(missing) == len(expected):
            warnings.append(f"{label}：整期无数据，金额与跨期变化不可用。")
        elif missing:
            warnings.append(f"{label}：工作表缺少月份 {'、'.join(missing)}；仅汇总已记录交易，比较口径可能不完整。")
        elif product is not None and not summary["rows"]:
            warnings.append(f"{label}：工作表有交易，所选商品无记录，商品金额按 0 计。")
    output["changes"] = {key:_number(selected[col]) for key, col in (
        ("revenue_delta","delta_revenue"), ("profit_delta","delta_profit"),
        ("revenue_growth","revenue_growth"), ("profit_growth","profit_growth"), ("margin_pp","margin_pp"))}
    for metric, label in (("revenue", "销售额"), ("profit", "利润")):
        baseline = output["previous"][metric]
        if baseline is not None and baseline <= 0:
            warnings.append(f"上期{label}为零或负数，仅展示变化额，不计算同比增长率。")
    if product is None:
        rows = [[rec["name"], *[_number(rec[k]) for k in CONTRIBUTION_FIELDS[1:]]] for rec in records[1:]]
        output["contributions"] = pd.DataFrame(rows, columns=CONTRIBUTION_FIELDS)
    return output


def compare_sales(frame, year, period, group_by="product"):
    """Aggregate the selected calendar interval against the identical interval one year earlier."""
    return _analyze(frame, year, period, group_by, None)


def drilldown(frame, year, period, product):
    """Look up a product in the same two windows, using period-specific company denominators."""
    if not isinstance(product, str) or not product.strip():
        raise ValueError("请选择一个有效商品。")
    return _analyze(frame, year, period, "product", product)
