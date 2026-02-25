import asyncio
import threading

from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver
from whimbox.common.logger import logger
from whimbox.config.config import global_config
from whimbox.plugin_runtime import get_registry
from whimbox.plugin_tools import build_tools

class Agent:

    _instance = None
    _initialized = False

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
        self.memory = None
        self.tools = None
        self._registry = None
        self._active_session_id = "default"
        self._session_stop_events = {}
        self._tool_running_sessions = set()
        self._session_stream_tasks = {}

        self._initialized = True

    def _get_active_stop_event(self):
        return self._session_stop_events.get(self._active_session_id)

    async def start(self):
        logger.debug("开始初始化agent")
        self.err_msg = "准备中，请稍等..."
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
                    api_key=api_key
                )
            except Exception as e:
                self.llm = None
                self.err_msg = f"AI初始化失败。请前往设置，检查大模型相关配置。"
                logger.error(self.err_msg)

        # 初始化插件工具(不重复初始化)
        if self.tools is None:
            self._registry = get_registry()
            self.tools = build_tools(
                self._registry,
                session_id_getter=lambda: self._active_session_id,
                stop_event_getter=self._get_active_stop_event,
            )
            if self.tools:
                self.mcp_ready = True
                logger.debug(f"插件工具加载完成: {len(self.tools)}")
            else:
                self.err_msg = "未加载任何插件工具"
                logger.error(self.err_msg)
        
        # 初始化memory（不重复初始化）
        if self.memory is None:
            self.memory = MemorySaver()
        
        if self.llm and self.tools and self.memory:
            self.langchain_agent = create_react_agent(
                model=self.llm, 
                tools=self.tools, 
                checkpointer=self.memory, 
                prompt=global_config.prompt, 
                debug=False)
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
        logger.debug("开始调用大模型")
        config = {"configurable": {"thread_id": thread_id}}
        input = {"messages": [{"role": "user", "content": text}]}

        session_id = thread_id or "default"
        self._active_session_id = session_id
        stop_event = threading.Event()
        self._session_stop_events[session_id] = stop_event
        
        full_response = ""
        tool_running = False
        
        # 通知开始思考
        if status_callback:
            status_callback("thinking", "", None)
        
        async def _run_stream():
            nonlocal full_response, tool_running
            async for event in self.langchain_agent.astream_events(input, config=config):
                # 处理不同类型的流式事件
                event_type = event.get("event")
                data = event.get("data", {})

                if event_type == "on_chat_model_stream":
                    if stop_event.is_set():
                        break
                    chunk = data.get("chunk")
                    if chunk and hasattr(chunk, 'content') and chunk.content:
                        content = chunk.content
                        full_response += content
                        if stream_callback and content.strip():  # 只发送非空内容
                            stream_callback(content)

                elif event_type == "on_tool_start":
                    # 工具调用开始
                    tool_name = event.get("name", "")
                    tool_running = True
                    self._tool_running_sessions.add(session_id)
                    if status_callback:
                        status_callback("on_tool_start", tool_name, None)

                elif event_type == "on_tool_end":
                    # 工具调用结束
                    tool_name = event.get("name", "")
                    tool_running = False
                    self._tool_running_sessions.discard(session_id)
                    # if stream_callback:
                    #     stream_callback(f"💭 任务完成，总结成果中~\n")
                    if status_callback:
                        status_callback("on_tool_end", tool_name, {"output": data.get("output")})

                elif event_type == "on_tool_error":
                    # 工具调用错误
                    error = data.get("error", "")
                    tool_name = event.get("name", "")
                    tool_running = False
                    self._tool_running_sessions.discard(session_id)
                    if stream_callback:
                        stream_callback(f"❌ 任务失败: {error}\n")
                    if status_callback:
                        status_callback("on_tool_error", tool_name, {"error": error})

                elif event_type == "on_chat_model_start":
                    # 开始生成回复
                    if status_callback:
                        status_callback("generating", "", None)

                elif event_type == "on_chain_end":
                    # 整个链条结束，获取最终结果
                    output = data.get("output")
                    if output and hasattr(output, 'content'):
                        # 如果有最终内容，确保包含在响应中
                        if output.content and output.content not in full_response:
                            final_content = output.content
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

        logger.debug("大模型调用完成")
        return full_response

    def get_ai_message(self, resp):
        ai_msgs = []
        for msg in resp['messages']:
            if msg.type == 'ai':
                ai_msgs.append(msg.content)
        return '\n'.join(ai_msgs)

    def reload_tools(self):
        self._registry = get_registry()
        self.tools = build_tools(
            self._registry,
            session_id_getter=lambda: self._active_session_id,
            stop_event_getter=self._get_active_stop_event,
        )
        if self.tools:
            self.mcp_ready = True
            self.err_msg = ""
            logger.debug(f"插件工具重载完成: {len(self.tools)}")
        else:
            self.mcp_ready = False
            self.err_msg = "未加载任何插件工具"
            logger.error(self.err_msg)

mcp_agent = Agent()
