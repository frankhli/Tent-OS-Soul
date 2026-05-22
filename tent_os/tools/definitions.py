"""内置工具定义 —— OpenAI function calling 兼容格式

每个工具定义包含：
- name: 工具名（LLM 调用时使用）
- description: 工具描述（帮助 LLM 理解何时使用）
- parameters: JSON Schema 参数定义

工具与执行者的映射：
- shell / file_read / file_write / directory_list / http_request → LocalExecutor
- memory_search / memory_get → TieredMemoryStore
"""

from typing import List, Dict, Any


# ========== 内置工具定义 ==========

_SHELL_TOOL = {
    "type": "function",
    "function": {
        "name": "shell",
        "description": (
            "在 Tent OS 运行的本地电脑上执行 shell 命令。"
            "通用执行工具，适用于文件操作、系统查询、运行脚本等场景。"
            "⚠️ 注意：当专用渲染工具（render_ppt/render_excel/render_document/render_contract/render_word）"
            "可用时，优先使用专用工具，不要用 shell 手写文件。"
            "支持：ls, cat, grep, curl, python3, git, find, pwd, echo, wc, diff 等常用命令。"
            "危险命令（rm -rf, sudo, mkfs 等）会被系统自动拦截，你无需担心。"
            "路径中的 ~ 会被自动展开为用户 home 目录。"
            "【重要】工具返回的结果是可信的，执行成功后无需用其他工具反复验证同一操作。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 shell 命令（单行）"
                },
                "__confirmed": {
                    "type": "boolean",
                    "description": "用户已确认执行此危险操作（仅当工具返回 need_confirmation 后使用）"
                }
            },
            "required": ["command"]
        }
    }
}

_FILE_READ_TOOL = {
    "type": "function",
    "function": {
        "name": "file_read",
        "description": "读取本地文件的内容。路径中的 ~ 会被自动展开。可访问范围取决于当前模式：full 模式下可访问任何路径；workspace/readonly 模式下只能访问 workspace 目录内的文件。读取成功后无需再次读取验证。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件的绝对路径或相对路径"
                }
            },
            "required": ["path"]
        }
    }
}

_FILE_WRITE_TOOL = {
    "type": "function",
    "function": {
        "name": "file_write",
        "description": "【文件写入专用】将完整内容写入本地文件（覆盖已有内容）。当你需要创建新文件、修改现有文件、保存代码或写入数据时，直接调用此工具。不要尝试在回复中输出文件内容——直接调用 file_write 写入磁盘。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径，例如 /Users/frank/Desktop/project/main.py"
                },
                "content": {
                    "type": "string",
                    "description": "文件的完整内容（覆盖写入），包括所有代码、文本或数据"
                },
                "__confirmed": {
                    "type": "boolean",
                    "description": "用户已确认执行此危险操作（仅当工具返回 need_confirmation 后使用）"
                }
            },
            "required": ["path", "content"]
        }
    }
}

_DIRECTORY_LIST_TOOL = {
    "type": "function",
    "function": {
        "name": "directory_list",
        "description": "列出目录下的文件和子目录。路径中的 ~ 会被自动展开。列出成功后无需重复列出验证。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "目录路径"
                }
            },
            "required": ["path"]
        }
    }
}

_HTTP_REQUEST_TOOL = {
    "type": "function",
    "function": {
        "name": "http_request",
        "description": "发送 HTTP 请求（GET/POST）。请求成功获取响应后，无需重复发送相同请求验证。",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "请求 URL"
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE"],
                    "description": "HTTP 方法"
                },
                "headers": {
                    "type": "object",
                    "description": "请求头（可选）"
                },
                "body": {
                    "type": "string",
                    "description": "请求体（可选，JSON 字符串）"
                }
            },
            "required": ["url", "method"]
        }
    }
}

_WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "搜索互联网上的实时信息。"
            "适合获取新闻、技术文档、产品信息、价格等最新数据。"
            "无需 API Key，免费使用。搜索结果可信，无需重复搜索验证。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词（自然语言）"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量（默认 5，最大 10）",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    }
}

