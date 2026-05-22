"""风格微调引擎 —— LoRA/Soft Prompt 微调用户语言风格"""

import json
from pathlib import Path
from typing import Dict, Optional

from tent_os.logging_config import get_logger

logger = get_logger()


class StyleFinetuner:
    """
    风格微调引擎（Phase 1 占位实现）
    
    未来集成：
    - 基于积累对话数据的 LoRA 微调
    - 或 Soft Prompt 学习
    """
    
    def __init__(self, storage_path: str = "./tent_memory/soul"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.style_dir = self.storage_path / "style_models"
        self.style_dir.mkdir(exist_ok=True)
    
    async def build_style_template(self, user_id: str, conversations: list) -> Dict:
        """基于对话构建风格模板（静态Prompt段）"""
        # Phase 1: 基于启发式规则构建伪LoRA模板
        template = {
            "user_id": user_id,
            "language_tone": "neutral",
            "sentence_length": "mixed",
            "favorite_expressions": [],
            "decision_phrases": [],
            "emotion_expressions": {},
        }
        
        all_text = " ".join([c.get("content", "") for c in conversations if c.get("role") == "user"])
        
        # 简单启发式
        if "。" in all_text and "，" in all_text:
            template["sentence_length"] = "long" if all_text.count("。") < len(all_text) / 100 else "short"
        
        # 保存模板
        template_path = self.style_dir / f"{user_id}_style.json"
        template_path.write_text(json.dumps(template, ensure_ascii=False, indent=2))
        
        logger.info(f"[SOUL] 风格模板已生成 [{user_id}]")
        return {"status": "ok", "template_path": str(template_path), "template": template}
    
    def get_style_template(self, user_id: str) -> Optional[Dict]:
        template_path = self.style_dir / f"{user_id}_style.json"
        if not template_path.exists():
            return None
        return json.loads(template_path.read_text())
    
    async def finetune(self, user_id: str) -> Dict:
        """触发微调（Phase 1 占位）"""
        logger.info(f"[SOUL] 风格微调请求（占位）[{user_id}]")
        return {
            "status": "placeholder",
            "message": "LoRA微调将在Phase 2集成本地训练流水线",
        }
