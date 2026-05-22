"""视觉凭证验证服务 —— AI自动扫描任务凭证图片

当任务执行者上传照片凭证时，AI自动判断图片是否满足任务需求，
无需人工审核，体验更流畅。
"""

import base64
import json
from typing import Dict, Optional
from pathlib import Path

from tent_os.logging_config import get_logger

logger = get_logger()


class VisionScanner:
    """多模态凭证验证器"""

    @staticmethod
    async def verify_task_submission(
        task_id: str,
        image_data: str,  # base64 data URL 或 URL
        requirement: str,
        llm=None
    ) -> Dict:
        """验证凭证图片是否满足任务需求
        
        Args:
            task_id: 任务ID
            image_data: 图片数据（base64字符串或URL）
            requirement: 任务需求描述
            llm: 多模态LLM实例（可选）
            
        Returns:
            {
                "status": "pass" | "fail" | "uncertain",
                "confidence": 0.0-1.0,
                "reason": "详细理由",
                "missing_elements": ["缺少的元素列表"]
            }
        """
        # 如果没有LLM或不支持vision，返回启发式结果
        if not llm:
            return VisionScanner._heuristic_verify(requirement)
        
        # 构建多模态prompt
        prompt = f"""你是一个视觉凭证审核员。请检查以下凭证是否满足任务需求。

任务要求: {requirement}

请判断凭证图片是否满足要求，并以JSON格式返回:
{{
    "status": "pass" | "fail" | "uncertain",
    "confidence": 0.0-1.0,
    "reason": "详细理由",
    "missing_elements": ["如果有缺少的元素，列出在这里"]
}}

注意：
- pass: 凭证完全符合任务要求
- fail: 凭证不符合要求或缺少关键元素
- uncertain: 无法确定，建议人工复核"""

        try:
            # 判断是否是base64
            if image_data.startswith('data:image'):
                # 提取base64部分
                image_base64 = image_data.split(',')[1]
            elif image_data.startswith('http'):
                # URL形式，描述中包含URL
                prompt += f"\n凭证图片URL: {image_data}"
                image_base64 = None
            else:
                image_base64 = image_data

            # 调用多模态LLM
            if hasattr(llm, 'chat') and image_base64:
                # 构造多模态消息（OpenAI 兼容格式）
                messages = [
                    {"role": "system", "content": "你是一个视觉凭证审核员。请分析图片并按要求返回JSON格式结果。"},
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                    ]}
                ]
                response = await llm.chat(messages)
            else:
                response = await llm.chat([{"role": "user", "content": prompt}])
            
            # 尝试从响应中解析JSON
            result = VisionScanner._extract_json(response)
            if result:
                return {
                    "status": result.get("status", "uncertain"),
                    "confidence": float(result.get("confidence", 0.5)),
                    "reason": result.get("reason", "AI分析完成"),
                    "missing_elements": result.get("missing_elements", []),
                }
        except Exception as e:
            logger.warning(f"[VisionScanner] LLM验证失败: {e}")
        
        # 回退到启发式验证
        return VisionScanner._heuristic_verify(requirement)

    @staticmethod
    def _heuristic_verify(requirement: str) -> Dict:
        """启发式验证（无LLM时回退）"""
        req_lower = requirement.lower()
        
        # 简单关键词检查
        has_photo = any(k in req_lower for k in ["照片", "图片", "拍照", "截图", "photo", "image", "picture"])
        has_document = any(k in req_lower for k in ["文件", "文档", "单据", "票据", "document", "receipt"])
        
        if has_photo or has_document:
            return {
                "status": "uncertain",
                "confidence": 0.5,
                "reason": "已收到图片凭证，但当前无法自动验证内容。建议人工复核。",
                "missing_elements": ["自动验证需要多模态LLM支持"],
            }
        
        return {
            "status": "pass",
            "confidence": 0.6,
            "reason": "凭证已提交（非图片类任务，无需内容验证）",
            "missing_elements": [],
        }

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict]:
        """从文本中提取JSON对象"""
        try:
            # 尝试直接解析
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # 尝试提取 ```json ... ``` 块
        import re
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        
        # 尝试提取任意 {...} 块
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        
        return None
