"""数据分析域定义。"""
from agent_starter.tasks.domains import DomainSpec
from agent_starter.tasks.analytics.tools import (
    search_sales, search_refunds, search_complaints, list_products,
)

SPEC = DomainSpec(
    name="analytics",
    label="数据分析（销售/退款/投诉查询与分析）",
    triggers=[
        "分析", "对比", "趋势", "销售", "退款", "投诉", "数据",
        "产品线", "哪个", "为什么", "原因", "建议", "报告",
        "占比", "排名", "最高", "最低", "增长", "下降",
    ],
    read_tools=[search_sales, search_refunds, search_complaints, list_products],
    write_tools=[],
)
