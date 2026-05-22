"""Document Schema —— 文档数据结构定义

支持通用文档和合同专用文档。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class DocumentSection:
    """文档章节"""
    title: str = ""
    content: str = ""  # 支持 Markdown 格式
    level: int = 1  # 标题级别 1-6


@dataclass
class Document:
    """通用文档"""
    title: str = ""
    subtitle: str = ""
    author: str = "Tent OS"
    date: str = ""
    theme: str = "light_corporate"  # 复用 PPT 主题
    sections: List[DocumentSection] = field(default_factory=list)
    # 全局配置
    config: Dict[str, Any] = field(default_factory=lambda: {
        "show_toc": True,
        "page_numbers": True,
    })
    
    def to_dict(self) -> Dict:
        from dataclasses import asdict
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Document":
        # FIX: 过滤掉 dataclass 不认识的字段（LLM 可能生成 'type'、'items' 等）
        sections = [DocumentSection(**{k: v for k, v in s.items() if k in DocumentSection.__dataclass_fields__}) for s in data.get("sections", [])]
        return cls(
            title=data.get("title", ""),
            subtitle=data.get("subtitle", ""),
            author=data.get("author", "Tent OS"),
            date=data.get("date", ""),
            theme=data.get("theme", "light_corporate"),
            sections=sections,
            config=data.get("config", {}),
        )


@dataclass
class ContractParty:
    """合同签署方"""
    name: str = ""
    role: str = ""  # 甲方 / 乙方
    address: str = ""
    contact: str = ""


@dataclass
class ContractClause:
    """合同条款"""
    number: str = ""  # 第一条、第1.1款 等
    title: str = ""
    content: str = ""


@dataclass
class Contract:
    """合同文档"""
    title: str = ""
    contract_no: str = ""  # 合同编号
    date: str = ""
    theme: str = "light_corporate"
    parties: List[ContractParty] = field(default_factory=list)
    clauses: List[ContractClause] = field(default_factory=list)
    # 签字区
    signature_date: str = ""
    signature_place: str = ""
    # 全局配置
    config: Dict[str, Any] = field(default_factory=lambda: {
        "show_seal_placeholder": True,
        "page_numbers": True,
    })
    
    def to_dict(self) -> Dict:
        from dataclasses import asdict
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Contract":
        # FIX: 过滤掉 dataclass 不认识的字段（LLM 可能生成 'representative' 等）
        parties = [ContractParty(**{k: v for k, v in p.items() if k in ContractParty.__dataclass_fields__}) for p in data.get("parties", [])]
        clauses = [ContractClause(**{k: v for k, v in c.items() if k in ContractClause.__dataclass_fields__}) for c in data.get("clauses", [])]
        return cls(
            title=data.get("title", ""),
            contract_no=data.get("contract_no", ""),
            date=data.get("date", ""),
            theme=data.get("theme", "light_corporate"),
            parties=parties,
            clauses=clauses,
            signature_date=data.get("signature_date", ""),
            signature_place=data.get("signature_place", ""),
            config=data.get("config", {}),
        )