_WEB_FETCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_fetch",
        "description": (
            "抓取指定网页的完整内容。"
            "适合读取文章、文档、博客等长文本内容。"
            "如果 web_search 返回的摘要不够，用此工具抓取完整页面。抓取成功后无需重复抓取验证。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要抓取的网页 URL"
                },
                "max_chars": {
                    "type": "integer",
                    "description": "最大返回字符数（默认 8000）",
                    "default": 8000
                }
            },
            "required": ["url"]
        }
    }
}

_MEMORY_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "memory_search",
        "description": (
            "搜索 Tent OS 的记忆系统，查找与查询相关的历史记忆。"
            "返回 L0/L1 层摘要，不包含完整内容。"
            "如需完整内容，请使用 memory_get(uri)。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询（自然语言）"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量（默认 5）",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    }
}

_MEMORY_GET_TOOL = {
    "type": "function",
    "function": {
        "name": "memory_get",
        "description": (
            "根据 URI 获取记忆的完整内容（L2 层）。"
            "URI 可以从 memory_search 的结果中获得。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "uri": {
                    "type": "string",
                    "description": "记忆的 URI（如 session/ws_xxx#chunk0）"
                }
            },
            "required": ["uri"]
        }
    }
}

_BROWSER_NAVIGATE_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_navigate",
        "description": "导航浏览器到指定 URL。",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "目标 URL"
                }
            },
            "required": ["url"]
        }
    }
}

_BROWSER_CLICK_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_click",
        "description": "点击页面上的元素（通过 CSS selector）。",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector，如 #button 或 .class"
                }
            },
            "required": ["selector"]
        }
    }
}

_BROWSER_TYPE_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_type",
        "description": "在输入框中输入文本。",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "输入框的 CSS selector"
                },
                "text": {
                    "type": "string",
                    "description": "要输入的文本"
                }
            },
            "required": ["selector", "text"]
        }
    }
}

_BROWSER_READ_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_read",
        "description": "读取当前页面的文本内容。",
        "parameters": {
            "type": "object",
            "properties": {
                "max_length": {
                    "type": "integer",
                    "description": "最大读取字符数（默认 5000）",
                    "default": 5000
                }
            }
        }
    }
}

_BROWSER_SCREENSHOT_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_screenshot",
        "description": "截取当前页面或指定元素的截图。",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "可选：元素 CSS selector"
                },
                "full_page": {
                    "type": "boolean",
                    "description": "是否截取全页面",
                    "default": False
                }
            }
        }
    }
}

# ======== 办公渲染工具（Tent OS 独有硬能力）========

_RENDER_PPT_TOOL = {
    "type": "function",
    "function": {
        "name": "render_ppt",
        "description": "【生成 PPT 专用】将 JSON 格式的 Presentation 数据结构渲染为精美的 HTML 幻灯片。当用户要求生成演示文稿、幻灯片、PPT 时，直接调用此工具。不要尝试用 shell 或 file_write 手写 HTML 幻灯片。",
        "parameters": {
            "type": "object",
            "properties": {
                "presentation_json": {
                    "type": "string",
                    "description": "Presentation 的 JSON 字符串（符合 schema.py 定义的数据结构）"
                },
                "output_path": {
                    "type": "string",
                    "description": "输出文件路径，默认保存到桌面。例如: /Users/frank/Desktop/my_ppt.html"
                }
            },
            "required": ["presentation_json"]
        }
    }
}

_RENDER_DOCUMENT_TOOL = {
    "type": "function",
    "function": {
        "name": "render_document",
        "description": "【生成文档专用】将 JSON 格式的 Document 数据结构渲染为精美的 HTML 文档（可打印为 PDF）。当用户要求生成报告、说明书、提案、文档时，直接调用此工具。不要尝试用 shell 或 file_write 手写 HTML 文档。",
        "parameters": {
            "type": "object",
            "properties": {
                "document_json": {
                    "type": "string",
                    "description": "Document 的 JSON 字符串（符合 schema.py 定义的数据结构）"
                },
                "output_path": {
                    "type": "string",
                    "description": "输出文件路径，例如: /Users/frank/Desktop/report.html"
                }
            },
            "required": ["document_json"]
        }
    }
}

