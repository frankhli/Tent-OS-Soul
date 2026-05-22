"""SkillRouter 去关键词化测试 —— 真实 LLM 驱动

验证核心目标：
- "生成幻灯片" 应匹配 presentation skill（无需"PPT"关键词）
- "做PPT" 应匹配 presentation skill（原始 triggers 兼容）
- "hello"/"你好" 不应匹配任何 skill（闲聊过滤）
"""

import pytest
from tent_os.skills.router import SkillRouter


@pytest.fixture
async def expanded_router(real_llm):
    """创建已扩展 triggers 的 SkillRouter"""
    router = SkillRouter(skills_dir="./skills", llm=real_llm)
    
    # 扩展关键 skills
    targets = ["presentation", "data-analysis", "software-engineer"]
    for name in targets:
        skill = router.skills.get(name)
        if skill:
            new_triggers = await router._llm_expand_triggers(skill)
            if new_triggers:
                skill.triggers = list(skill.triggers) + new_triggers
                router._index_skill(skill, is_expansion=True)
    
    return router


@pytest.mark.timeout(120)
@pytest.mark.integration
class TestSkillRouterDekeywordization:
    """SkillRouter 去关键词化集成测试"""

    @pytest.mark.asyncio
    async def test_semantic_match_no_keywords(self, expanded_router):
        """语义匹配：无关键词但能匹配到正确 skill"""
        router = await expanded_router
        skills = await router.route("生成幻灯片")
        names = [s.name for s in skills]
        assert "Presentation Design Master" in names, \
            f"'生成幻灯片'应匹配 presentation: {names}"

    @pytest.mark.asyncio
    async def test_original_triggers_still_work(self, expanded_router):
        """原始 triggers 兼容性：做PPT 仍能匹配"""
        router = await expanded_router
        skills = await router.route("做PPT")
        names = [s.name for s in skills]
        assert "Presentation Design Master" in names, \
            f"'做PPT'应匹配 presentation: {names}"

    @pytest.mark.asyncio
    async def test_chitchat_filtered(self, expanded_router):
        """闲聊过滤：不应匹配任何 skill"""
        router = await expanded_router
        for query in ["hello", "你好", "谢谢", "再见"]:
            skills = await router.route(query)
            assert skills == [], f"'{query}' 不应匹配任何 skill: {[s.name for s in skills]}"

    @pytest.mark.asyncio
    async def test_data_analysis_semantic(self, expanded_router):
        """数据分析语义匹配"""
        router = await expanded_router
        skills = await router.route("分析一下销售数据")
        names = [s.name for s in skills]
        assert "Data Analysis" in names, \
            f"'分析一下销售数据'应匹配 data-analysis: {names}"

    @pytest.mark.asyncio
    async def test_llm_semantic_route_fallback(self, expanded_router):
        """LLM 语义路由：当倒排索引无命中时触发"""
        router = await expanded_router
        # "帮我整理桌面文件" 不在任何 skill triggers 中
        # 应触发 LLM 语义路由或返回空
        skills = await router.route("帮我整理桌面文件")
        # 不要求具体匹配，只要求不崩溃
        assert isinstance(skills, list)
