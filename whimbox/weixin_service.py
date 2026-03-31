from __future__ import annotations

import asyncio
import base64
import json
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from whimbox.channel_gateway import (
    ChannelInboundMessage,
    ChannelReplyHandle,
    handle_inbound_message,
    resolve_channel_session_id,
)
from whimbox.common.logger import logger
from whimbox.common.path_lib import CONFIG_PATH


DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com/"
DEFAULT_BOT_TYPE = "3"
DEFAULT_CHANNEL_VERSION = "whimbox"
QR_STATUS_TIMEOUT_SECONDS = 35


@dataclass(slots=True)
class _WeixinAuth:
    token: str = ""
    base_url: str = DEFAULT_BASE_URL
    account_id: str = ""
    user_id: str = ""
    saved_at: str = ""


class _WeixinReplyHandle(ChannelReplyHandle):
    def __init__(self, service: "WeixinService", to_user_id: str, context_token: str) -> None:
        self._service = service
        self._to_user_id = to_user_id
        self._context_token = context_token
        self._send_lock = asyncio.Lock()

    async def send_text(self, text: str) -> None:
        payload = str(text or "")
        if not payload.strip():
            return
        async with self._send_lock:
            await self._service.send_text_message(
                to_user_id=self._to_user_id,
                context_token=self._context_token,
                text=payload,
            )

    async def send_tool_start(self, tool_name: str) -> None:
        name = str(tool_name or "").strip()
        if not name:
            return
        await self.send_text(f"调用工具：{name}")

    async def send_error(self, message: str) -> None:
        await self.send_text(message)