_RENDER_CONTRACT_TOOL = {
    "type": "function",
    "function": {
        "name": "render_contract",
        "description": "【生成合同专用】将 JSON 格式的 Contract 数据结构渲染为专业的 HTML 合同（可打印为 PDF）。当用户要求生成合同、协议、法律文件时，直接调用此工具。不要尝试用 shell 或 file_write 手写合同文本。",
        "parameters": {
            "type": "object",
            "properties": {
                "contract_json": {
                    "type": "string",
                    "description": "Contract 的 JSON 字符串（符合 schema.py 定义的数据结构）"
                },
                "output_path": {
                    "type": "string",
                    "description": "输出文件路径，例如: /Users/frank/Desktop/contract.html"
                }
            },
            "required": ["contract_json"]
        }
    }
}

_RENDER_EXCEL_TOOL = {
    "type": "function",
    "function": {
        "name": "render_excel",
        "description": "【生成 Excel 专用】将 JSON 格式的 ExcelWorkbook 数据结构渲染为专业的 .xlsx 文件。支持多 sheet、公式、图表、条件格式、单元格样式。当用户要求生成报表、数据分析表、财务表格、Excel 文件时，直接调用此工具。不要尝试用 shell 或 file_write 手写 Excel 文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "workbook_json": {
                    "type": "string",
                    "description": "ExcelWorkbook 的 JSON 字符串（符合 schema.py 定义的数据结构）"
                },
                "output_path": {
                    "type": "string",
                    "description": "输出文件路径，例如: /Users/frank/Desktop/report.xlsx"
                }
            },
            "required": ["workbook_json"]
        }
    }
}

_RENDER_WORD_TOOL = {
    "type": "function",
    "function": {
        "name": "render_word",
        "description": "【生成 Word 专用】将 JSON 格式的 WordDocument 数据结构渲染为专业的 .docx 文件。支持段落、表格、图片、页眉页脚、标题样式。当用户要求生成 Word 文档、.docx 文件、公文、标书时，直接调用此工具。不要尝试用 shell 或 file_write 手写 Word 文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "document_json": {
                    "type": "string",
                    "description": "WordDocument 的 JSON 字符串（符合 schema.py 定义的数据结构）"
                },
                "output_path": {
                    "type": "string",
                    "description": "输出文件路径，例如: /Users/frank/Desktop/report.docx"
                }
            },
            "required": ["document_json"]
        }
    }
}

# 所有内置工具
BUILTIN_TOOLS: List[Dict[str, Any]] = [
    # 专用渲染工具（优先展示，减少 LLM fallback 到 shell 的倾向）
    _RENDER_PPT_TOOL,
    _RENDER_DOCUMENT_TOOL,
    _RENDER_CONTRACT_TOOL,
    _RENDER_EXCEL_TOOL,
    _RENDER_WORD_TOOL,
    # 通用工具
    _SHELL_TOOL,
    _FILE_READ_TOOL,
    _FILE_WRITE_TOOL,
    _DIRECTORY_LIST_TOOL,
    _HTTP_REQUEST_TOOL,
    _WEB_SEARCH_TOOL,
    _WEB_FETCH_TOOL,
    _MEMORY_SEARCH_TOOL,
    _MEMORY_GET_TOOL,
    _BROWSER_NAVIGATE_TOOL,
    _BROWSER_CLICK_TOOL,
    _BROWSER_TYPE_TOOL,
    _BROWSER_READ_TOOL,
    _BROWSER_SCREENSHOT_TOOL,
]

# 工具名到执行者 ID 的映射
TOOL_EXECUTOR_MAP = {
    "shell": "local",
    "file_read": "local",
    "file_write": "local",
    "directory_list": "local",
    "http_request": "local",
    "web_search": "web",
    "web_fetch": "web",
    "memory_search": "memory",
    "memory_get": "memory",
    "browser_navigate": "browser",
    "browser_click": "browser",
    "browser_type": "browser",
    "browser_read": "browser",
    "browser_screenshot": "browser",
    "render_ppt": "local",
    "render_document": "local",
    "render_contract": "local",
    "render_excel": "local",
    "render_word": "local",
    # FIX: 物理执行者映射到调度进程
    "realman": "realman",
    "flashex": "flashex",
    "scheduler_dispatch": "scheduler",
}


