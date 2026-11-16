"""拆解-并行-综合 Agent 测试。"""

from agent_starter.tasks.analytics.tools import (
    list_products,
    search_complaints,
    search_refunds,
    search_sales,
)


class TestRetrievalTools:
    """检索工具单元测试"""

    def test_list_products(self):
        result = list_products.invoke("")
        assert "prod_a" in result
        assert "prod_b" in result
        assert "prod_c" in result

    def test_search_sales_all(self):
        result = search_sales.invoke({"product_id": "", "month": ""})
        assert "17" in result or "17 " in result  # 17 records

    def test_search_sales_by_product(self):
        result = search_sales.invoke({"product_id": "prod_a", "month": ""})
        assert "AI" in result
        assert "150" in result  # total orders for prod_a

    def test_search_sales_by_month(self):
        result = search_sales.invoke({"product_id": "", "month": "2025-06"})
        assert "2025-06" in result

    def test_search_refunds_all(self):
        result = search_refunds.invoke({"product_id": "", "month": ""})
        assert "13" in result or "13 " in result

    def test_search_refunds_by_product(self):
        result = search_refunds.invoke({"product_id": "prod_a", "month": ""})
        assert "AI" in result
        assert "10" in result  # total refunds for prod_a

    def test_search_complaints_all(self):
        result = search_complaints.invoke({"product_id": "", "month": "", "category": ""})
        assert "30" in result  # 30 total complaints

    def test_search_complaints_high_severity(self):
        result = search_complaints.invoke({"product_id": "", "month": "", "category": "性能问题"})
        assert "性能" in result

    def test_no_results(self):
        result = search_sales.invoke({"product_id": "prod_z", "month": ""})
        assert "未找到" in result


class TestDecomposePrompt:
    """拆解 Prompt 格式验证"""

    def test_decompose_prompt_format(self):
        from agent_starter.graph import DECOMPOSE_PROMPT
        prompt = DECOMPOSE_PROMPT.format(user_input="测试问题", tool_catalog="- search_sales")
        assert "测试问题" in prompt
        assert "JSON" in prompt
        assert "search_sales" in prompt

    def test_synthesize_prompt_format(self):
        from agent_starter.graph import SYNTHESIZE_PROMPT
        prompt = SYNTHESIZE_PROMPT.format(user_input="测试", sub_results="结果")
        assert "测试" in prompt
        assert "结果" in prompt
