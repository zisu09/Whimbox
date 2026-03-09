import asyncio
import threading

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model

from whimbox.agent_workspace import AgentWorkspace, ContextBuilder, MemoryStore, SessionManager
from whimbox.agent_workspace.tools import build_workspace_tools
from whimbox.common.logger import logger
from whimbox.config.config import global_config
from whimbox.plugin_runtime import get_registry
from whimbox.plugin_tools import build_tools
from whimbox.common.cvars import DEBUG_MODE


class Agent:
    _instance = None
    _initialized = False
    _memory_window = 100

    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super(Agent, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.langchain_agent = None
        self.err_msg = ""
        self.mcp_ready = False
        self.llm = None
        self.tools = None
        self._registry = None
        self._active_session_id = "default"
        self._session_stop_events = {}
        self._tool_running_sessions = set()
        self._session_stream_tasks = {}
        self.workspace = AgentWorkspace()
        self.context_builder = None
        self.memory_store = None
        self.session_manager = None

        self._initialized = True

    def _get_active_stop_event(self):
        return self._session_stop_events.get(self._active_session_id)

    async def start(self):
        logger.debug("开始初始化agent")
        self.err_msg = "准备中，请稍等..."
        self.workspace.ensure()
        if self.context_builder is None:
            self.context_builder = ContextBuilder(self.workspace.root)
        if self.memory_store is None:
            self.memory_store = MemoryStore(self.workspace.root)
        if self.session_manager is None:
            self.session_manager = SessionManager(self.workspace.sessions_dir)

        api_key = global_config.get("Agent", "api_key")
        if not api_key:
            self.langchain_agent = None
            self.err_msg = "请先前往设置，配置大模型的api密钥。不会配置？点开通知，里面有详细白嫖教程！"
            self.llm = None
            logger.error(self.err_msg)
        else:
            try:
                self.llm = init_chat_model(
                    model=global_config.get("Agent", "model"),
                    model_provider=global_config.get("Agent", "model_provider"),
                    base_url=global_config.get("Agent", "base_url"),
                    api_key=api_key,
                )
            except Exception:
                self.llm = None
                self.err_msg = "AI初始化失败。请前往设置，检查大模型相关配置。"
                logger.error(self.err_msg)

        self._rebuild_tools()

        if self.llm and self.tools and self.context_builder and self.session_manager:
            self.langchain_agent = create_agent(
                model=self.llm,
                tools=self.tools,
                debug=DEBUG_MODE,
            )
            self.err_msg = ""
            logger.debug("MCP AGENT 初始化完成")
        else:
            self.langchain_agent = None
            logger.error("MCP AGENT 初始化失败")

    def is_ready(self):
        agent_ready = self.langchain_agent is not None
        return agent_ready, self.mcp_ready, self.err_msg

    def request_stop(self, session_id: str):
        logger.debug(f"request_stop: session_id={session_id}")
        sid = session_id or "default"
        stop_event = self._session_stop_events.get(sid)
        stream_task = self._session_stream_tasks.get(sid)
        if stop_event is None and stream_task is None:
            return {"ok": False, "tool_running": sid in self._tool_running_sessions}
        if stop_event is not None:
            stop_event.set()
        return {"ok": True, "tool_running": sid in self._tool_running_sessions}

    def request_stop_all(self):
        session_ids = set(self._session_stop_events.keys()) | set(self._session_stream_tasks.keys())
        results = []
        for sid in session_ids:
            stop_event = self._session_stop_events.get(sid)
            if stop_event is not None:
                stop_event.set()
            results.append(
                {
                    "session_id": sid,
                    "tool_running": sid in self._tool_running_sessions,
                }
            )
        return results

    async def query_agent(self, text, thread_id="default", stream_callback=None, status_callback=None):
        if not self.langchain_agent:
            err_msg = self.err_msg or "Agent 未就绪，请先完成初始化。"
            if status_callback:
                status_callback("error", err_msg, None)
            raise RuntimeError(err_msg)

        session_id = thread_id or "default"
        self._active_session_id = session_id
        session = self.session_manager.get_or_create(session_id)
        input_payload = {
            "messages": self.context_builder.build_messages(
                history=session.get_history(max_messages=self._memory_window),
                current_message=text,
                session_id=session_id,
            )
        }

        logger.debug("开始调用大模型")
        stop_event = threading.Event()
        self._session_stop_events[session_id] = stop_event

        full_response = ""
        tools_used = []

        if status_callback:
            status_callback("thinking", "", None)

        async def _run_stream():
            nonlocal full_response
            async for event in self.langchain_agent.astream_events(input_payload):
                event_type = event.get("event")
                data = event.get("data", {})

                if event_type == "on_chat_model_stream":
                    if stop_event.is_set():
                        break
                    content = self._extract_chunk_text(data.get("chunk"))
                    if content:
                        full_response += content
                        if stream_callback and content.strip():
                            stream_callback(content)

                elif event_type == "on_tool_start":
                    tool_name = event.get("name", "")
                    if tool_name and tool_name not in tools_used:
                        tools_used.append(tool_name)
                    self._tool_running_sessions.add(session_id)
                    if status_callback:
                        status_callback("on_tool_start", tool_name, None)

                elif event_type == "on_tool_end":
                    tool_name = event.get("name", "")
                    self._tool_running_sessions.discard(session_id)
                    if status_callback:
                        status_callback("on_tool_end", tool_name, {"output": data.get("output")})

                elif event_type == "on_tool_error":
                    error = data.get("error", "")
                    tool_name = event.get("name", "")
                    self._tool_running_sessions.discard(session_id)
                    if stream_callback:
                        stream_callback(f"❌ 任务失败: {error}\n")
                    if status_callback:
                        status_callback("on_tool_error", tool_name, {"error": error})

                elif event_type == "on_chat_model_start":
                    if status_callback:
                        status_callback("generating", "", None)

                elif event_type == "on_chain_end":
                    final_content = self._extract_output_text(data.get("output"))
                    if final_content and not full_response.strip():
                        full_response += final_content
                        if stream_callback:
                            stream_callback(final_content)

        stream_task = asyncio.create_task(_run_stream())
        self._session_stream_tasks[session_id] = stream_task
        try:
            await stream_task
        except asyncio.CancelledError:
            logger.info(f"Agent stream cancelled: session={session_id}")
        finally:
            self._session_stream_tasks.pop(session_id, None)
            self._session_stop_events.pop(session_id, None)
            self._tool_running_sessions.discard(session_id)

        if stop_event.is_set() and not full_response.strip():
            full_response = "已停止当前对话。"

        self._save_session_turn(session, user_text=text, assistant_text=full_response, tools_used=tools_used)
        if self.memory_store and self.llm:
            await self.memory_store.consolidate(
                session=session,
                llm=self.llm,
                memory_window=self._memory_window,
            )
        self.session_manager.save(session)

        logger.debug("大模型调用完成")
        return full_response

    def get_ai_message(self, resp):
        ai_msgs = []
        for msg in resp["messages"]:
            if msg.type == "ai":
                ai_msgs.append(msg.content)
        return "\n".join(ai_msgs)

    def reload_tools(self):
        self._rebuild_tools()
        if self.tools:
            self.mcp_ready = True
            self.err_msg = ""
            logger.debug(f"插件工具重载完成: {len(self.tools)}")
        else:
            self.mcp_ready = False
            self.err_msg = "未加载任何插件工具"
            logger.error(self.err_msg)

    def _rebuild_tools(self):
        self._registry = get_registry()
        plugin_tools = build_tools(
            self._registry,
            session_id_getter=lambda: self._active_session_id,
            stop_event_getter=self._get_active_stop_event,
        )
        workspace_tools = build_workspace_tools(self.workspace.root)
        self.tools = [*plugin_tools, *workspace_tools]
        self.mcp_ready = bool(plugin_tools)

    def _save_session_turn(self, session, user_text: str, assistant_text: str, tools_used: list[str]) -> None:
        session.add_message("user", user_text)
        if assistant_text:
            session.add_message("assistant", assistant_text, tools_used=tools_used)

    def _extract_chunk_text(self, chunk) -> str:
        if hasattr(chunk, "content"):
            return self._extract_output_text(chunk)
        return ""

    def _extract_output_text(self, output) -> str:
        if output is None:
            return ""
        if isinstance(output, dict):
            messages = output.get("messages")
            if isinstance(messages, list):
                for item in reversed(messages):
                    item_type = getattr(item, "type", "")
                    if item_type in {"ai", "assistant"}:
                        return self._extract_output_text(item)
                    if isinstance(item, dict) and item.get("role") == "assistant":
                        return self._extract_output_text(item.get("content"))
            if "content" in output:
                return self._extract_output_text(output.get("content"))
            return ""
        content = getattr(output, "content", output)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif isinstance(item, str):
                    parts.append(item)
            return "".join(parts)
        return str(content)


whimbox_agent = Agent()