def get_tool_schemas(filter_names: List[str] = None) -> List[Dict[str, Any]]:
    """获取工具 schema 列表
    
    Args:
        filter_names: 如果提供，只返回指定名称的工具
    
    Returns:
        OpenAI function calling 格式的工具定义列表
    """
    if not filter_names:
        return BUILTIN_TOOLS
    return [
        t for t in BUILTIN_TOOLS
        if t["function"]["name"] in filter_names
    ]


def get_tools_for_executor(executor_id: str) -> List[str]:
    """获取指定执行者支持的工具名列表"""
    return [
        name for name, eid in TOOL_EXECUTOR_MAP.items()
        if eid == executor_id
    ]


def get_executor_for_tool(tool_name: str) -> str:
    """获取工具对应的执行者 ID"""
    return TOOL_EXECUTOR_MAP.get(tool_name, "local")


# ========== 渐进式工具加载（P1: 直觉模式）==========

def get_tool_metadata(tool_def: Dict[str, Any]) -> Dict[str, Any]:
    """提取工具的轻量元数据（用于直觉模式）
    
    元数据只包含工具名和一句话描述，约30-50 Token/工具。
    完整定义（200-500 Token）只在深度模式加载。
    """
    func = tool_def.get("function", {})
    name = func.get("name", "")
    desc = func.get("description", "")
    # 截断到第一句话（约30-50字）
    first_sentence = desc.split("。")[0].strip() if desc else ""
    if len(first_sentence) > 60:
        first_sentence = first_sentence[:60] + "..."
    
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": first_sentence,
            # 直觉模式下不暴露 parameters，避免LLM尝试构造参数
        }
    }


def get_tools_by_mode(mode: str, filter_names: List[str] = None) -> List[Dict[str, Any]]:
    """根据对话模式获取对应的工具定义
    
    Args:
        mode: 对话模式
            - "chat": 聊天模式，不返回任何工具
            - "intuition": 直觉模式，返回工具元数据索引（轻量）
            - "deep": 深度模式，返回完整工具定义
        filter_names: 可选，只返回指定名称的工具
    
    Returns:
        OpenAI function calling 格式的工具定义列表
    """
    if mode == "chat":
        return []
    
    tools = get_tool_schemas(filter_names)
    
    if mode == "intuition":
        # 直觉模式：只加载元数据层（约50 Token/工具）
        return [get_tool_metadata(t) for t in tools]
    
    # 深度模式：返回完整定义
    return tools


# 工具分类标签（用于直觉模式下的自动检测提示）
TOOL_CATEGORY_HINTS = {
    "shell": ["执行命令", "运行脚本", "查看系统"],
    "file_read": ["读取文件", "查看内容", "打开文件"],
    "file_write": ["写入文件", "创建文件", "修改文件", "保存"],
    "directory_list": ["列出目录", "查看文件夹", "浏览文件"],
    "http_request": ["发送请求", "调用API", "获取数据"],
    "web_search": ["搜索", "查资料", "找信息", "网上"],
    "web_fetch": ["抓取网页", "读取页面", "获取文章"],
    "memory_search": ["搜索记忆", "查找历史", "回忆"],
    "memory_get": ["获取记忆", "读取记忆"],
    "browser_navigate": ["打开网页", "浏览网站", "访问URL"],
    "browser_click": ["点击", "操作网页"],
    "browser_type": ["输入", "填写表单"],
    "browser_read": ["读取网页", "获取页面内容"],
    "browser_screenshot": ["截图", "截屏"],
    "render_ppt": ["生成PPT", "做幻灯片", "演示文稿"],
    "render_document": ["生成文档", "写报告", "生成PDF"],
    "render_contract": ["生成合同", "写协议"],
    "render_excel": ["生成Excel", "做表格", "报表"],
    "render_word": ["生成Word", "写文档", "公文"],
}