class WeixinService:
    def __init__(self) -> None:
        self._root_dir = os.path.join(CONFIG_PATH, "weixin")
        self._auth_path = os.path.join(self._root_dir, "auth.json")
        self._runtime_path = os.path.join(self._root_dir, "runtime.json")
        self._auth = _WeixinAuth()
        self._login_state = "logged_out"
        self._monitor_state = "stopped"
        self._last_error = ""
        self._qrcode: str = ""
        self._qrcode_url: str = ""
        self._get_updates_buf: str = ""
        self._monitor_task: asyncio.Task[Any] | None = None
        self._monitor_stop = asyncio.Event()
        self._context_tokens: dict[str, str] = {}
        self._active_inbound_tasks: set[asyncio.Task[Any]] = set()
        self._lock = asyncio.Lock()
        self._ensure_storage()
        self._load_state()

    async def auto_restore(self) -> None:
        if not self._auth.token:
            return
        if self._monitor_task and not self._monitor_task.done():
            return
        try:
            await self.start_monitor()
        except Exception as exc:  # noqa: BLE001
            self._monitor_state = "error"
            self._last_error = str(exc)
            logger.warning(f"auto restore weixin monitor failed: {exc}")

    def _ensure_storage(self) -> None:
        os.makedirs(self._root_dir, exist_ok=True)

    def _load_state(self) -> None:
        if os.path.exists(self._auth_path):
            try:
                with open(self._auth_path, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
                self._auth = _WeixinAuth(
                    token=str(raw.get("token") or ""),
                    base_url=str(raw.get("base_url") or DEFAULT_BASE_URL),
                    account_id=str(raw.get("account_id") or ""),
                    user_id=str(raw.get("user_id") or ""),
                    saved_at=str(raw.get("saved_at") or ""),
                )
                if self._auth.token:
                    self._login_state = "logged_in"
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"load weixin auth failed: {exc}")
        if os.path.exists(self._runtime_path):
            try:
                with open(self._runtime_path, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
                self._get_updates_buf = str(raw.get("get_updates_buf") or "")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"load weixin runtime failed: {exc}")

    def _save_auth(self) -> None:
        payload = {
            "token": self._auth.token,
            "base_url": self._auth.base_url,
            "account_id": self._auth.account_id,
            "user_id": self._auth.user_id,
            "saved_at": self._auth.saved_at,
        }
        with open(self._auth_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def _save_runtime(self) -> None:
        payload = {"get_updates_buf": self._get_updates_buf}
        with open(self._runtime_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def get_status(self) -> dict[str, Any]:
        return {
            "login_state": self._login_state,
            "monitor_state": self._monitor_state,
            "account_id": self._auth.account_id or None,
            "last_error": self._last_error or None,
            "qrcode_url": self._qrcode_url or None,
        }

    async def start_login(self) -> dict[str, Any]:
        async with self._lock:
            response = await asyncio.to_thread(
                self._api_get,
                DEFAULT_BASE_URL,
                "ilink/bot/get_bot_qrcode",
                {"bot_type": DEFAULT_BOT_TYPE},
            )
            self._qrcode = str(response.get("qrcode") or "")
            self._qrcode_url = str(response.get("qrcode_img_content") or "")
            if not self._qrcode or not self._qrcode_url:
                raise ValueError("微信二维码获取失败")
            self._login_state = "pending_scan"
            self._last_error = ""
        return self.get_status()

    async def poll_login(self) -> dict[str, Any]:
        should_start_monitor = False
        async with self._lock:
            if not self._qrcode:
                return self.get_status()
            try:
                response = await asyncio.to_thread(
                    self._api_get,
                    DEFAULT_BASE_URL,
                    "ilink/bot/get_qrcode_status",
                    {"qrcode": self._qrcode},
                    QR_STATUS_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                response = {"status": "wait"}
            status = str(response.get("status") or "")
            if status == "scaned":
                self._login_state = "scan_confirmed"
            elif status == "confirmed":
                self._auth = _WeixinAuth(
                    token=str(response.get("bot_token") or ""),
                    base_url=str(response.get("baseurl") or DEFAULT_BASE_URL),
                    account_id=str(response.get("ilink_bot_id") or ""),
                    user_id=str(response.get("ilink_user_id") or ""),
                    saved_at=datetime.now(timezone.utc).isoformat(),
                )
                if not self._auth.token:
                    raise ValueError("微信登录成功，但未获取到 bot_token")
                self._save_auth()
                self._login_state = "logged_in"
                self._last_error = ""
                self._qrcode = ""
                self._qrcode_url = ""
                should_start_monitor = True
            elif status == "expired":
                self._login_state = "expired"
            elif status == "wait":
                self._login_state = "pending_scan"
        if should_start_monitor:
            await self.start_monitor()
        return self.get_status()

    async def start_monitor(self) -> dict[str, Any]:
        async with self._lock:
            if not self._auth.token:
                raise ValueError("微信未登录")
            if self._monitor_task and not self._monitor_task.done():
                return self.get_status()
            self._monitor_stop = asyncio.Event()
            self._monitor_state = "running"
            self._last_error = ""
            self._monitor_task = asyncio.create_task(self._monitor_loop())
        return self.get_status()

    async def stop_monitor(self) -> dict[str, Any]:
        async with self._lock:
            self._monitor_stop.set()
            task = self._monitor_task
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        async with self._lock:
            self._monitor_task = None
            if self._monitor_state != "error":
                self._monitor_state = "stopped"
        return self.get_status()

    async def disconnect(self) -> dict[str, Any]:
        await self.stop_monitor()
        async with self._lock:
            self._auth = _WeixinAuth()
            self._login_state = "logged_out"
            self._monitor_state = "stopped"
            self._last_error = ""
            self._qrcode = ""
            self._qrcode_url = ""
            self._get_updates_buf = ""
            self._context_tokens.clear()
            if os.path.exists(self._auth_path):
                os.remove(self._auth_path)
            if os.path.exists(self._runtime_path):
                os.remove(self._runtime_path)
        return self.get_status()

    async def send_text_message(self, *, to_user_id: str, context_token: str, text: str) -> None:
        client_id = f"whimbox-{int(time.time() * 1000)}-{random.randint(1000, 9999)}"
        body = {
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "client_id": client_id,
                "message_type": 2,
                "message_state": 2,
                "context_token": context_token,
                "item_list": [
                    {
                        "type": 1,
                        "text_item": {"text": text},
                    }
                ],
            }
        }
        await asyncio.to_thread(self._api_post, self._auth.base_url, "ilink/bot/sendmessage", body)

    async def _monitor_loop(self) -> None:
        logger.info("weixin monitor started")
        try:
            while not self._monitor_stop.is_set():
                response = await asyncio.to_thread(
                    self._api_post,
                    self._auth.base_url,
                    "ilink/bot/getupdates",
                    {"get_updates_buf": self._get_updates_buf},
                    40,
                )
                if not isinstance(response, dict):
                    continue
                errcode = int(response.get("errcode") or 0)
                if errcode == -14:
                    self._login_state = "expired"
                    self._monitor_state = "error"
                    self._last_error = "微信登录已过期，请重新扫码登录。"
                    break
                new_buf = str(response.get("get_updates_buf") or "")
                if new_buf:
                    self._get_updates_buf = new_buf
                    self._save_runtime()
                for item in response.get("msgs") or []:
                    task = asyncio.create_task(self._handle_weixin_message(item))
                    self._active_inbound_tasks.add(task)
                    task.add_done_callback(self._active_inbound_tasks.discard)
        except Exception as exc:  # noqa: BLE001
            self._monitor_state = "error"
            self._last_error = str(exc)
            logger.exception("weixin monitor failed")
        finally:
            if self._monitor_state != "error":
                self._monitor_state = "stopped"
            logger.info("weixin monitor stopped")

    async def _handle_weixin_message(self, payload: dict[str, Any]) -> None:
        if int(payload.get("message_type") or 0) != 1:
            return
        sender_id = str(payload.get("from_user_id") or "").strip()
        context_token = str(payload.get("context_token") or "").strip()
        if not sender_id or not context_token:
            return
        self._context_tokens[sender_id] = context_token
        text = self._extract_text(payload.get("item_list") or [])
        reply = _WeixinReplyHandle(self, sender_id, context_token)
        message = ChannelInboundMessage(
            channel="weixin",
            sender_id=sender_id,
            text=text,
            session_id=resolve_channel_session_id(),
            reply=reply,
        )
        await handle_inbound_message(message)

    @staticmethod
    def _extract_text(item_list: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for item in item_list:
            if int(item.get("type") or 0) == 1:
                text = str((item.get("text_item") or {}).get("text") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()

    @staticmethod
    def _build_headers(token: str | None, body: str | None = None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "X-WECHAT-UIN": base64.b64encode(str(random.randint(1, 2**32 - 1)).encode("utf-8")).decode("utf-8"),
        }
        if body is not None:
            headers["Content-Length"] = str(len(body.encode("utf-8")))
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _api_get(
        self,
        base_url: str,
        endpoint: str,
        query: dict[str, Any] | None = None,
        timeout_seconds: int = 15,
    ) -> dict[str, Any]:
        url = urljoin(base_url, endpoint)
        if query:
            url = f"{url}?{urlencode(query)}"
        request = Request(url, method="GET")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except TimeoutError:
            raise
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise TimeoutError() from exc
            raise

    def _api_post(
        self,
        base_url: str,
        endpoint: str,
        body: dict[str, Any],
        timeout_seconds: int = 15,
    ) -> dict[str, Any]:
        payload = {**body, "base_info": {"channel_version": DEFAULT_CHANNEL_VERSION}}
        body_text = json.dumps(payload, ensure_ascii=False)
        url = urljoin(base_url, endpoint)
        request = Request(
            url,
            data=body_text.encode("utf-8"),
            headers=self._build_headers(self._auth.token, body_text),
            method="POST",
        )
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))


weixin_service = WeixinService()
