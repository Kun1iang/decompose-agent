"""数据分析域的工具集：销售查询、退款查询、投诉查询。"""

from langchain_core.tools import tool

from agent_starter.tasks.analytics.data import (
    COMPLAINT_DATA,
    PRODUCTS,
    REFUND_DATA,
    SALES_DATA,
)


def _product_name(pid: str) -> str:
    return PRODUCTS.get(pid, {}).get("name", pid)


@tool
def search_sales(product_id: str = "", month: str = "") -> str:
    """
    查询产品销售数据（订单量、收入）。可按产品ID或月份筛选，留空则返回全部。

    参数：
    - product_id: 产品ID（prod_a/prod_b/prod_c），留空查全部
    - month: 月份（如 2025-06），留空查全部月份
    """
    results = []
    for row in SALES_DATA:
        if product_id and row["product_id"] != product_id:
            continue
        if month and row["month"] != month:
            continue
        results.append(row)

    if not results:
        return "未找到匹配的销售数据。"

    # 汇总
    total_orders = sum(r["orders"] for r in results)
    total_revenue = sum(r["revenue"] for r in results)
    lines = [f"销售数据（共 {len(results)} 条记录）："]
    for r in results:
        lines.append(f"  {r['month']} | {_product_name(r['product_id'])} | 订单{r['orders']}笔 | 收入{r['revenue']:,}元")
    lines.append(f"  合计：{total_orders}笔订单，{total_revenue:,}元")
    return "\n".join(lines)


@tool
def search_refunds(product_id: str = "", month: str = "") -> str:
    """
    查询退款数据（退款笔数、金额、原因）。可按产品ID或月份筛选。

    参数：
    - product_id: 产品ID，留空查全部
    - month: 月份，留空查全部月份
    """
    results = []
    for row in REFUND_DATA:
        if product_id and row["product_id"] != product_id:
            continue
        if month and row["month"] != month:
            continue
        results.append(row)

    if not results:
        return "未找到匹配的退款数据。"

    total_count = sum(r["refund_count"] for r in results)
    total_amount = sum(r["refund_amount"] for r in results)

    # 统计原因分布
    from collections import Counter
    reason_dist = Counter()
    for r in results:
        reason_dist[r["reason"]] += r["refund_count"]

    lines = [f"退款数据（共 {len(results)} 条记录）："]
    for r in results:
        lines.append(f"  {r['month']} | {_product_name(r['product_id'])} | 退款{r['refund_count']}笔/{r['refund_amount']:,}元 | 原因：{r['reason']}")
    lines.append(f"  合计：{total_count}笔退款，{total_amount:,}元")
    lines.append(f"  退款原因分布：{dict(reason_dist)}")
    return "\n".join(lines)


@tool
def search_complaints(product_id: str = "", month: str = "", category: str = "") -> str:
    """
    查询投诉数据（投诉数量、类别、严重程度）。可按产品ID、月份或类别筛选。

    参数：
    - product_id: 产品ID，留空查全部
    - month: 月份，留空查全部月份
    - category: 投诉类别（响应速度/功能缺陷/性能问题/文档不完善），留空查全部
    """
    results = []
    for row in COMPLAINT_DATA:
        if product_id and row["product_id"] != product_id:
            continue
        if month and row["month"] != month:
            continue
        if category and row["category"] != category:
            continue
        results.append(row)

    if not results:
        return "未找到匹配的投诉数据。"

    total = sum(r["count"] for r in results)
    high = sum(r["count"] for r in results if r["severity"] == "高")

    from collections import Counter
    cat_dist = Counter()
    for r in results:
        cat_dist[r["category"]] += r["count"]

    lines = [f"投诉数据（共 {len(results)} 条记录）："]
    for r in results:
        lines.append(f"  {r['month']} | {_product_name(r['product_id'])} | {r['count']}起 | 类别：{r['category']} | 严重度：{r['severity']}")
    lines.append(f"  合计：{total}起投诉，其中高严重度 {high}起")
    lines.append(f"  类别分布：{dict(cat_dist)}")
    return "\n".join(lines)


@tool
def list_products() -> str:
    """列出所有产品线及其基本信息（名称、类别、价格、上线时间）。"""
    lines = ["产品线列表："]
    for pid, info in PRODUCTS.items():
        lines.append(f"  {pid} | {info['name']} | {info['category']} | {info['price']:,}元/年 | {info['launched']}上线")
    return "\n".join(lines)
