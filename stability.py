"""
stability.py —— 稳定性增强层

原脚本遇到这三类问题会直接抛异常，把整个刷课流程搞挂：

1. 断网 / DNS 解析失败
   `getaddrinfo failed` 一路冒到顶层，进程退出，前面刷的进度白费。

2. 触发风控「疑是多窗口观看」
   `code: -10` 直接 raise，脚本中断。实际上等一两分钟会话过期就恢复了。

3. 偶发超时
   一次 30s 超时就让课程中断，重来又要重新拉上下文。

本模块通过包装 Fucker 的请求方法（不修改原文件核心逻辑），
给这三类情况加上退避重试，让脚本能自己扛过去。
"""

from __future__ import annotations

import socket
import time
from typing import Any, Callable

import requests

from logger import logger


# 这些关键字说明是网络层问题，值得重试
_NETWORK_ERROR_HINTS = (
    "getaddrinfo failed",
    "NameResolutionError",
    "Max retries exceeded",
    "Connection aborted",
    "ConnectionResetError",
    "Read timed out",
    "Temporary failure in name resolution",
)

# 风控关键字
_RISK_HINTS = (
    "疑是多窗口观看",
    "captcha required",
    "code: -10",
)


def is_network_error(exc: Exception) -> bool:
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    text = str(exc)
    return any(hint in text for hint in _NETWORK_ERROR_HINTS)


def is_risk_control(exc: Exception) -> bool:
    text = str(exc)
    return any(hint in text for hint in _RISK_HINTS)


def is_captcha(exc: Exception) -> bool:
    return "captcha required" in str(exc) or "Captcha" in type(exc).__name__


def wait_for_network(host: str = "studyservice-api.zhihuishu.com",
                     port: int = 443,
                     max_wait: int = 900,
                     interval: int = 15) -> bool:
    """等网络恢复。返回 True 表示恢复，False 表示超时。"""
    deadline = time.time() + max_wait
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            socket.create_connection((host, port), timeout=5).close()
            logger.info(f"[稳定性] 网络已恢复（第 {attempt} 次探测）")
            return True
        except OSError:
            logger.warning(f"[稳定性] 网络不通，{interval}s 后重试（第 {attempt} 次）")
            time.sleep(interval)
    logger.error(f"[稳定性] 等待网络超时（{max_wait}s），放弃本次重试")
    return False


class StabilityGuard:
    """给 Fucker 实例的请求方法套上重试逻辑。"""

    def __init__(
        self,
        max_retries: int = 5,
        base_delay: float = 3.0,
        max_delay: float = 60.0,
        risk_cooldown: int = 90,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.risk_cooldown = risk_cooldown
        self.stats = {"network_retries": 0, "risk_retries": 0, "recovered": 0}

    def _backoff(self, attempt: int) -> float:
        return min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)

    def _wrap(self, fn: Callable, name: str) -> Callable:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None

            for attempt in range(1, self.max_retries + 1):
                try:
                    return fn(*args, **kwargs)

                except Exception as exc:
                    last_exc = exc

                    if is_captcha(exc):
                        logger.error(
                            "[稳定性] 平台要求验证码（captcha required），"
                            "脚本无法自动通过，请手动在浏览器登录一次后重启"
                        )
                        raise

                    if is_risk_control(exc):
                        self.stats["risk_retries"] += 1
                        logger.warning(
                            f"[稳定性] 触发风控：{exc}，"
                            f"冷却 {self.risk_cooldown}s 后重试（{attempt}/{self.max_retries}）"
                        )
                        if attempt < self.max_retries:
                            time.sleep(self.risk_cooldown)
                            continue
                        raise

                    if is_network_error(exc):
                        self.stats["network_retries"] += 1
                        delay = self._backoff(attempt)
                        logger.warning(
                            f"[稳定性] 网络异常：{str(exc)[:120]}，"
                            f"{delay:.0f}s 后重试（{attempt}/{self.max_retries}）"
                        )
                        if attempt < self.max_retries:
                            time.sleep(delay)
                            if not wait_for_network(max_wait=300):
                                continue
                            self.stats["recovered"] += 1
                            continue
                        raise

                    # 其他异常（接口返回码错误等）不重试，交给上层
                    raise

            raise last_exc if last_exc else RuntimeError(f"{name} 未知错误")

        wrapper.__name__ = f"guarded_{name}"
        return wrapper

    def patch(self, fucker: Any) -> None:
        """包装实例上的请求方法。只改实例，不动类定义。"""
        for method_name in ("zhidaoQuery", "_apiQuery", "hikeQuery"):
            original = getattr(fucker, method_name, None)
            if original is None or not callable(original):
                continue
            setattr(fucker, method_name, self._wrap(original, method_name))
            logger.info(f"[稳定性] 已加固 {method_name}")

    def summary(self) -> str:
        s = self.stats
        return (
            f"网络重试 {s['network_retries']} 次，"
            f"风控重试 {s['risk_retries']} 次，"
            f"断网恢复 {s['recovered']} 次"
        )
