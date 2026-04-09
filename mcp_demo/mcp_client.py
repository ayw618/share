import asyncio
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Dict, List

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Tool, CallToolResult

class MCPClient:
    def __init__(self):
        # 官方标准：异步上下文栈 + 会话管理
        self.exit_stack = AsyncExitStack()
        self.session: ClientSession | None = None
        self.available_tools: List[Tool] = []

    async def connect_to_server(self, server_script_path: str = "mcp_server.py"):
        """
        官方标准方式连接本地MCP Server
        Args:
            server_script_path: 服务器py文件路径
        """
        # 校验服务器文件
        path = Path(server_script_path).resolve()
        if not path.exists() or not path.suffix == ".py":
            raise ValueError("无效的MCP服务器Python文件")

        # 官方标准：定义STDIO服务器参数
        server_params = StdioServerParameters(
            command="python",
            args=[str(path)],
            env=None
        )

        # 建立传输连接 + 客户端会话
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.read_stream, self.write_stream = stdio_transport
        
        # 初始化MCP会话
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(self.read_stream, self.write_stream)
        )
        await self.session.initialize()

        # 获取服务器所有工具
        tools_response = await self.session.list_tools()
        self.available_tools = tools_response.tools
        print(f"✅ 连接MCP服务器成功 | 可用工具: {[t.name for t in self.available_tools]}")

    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        官方标准工具调用
        """
        if not self.session:
            raise RuntimeError("未连接到MCP服务器")

        # 调用工具
        result: CallToolResult = await self.session.call_tool(tool_name, arguments)
        
        # 解析返回结果（兼容MCP标准格式）
        if result.content:
            content = result.content[0]
            if hasattr(content, "text"):
                return content.text
            if hasattr(content, "value"):
                return content.value
        return "工具执行无返回结果"

    async def cleanup(self):
        """官方标准：清理所有资源"""
        await self.exit_stack.aclose()
        
# 极简远程MCP客户端（核心逻辑）
class RemoteMCPClient:
    def __init__(self, url: str):
        self.url = url
        self.exit_stack = AsyncExitStack()
        self.session = None

    async def connect(self):
        try:
            read, write, _ = await self.exit_stack.enter_async_context(
                streamable_http_client(self.url)
            )
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await asyncio.wait_for(self.session.initialize(), timeout=15.0)
        except Exception:
            sse_url = self.url.rstrip("/")
            if not sse_url.endswith("/sse"):
                sse_url = sse_url + "/sse"
            transport = await self.exit_stack.enter_async_context(
                sse_client(sse_url)
            )
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(transport.read, transport.write)
            )
            await asyncio.wait_for(self.session.initialize(), timeout=15.0)
        # 打印可用工具
        tools = await self.session.list_tools()
        print(f"✅ 连接成功 | 可用工具：{[t.name for t in tools.tools]}")

    async def call(self, tool_name: str, args: dict):
        # 调用工具
        res: CallToolResult = await self.session.call_tool(tool_name, args)
        if res.content:
            block = res.content[0]
            if hasattr(block, "text"):
                return block.text
            if hasattr(block, "value"):
                return block.value
        return "无结果"

    async def close(self):
        # 清理资源
        await self.exit_stack.aclose()

# 测试主函数
async def main():
    client = RemoteMCPClient("https://calculator.caseyjhand.com/mcp")
    try:
        await client.connect()
        # 获取并打印工具列表及其参数详情
        resp = await client.session.list_tools()
        client.available_tools = resp.tools
        
        print(f"✅ 连接成功 | 发现 {len(client.available_tools)} 个工具")
        
        for tool in client.available_tools:
            print(f"\n🛠️  工具: {tool.name}")
            print(f"   📝 描述: {tool.description}")
            
            # 关键：从 inputSchema 获取参数定义
            schema = tool.inputSchema
            props = schema.get("properties", {})
            required = schema.get("required", [])
            
            if props:
                print("   📥 参数详情:")
                for p_name, p_info in props.items():
                    p_type = p_info.get("type", "unknown")
                    is_req = " (必填)" if p_name in required else " (可选)"
                    print(f"      - {p_name} [{p_type}]{is_req}")
            else:
                print("   📥 无需参数")
        
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
