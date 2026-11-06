"""
ai_provider.py —— 统一大模型答题接入层

针对原项目 AI 答题链路的三个问题做了修复：

1. URL 拼接 bug
   原实现 `f"{baseUrl}/v1/chat/completions"`，如果用户按官方文档填
   `https://api.deepseek.com/v1`，实际请求变成 `/v1/v1/chat/completions` → 404。
   本模块统一归一化 base_url，带不带 /v1 都正确。

2. 答案解析过严
   原实现只认 ```answer\\n...\\n``` 这一种格式，模型输出 ```json、
   无换行、裸 JSON 都会直接抛异常。本模块支持多种格式并做渐进式降级解析。

3. 自建模型失败即中断
   原实现重试 3 次后直接 raise，会让整个刷课流程挂掉。
   本模块失败后可选降级到智慧树自带 AI，保证不中断。

对外接口与原有 `Openai.generateAnswer(prompt)` 保持一致，可直接替换。
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import time
from typing import Any

import requests

from logger import logger


# ---------------------------------------------------------------- 预设服务商
# 都是 OpenAI 兼容接口，填上 api_key 就能用
PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "deepseek": {
        "api_base": "https://api.deepseek.com/v1",
        "model_name": "deepseek-chat",
    },
    "dashscope": {  # 阿里通义千问
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_name": "qwen-plus",
    },
    "moonshot": {  # 月之暗面 Kimi
        "api_base": "https://api.moonshot.cn/v1",
        "model_name": "moonshot-v1-32k",
    },
    "zhipu": {  # 智谱 GLM
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "model_name": "glm-4-flash",
    },
    "siliconflow": {
        "api_base": "https://api.siliconflow.cn/v1",
        "model_name": "deepseek-ai/DeepSeek-V3",
    },
    "openai": {
        "api_base": "https://api.openai.com/v1",
        "model_name": "gpt-4o-mini",
    },
}


def normalize_base_url(url: str) -> str:
    """把各种写法的 base_url 统一成不带尾部 /v1 的形式。

    https://api.deepseek.com/v1      -> https://api.deepseek.com
    https://api.deepseek.com/v1/     -> https://api.deepseek.com
    https://api.deepseek.com         -> https://api.deepseek.com
    """
    url = (url or "").strip().rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url


def resolve_config(op_conf: dict[str, Any]) -> tuple[str, str, str]:
    """解析出 (api_base, api_key, model_name)，支持 provider 预设。"""
    provider = str(op_conf.get("provider", "") or "").strip().lower()
    preset = PROVIDER_PRESETS.get(provider, {})

    api_base = op_conf.get("api_base") or preset.get("api_base", "")
    model_name = op_conf.get("model_name") or preset.get("model_name", "")
    api_key = op_conf.get("api_key", "") or ""

    return normalize_base_url(api_base), api_key, model_name


def is_key_valid(api_key: str) -> bool:
    """判断 key 看起来是否可用（排除空串和 config 模板里的 'sk-' 占位符）。"""
    key = (api_key or "").strip()
    return len(key) > 10 and key not in {"sk-", "your-key", "none"}


# ---------------------------------------------------------------- 答案解析
_ANSWER_PATTERNS = [
    r"```answer\s*\n(.*?)\n\s*```",   # 标准格式
    r"```json\s*\n(.*?)\n\s*```",     # 模型偶尔用 json 标签
    r"```\s*\n(.*?)\n\s*```",         # 无标签代码块
    r"```answer(.*?)```",             # 无换行
    r"(\[\s*\{.*?\}\s*\])",           # 裸 JSON 数组
]


def parse_answer(text: str) -> list[int]:
    """从模型输出里抠出答案 id 列表。

    渐进式降级：依次尝试多种代码块格式，最后兜底正则一个 JSON 数组。
    """
    if not text:
        raise ValueError("模型返回为空")

    block = None
    for pattern in _ANSWER_PATTERNS:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            block = match.group(1).strip()
            break

    if block is None:
        # 最后一根稻草：全文找形如 [{"id": 1, ...}] 的片段
        match = re.search(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
        if not match:
            raise ValueError(f"未能在模型输出中找到答案块，原文前 200 字：{text[:200]}")
        block = match.group(0)

    # 去尾逗号（模型常见毛病：{"id": 1, "content": "x",}）
    block = re.sub(r",\s*([}\]])", r"\1", block)

    data = None
    try:
        data = json.loads(block)
    except json.JSONDecodeError:
        try:
            data = ast.literal_eval(block)
        except (ValueError, SyntaxError):
            raise ValueError(f"答案块无法解析为 JSON：{block[:200]}")

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        raise ValueError(f"答案应为非空列表，实际是 {type(data)}")

    ids: list[int] = []
    for item in data:
        if isinstance(item, dict):
            if "id" in item:
                ids.append(int(item["id"]))
            elif "content" in item:
                raise ValueError(f"答案缺少 id 字段，只有 content：{item}")
            else:
                raise ValueError(f"答案项格式非法：{item}")
        elif isinstance(item, (int, str)):
            ids.append(int(item))
        else:
            raise ValueError(f"答案项格式非法：{item}")

    if not ids:
        raise ValueError("解析出的答案 id 列表为空")
    return ids


# ---------------------------------------------------------------- 主体
class AIProvider:
    """OpenAI 兼容接口的答题客户端。"""

    def __init__(
        self,
        api_base: str,
        api_key: str,
        model_name: str,
        extra: dict[str, Any] | None = None,
        timeout: int = 45,
        max_retries: int = 3,
        temperature: float = 0.2,
    ) -> None:
        self.api_base = normalize_base_url(api_base)
        self.api_key = api_key
        self.model_name = model_name
        self.extra = extra or {}
        self.timeout = timeout
        self.max_retries = max_retries
        self.temperature = temperature

        self.session = requests.Session()
        self._cache: dict[str, list[int]] = {}
        self.stats = {"requests": 0, "success": 0, "failed": 0, "cached": 0}

    @property
    def endpoint(self) -> str:
        return f"{self.api_base}/v1/chat/completions"

    def _cache_key(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:32]

    def chat(self, prompt: str) -> str:
        """发一次对话请求，带指数退避重试。"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        body = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "你是严谨的答题助手，严格按要求的 JSON 格式输出答案。",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "stream": False,
        }

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self.stats["requests"] += 1
            try:
                resp = self.session.post(
                    self.endpoint, headers=headers, json=body, timeout=self.timeout
                )

                if resp.status_code == 401:
                    raise PermissionError(f"API key 无效或已过期（401）：{resp.text[:200]}")
                if resp.status_code == 404:
                    raise LookupError(
                        f"接口地址不对（404）：{self.endpoint}，"
                        f"请检查 api_base 是否需要去掉 /v1"
                    )
                if resp.status_code == 429:
                    raise RuntimeError(f"触发限流（429），稍后重试：{resp.text[:200]}")

                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                if not content or not content.strip():
                    raise ValueError("模型返回内容为空")
                return content

            except PermissionError:
                raise  # key 错了，重试没意义
            except Exception as exc:
                last_error = exc
                logger.warning(
                    f"[AI] 第 {attempt}/{self.max_retries} 次请求失败：{exc}"
                )
                if attempt < self.max_retries:
                    backoff = min(2 ** attempt, 10)
                    time.sleep(backoff)

        raise RuntimeError(f"AI 请求全部失败：{last_error}")

    def generateAnswer(self, prompt: str) -> list[int]:
        """与原 Openai.generateAnswer 接口一致，返回答案 id 列表。"""
        key = self._cache_key(prompt)
        if key in self._cache:
            self.stats["cached"] += 1
            return self._cache[key]

        try:
            text = self.chat(prompt)
            ids = parse_answer(text)
            self._cache[key] = ids
            self.stats["success"] += 1
            return ids
        except Exception as exc:
            self.stats["failed"] += 1
            logger.error(f"[AI] 答题失败：{exc}")
            raise

    def summary(self) -> str:
        s = self.stats
        total = max(s["requests"], 1)
        rate = s["success"] / total * 100
        return (
            f"AI 请求 {s['requests']} 次，成功 {s['success']}，"
            f"失败 {s['failed']}，命中缓存 {s['cached']}，成功率 {rate:.0f}%"
        )


def create_provider(
    op_conf: dict[str, Any], extra: dict[str, Any] | None = None
) -> AIProvider | None:
    """从配置创建 provider。key 不可用时返回 None，由调用方回退到智慧树 AI。"""
    api_base, api_key, model_name = resolve_config(op_conf or {})

    if not is_key_valid(api_key):
        logger.info("[AI] 未配置有效的大模型 api_key，将使用智慧树自带 AI")
        return None
    if not api_base:
        logger.warning("[AI] api_base 为空，无法创建 provider")
        return None
    if not model_name:
        logger.warning("[AI] model_name 为空，无法创建 provider")
        return None

    provider = AIProvider(
        api_base=api_base,
        api_key=api_key,
        model_name=model_name,
        extra=extra,
        timeout=int(op_conf.get("timeout", 45)),
        max_retries=int(op_conf.get("max_retries", 3)),
        temperature=float(op_conf.get("temperature", 0.2)),
    )
    logger.info(f"[AI] 已启用自建模型：{model_name} @ {provider.api_base}")
    return provider
