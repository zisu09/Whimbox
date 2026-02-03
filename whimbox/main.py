import asyncio

from whimbox.plugin_runtime import init_plugins
from whimbox.mcp_agent import mcp_agent
from whimbox.rpc_server import start_rpc_server


def main():
    init_plugins()
    asyncio.run(mcp_agent.start())
    asyncio.run(start_rpc_server())


if __name__ == "__main__":
    main()