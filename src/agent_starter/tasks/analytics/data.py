# -*- coding: utf-8 -*-
"""三条产品线的模拟销售、退款、投诉数据。"""

# 产品线
PRODUCTS = {
    "prod_a": {"name": "AI客服Agent", "category": "企业软件", "price": 49900, "launched": "2025-03"},
    "prod_b": {"name": "数据分析平台", "category": "企业软件", "price": 79900, "launched": "2025-01"},
    "prod_c": {"name": "知识库SaaS",     "category": "SaaS",     "price": 19900, "launched": "2025-06"},
}

# 2025年度销售数据（模拟）
SALES_DATA = [
    {"month": "2025-01", "product_id": "prod_b", "orders": 12, "revenue": 958800},
    {"month": "2025-02", "product_id": "prod_b", "orders": 18, "revenue": 1438200},
    {"month": "2025-03", "product_id": "prod_a", "orders": 5,  "revenue": 249500},
    {"month": "2025-03", "product_id": "prod_b", "orders": 22, "revenue": 1757800},
    {"month": "2025-04", "product_id": "prod_a", "orders": 15, "revenue": 748500},
    {"month": "2025-04", "product_id": "prod_b", "orders": 20, "revenue": 1598000},
    {"month": "2025-05", "product_id": "prod_a", "orders": 25, "revenue": 1247500},
    {"month": "2025-05", "product_id": "prod_b", "orders": 28, "revenue": 2237200},
    {"month": "2025-06", "product_id": "prod_a", "orders": 30, "revenue": 1497000},
    {"month": "2025-06", "product_id": "prod_b", "orders": 32, "revenue": 2556800},
    {"month": "2025-06", "product_id": "prod_c", "orders": 8,  "revenue": 159200},
    {"month": "2025-07", "product_id": "prod_a", "orders": 35, "revenue": 1746500},
    {"month": "2025-07", "product_id": "prod_b", "orders": 30, "revenue": 2397000},
    {"month": "2025-07", "product_id": "prod_c", "orders": 15, "revenue": 298500},
    {"month": "2025-08", "product_id": "prod_a", "orders": 40, "revenue": 1996000},
    {"month": "2025-08", "product_id": "prod_b", "orders": 26, "revenue": 2077400},
    {"month": "2025-08", "product_id": "prod_c", "orders": 22, "revenue": 437800},
]

# 退款数据
REFUND_DATA = [
    {"product_id": "prod_a", "month": "2025-03", "refund_count": 1, "refund_amount": 49900, "reason": "功能不满足需求"},
    {"product_id": "prod_a", "month": "2025-04", "refund_count": 2, "refund_amount": 99800, "reason": "实施周期长"},
    {"product_id": "prod_a", "month": "2025-05", "refund_count": 1, "refund_amount": 49900, "reason": "预算缩减"},
    {"product_id": "prod_a", "month": "2025-06", "refund_count": 2, "refund_amount": 99800, "reason": "竞品替代"},
    {"product_id": "prod_a", "month": "2025-07", "refund_count": 1, "refund_amount": 49900, "reason": "功能不满足需求"},
    {"product_id": "prod_a", "month": "2025-08", "refund_count": 3, "refund_amount": 149700, "reason": "预算缩减"},
    {"product_id": "prod_b", "month": "2025-02", "refund_count": 1, "refund_amount": 79900, "reason": "数据迁移困难"},
    {"product_id": "prod_b", "month": "2025-04", "refund_count": 1, "refund_amount": 79900, "reason": "性能不达标"},
    {"product_id": "prod_b", "month": "2025-05", "refund_count": 2, "refund_amount": 159800, "reason": "竞品替代"},
    {"product_id": "prod_b", "month": "2025-07", "refund_count": 2, "refund_amount": 159800, "reason": "预算缩减"},
    {"product_id": "prod_b", "month": "2025-08", "refund_count": 3, "refund_amount": 239700, "reason": "功能不满足需求"},
    {"product_id": "prod_c", "month": "2025-07", "refund_count": 1, "refund_amount": 19900, "reason": "竞品替代"},
    {"product_id": "prod_c", "month": "2025-08", "refund_count": 1, "refund_amount": 19900, "reason": "不再需要"},
]

# 投诉数据
COMPLAINT_DATA = [
    {"product_id": "prod_a", "month": "2025-04", "count": 2, "category": "响应速度", "severity": "中"},
    {"product_id": "prod_a", "month": "2025-05", "count": 1, "category": "文档不完善", "severity": "低"},
    {"product_id": "prod_a", "month": "2025-06", "count": 3, "category": "响应速度", "severity": "中"},
    {"product_id": "prod_a", "month": "2025-07", "count": 2, "category": "功能缺陷", "severity": "高"},
    {"product_id": "prod_a", "month": "2025-08", "count": 4, "category": "响应速度", "severity": "中"},
    {"product_id": "prod_b", "month": "2025-03", "count": 1, "category": "响应速度", "severity": "低"},
    {"product_id": "prod_b", "month": "2025-05", "count": 2, "category": "性能问题", "severity": "高"},
    {"product_id": "prod_b", "month": "2025-06", "count": 3, "category": "性能问题", "severity": "高"},
    {"product_id": "prod_b", "month": "2025-07", "count": 4, "category": "性能问题", "severity": "高"},
    {"product_id": "prod_b", "month": "2025-08", "count": 5, "category": "响应速度", "severity": "中"},
    {"product_id": "prod_c", "month": "2025-07", "count": 1, "category": "文档不完善", "severity": "低"},
    {"product_id": "prod_c", "month": "2025-08", "count": 2, "category": "功能缺陷", "severity": "低"},
]
