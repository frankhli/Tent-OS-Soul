"""统一 Embedding Client —— 支持多种 Provider，优雅降级

Phase 4 优先级：
1. OpenAI text-embedding-3-small（如果配置了 OPENAI_API_KEY）
2. TF-IDF Embedding（本地语义嵌入，零 API 成本）
3. HashEmbedding（基于哈希的确定性向量，最弱但零依赖）

TF-IDF Embedding 原理：
- 基于词频-逆文档频率，理解"关键词权重"
- 相似文本 → 更高余弦相似度
- 零外部 API，零成本，效果比 HashEmbedding 好得多

HashEmbedding 原理：
- 将文本分词，每个词的 hash 映射到向量维度
- 相同文本 → 相同向量（确定性）
- 最弱，但零依赖兜底
"""

import hashlib
import struct
from typing import List, Optional
import numpy as np


try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class HashEmbedding:
    """基于文本哈希的确定性 Embedding
    
    这不是语义嵌入，但比固定 [0.1]*1536 好得多：
    - 相同文本总是得到相同向量
    - 共享词汇的文本有更高相似度
    - 零 API 成本，零延迟
    """
    
    DIM = 1536
    SEED = 42
    
    def __init__(self, dim: int = 1536):
        self.dim = dim
    
    def embed(self, text: str) -> List[float]:
        """生成确定性向量"""
        text = text.lower().strip()
        if not text:
            return [0.0] * self.dim
        
        # 分词（简单按空格和标点分割）
        tokens = self._tokenize(text)
        
        # 初始化向量
        vec = np.zeros(self.dim, dtype=np.float32)
        
        for i, token in enumerate(tokens):
            # 每个词通过双哈希映射到两个位置，增加碰撞抵抗
            h1 = self._hash(token, self.SEED)
            h2 = self._hash(token, self.SEED + 1)
            
            idx1 = h1 % self.dim
            idx2 = h2 % self.dim
            
            # 权重衰减：越靠前的词权重越高（通常更重要）
            weight = 1.0 / (1.0 + i * 0.1)
            
            # 使用 hash 值作为有符号数值（-1 到 1）
            val1 = (h1 % 2000 - 1000) / 1000.0 * weight
            val2 = (h2 % 2000 - 1000) / 1000.0 * weight
            
            vec[idx1] += val1
            vec[idx2] += val2
        
        # L2 归一化
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        
        return vec.tolist()
    
    def _tokenize(self, text: str) -> List[str]:
        """简单分词：按非字母数字字符分割"""
        import re
        tokens = re.findall(r'[a-zA-Z0-9\u4e00-\u9fff]+', text)
        # 过滤停用词（简单版）
        stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                     'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                     'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                     'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                     'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
                     'through', 'during', 'before', 'after', 'above', 'below',
                     'between', 'under', '的', '了', '在', '是', '我', '有', '和',
                     '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到',
                     '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己',
                     '这'}
        return [t for t in tokens if t not in stopwords and len(t) > 1]
    
    def _hash(self, s: str, seed: int) -> int:
        """确定性哈希"""
        return int(hashlib.md5(f"{s}:{seed}".encode()).hexdigest(), 16)


class OpenAIEmbedding:
    """OpenAI text-embedding-3-small 适配器"""
    
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        if not OPENAI_AVAILABLE:
            raise ImportError("openai package is required for OpenAIEmbedding")
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model
    
    async def embed(self, text: str) -> List[float]:
        resp = await self.client.embeddings.create(
            model=self.model,
            input=text[:8000],  # 截断到最大输入长度
        )
        return resp.data[0].embedding


class TfidfEmbedding:
    """TF-IDF 语义嵌入 —— 零 API 成本，效果优于 HashEmbedding"""
    
    def __init__(self, dim: int = 1536):
        from tent_os.llm.embedding_tfidf import TfidfEmbeddingProvider
        self._provider = TfidfEmbeddingProvider()
        self.dim = dim
    
    def embed(self, text: str) -> List[float]:
        vec = self._provider.embed_single(text)
        # 扩展到目标维度（用零填充，保持余弦相似度不变）
        if len(vec) < self.dim:
            vec = vec + [0.0] * (self.dim - len(vec))
        elif len(vec) > self.dim:
            vec = vec[:self.dim]
        return vec


class EmbeddingClient:
    """统一 Embedding 客户端 —— 自动选择最佳可用 Provider"""
    
    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        openai_model: str = "text-embedding-3-small",
        dim: int = 1536,
    ):
        self.dim = dim
        self._provider = None
        
        # 优先级：OpenAI > TF-IDF > Hash
        if openai_api_key and OPENAI_AVAILABLE:
            self._provider = OpenAIEmbedding(openai_api_key, openai_model)
            self._provider_name = "openai"
            self._is_semantic = True
        else:
            try:
                self._provider = TfidfEmbedding(dim)
                self._provider_name = "tfidf"
                self._is_semantic = True
            except Exception:
                self._provider = HashEmbedding(dim)
                self._provider_name = "hash"
                self._is_semantic = False
    
    async def embed(self, text: str) -> List[float]:
        """生成文本的向量表示"""
        if hasattr(self._provider, 'embed'):
            if self._provider_name == "openai":
                return await self._provider.embed(text)
            else:
                return self._provider.embed(text)
        raise RuntimeError("No embedding provider available")
    
    @property
    def provider_name(self) -> str:
        return self._provider_name
    
    @property
    def is_semantic(self) -> bool:
        """是否是真正的语义嵌入（TF-IDF 和 OpenAI 是，HashEmbedding 不是）"""
        return self._is_semantic
