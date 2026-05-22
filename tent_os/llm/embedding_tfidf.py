"""TF-IDF Embedding Provider —— 轻量级语义搜索

Phase 4 设计理念：
- 用户只需要一个 Kimi API key
- Embedding 本地计算，不调用任何 API
- 用 numpy 手写 TF-IDF，零额外依赖

效果：
- 比 SQL LIKE 好得多（理解语义相近）
- 比神经网络 embedding 差一些，但成本低、延迟低
- 像人：不是精确记忆每个词，而是记住"大概意思"
"""

import math
import re
from typing import List, Dict, Tuple
import numpy as np


class TfidfEmbeddingProvider:
    """TF-IDF 语义嵌入 —— 零 API 调用，纯本地计算
    
    像人的记忆方式：
    - 不是精确记住每个字
    - 而是记住"关键词 + 权重"
    - 搜索时联想相近的词
    """
    
    def __init__(self, min_df: int = 1):
        self.min_df = min_df
        self._vocab: Dict[str, int] = {}  # word -> index
        self._idf: np.ndarray = None
        self._docs_count = 0
        self._fitted = False
    
    def _tokenize(self, text: str) -> List[str]:
        """轻量级分词 —— 中文按字，英文按词"""
        if not text:
            return []
        text = text.lower()
        # 英文单词
        words = re.findall(r'[a-z_]+', text)
        # 中文字符（过滤常见虚词）
        stop_chars = set('的了吗呢吧啊哦嗯了着过')
        chars = [c for c in text if '\u4e00' <= c <= '\u9fff' and c not in stop_chars]
        return words + chars
    
    def fit(self, documents: List[str]):
        """拟合语料库 —— 计算 IDF"""
        if not documents:
            return
        
        # 统计文档频率
        df = {}
        for doc in documents:
            words = set(self._tokenize(doc))
            for w in words:
                df[w] = df.get(w, 0) + 1
        
        # 构建词表（过滤低频词）
        self._vocab = {}
        idx = 0
        for word, count in df.items():
            if count >= self.min_df:
                self._vocab[word] = idx
                idx += 1
        
        if not self._vocab:
            return
        
        # 计算 IDF
        n = len(documents)
        self._idf = np.zeros(len(self._vocab))
        for word, idx in self._vocab.items():
            self._idf[idx] = math.log((n + 1) / (df[word] + 1)) + 1
        
        self._docs_count = n
        self._fitted = True
    
    def embed_single(self, text: str) -> List[float]:
        """无需 fit 的单文本嵌入 —— 用于增量场景"""
        words = self._tokenize(text)
        if not words:
            return []
        
        # 构建临时词表
        unique_words = list(set(words))
        vocab = {w: i for i, w in enumerate(unique_words)}
        
        # 简化 IDF（所有词视为同等重要）
        idf = np.ones(len(vocab))
        
        # TF
        tf = np.zeros(len(vocab))
        for w in words:
            if w in vocab:
                tf[vocab[w]] += 1
        
        if tf.sum() > 0:
            tf = tf / tf.sum()
        
        # TF-IDF + L2 归一化
        vec = tf * idf
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        
        return vec.tolist()
    
    def embed(self, text: str) -> np.ndarray:
        """将文本转为向量"""
        if not self._fitted or not self._vocab:
            return np.zeros(1)
        
        words = self._tokenize(text)
        if not words:
            return np.zeros(len(self._vocab))
        
        # TF（词频）
        tf = np.zeros(len(self._vocab))
        for w in words:
            if w in self._vocab:
                tf[self._vocab[w]] += 1
        
        # 归一化 TF
        if tf.sum() > 0:
            tf = tf / tf.sum()
        
        # TF-IDF
        vec = tf * self._idf
        
        # L2 归一化
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        
        return vec
    
    def similarity(self, text1: str, text2: str) -> float:
        """计算两段文本的相似度"""
        v1 = self.embed(text1)
        v2 = self.embed(text2)
        return float(np.dot(v1, v2))
    
    def search(self, query: str, documents: List[str], top_k: int = 5) -> List[Tuple[int, float]]:
        """搜索最相似的文档
        
        返回: [(doc_index, score), ...]
        """
        if not documents or not self._fitted:
            return []
        
        # 重新拟合（增量更新）
        self.fit(documents)
        
        query_vec = self.embed(query)
        scores = []
        
        for i, doc in enumerate(documents):
            doc_vec = self.embed(doc)
            score = float(np.dot(query_vec, doc_vec))
            scores.append((i, score))
        
        # 按相似度排序
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


class SynonymExpander:
    """同义词扩展 —— 让搜索更人性化
    
    像人：你说"酒店"，我会联想到"旅馆、住宿、宾馆"
    """
    
    SYNONYMS = {
        '酒店': ['旅馆', '住宿', '宾馆', 'hotel', '旅店'],
        '备份': ['存档', '保存', '复制', 'backup', 'snapshot'],
        '压缩': ['打包', '归档', 'zip', '压缩'],
        '删除': ['移除', '清空', '删掉', 'delete', 'remove'],
        '查询': ['搜索', '查找', '检索', 'search', 'query'],
        '创建': ['新建', '生成', '建立', 'create', 'make'],
        '更新': ['修改', '刷新', '升级', 'update'],
        '用户': ['客户', '使用者', 'user', 'customer'],
        '任务': ['工作', '事项', '作业', 'task', 'job'],
        '错误': ['异常', '故障', 'bug', 'error', '失败'],
        '文件': ['文档', '资料', 'file', 'document'],
        '数据': ['信息', '资料', 'data', 'information'],
        '系统': ['平台', '服务', 'system', 'platform'],
        '配置': ['设置', '参数', 'config', 'configuration'],
        '启动': ['运行', '开启', '开始', 'start', 'launch'],
        '停止': ['关闭', '结束', '终止', 'stop', 'shutdown'],
    }
    
    @classmethod
    def expand(cls, text: str) -> str:
        """扩展查询文本中的同义词"""
        expanded = text
        for word, synonyms in cls.SYNONYMS.items():
            if word in text:
                expanded += ' ' + ' '.join(synonyms)
        return expanded
