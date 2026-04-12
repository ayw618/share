import asyncio
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Dict, List

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Tool, CallToolResult


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
    async def list_tools(self):
        return await self.session.list_tools()
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


# 在 mcp_client.py 文件末尾添加
async def get_remote_tools(url: str) -> List[Dict[str, Any]]:
    """
    从远程 MCP 服务器获取工具列表，并转换为 OpenAI 格式
    
    Args:
        url: MCP 服务器 URL
        
    Returns:
        符合 OpenAI 工具格式的工具列表
    """
    client = RemoteMCPClient(url)
    openai_tools = []
    
    try:
        await client.connect()
        tools_response = await client.list_tools()
        
        for tool in tools_response.tools:
            # 构建 OpenAI 格式的工具
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema
                }
            }
            openai_tools.append(openai_tool)
            
        print(f"✅ 成功获取 {len(openai_tools)} 个远程工具")
        
    except Exception as e:
        print(f"获取远程工具失败: {str(e)}")
    finally:
        await client.close()
        
    return openai_tools
# 测试主函数
async def main():
    # client = RemoteMCPClient("https://calculator.caseyjhand.com/mcp")
    client = RemoteMCPClient("https://mcpmarket.cn/mcp/0542036c39c9056c228f4592")
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

        # 测试调用工具
        print("\n=== 测试调用远程工具 ===")
        
        # 测试 fetch 工具
        try:
            print("测试 fetch 工具...")
            result = await client.call("fetch", {"url": "https://mcp-docs.apifox.cn/6174083m0"})
            print(f"fetch 工具结果: {result[:200]}...")  # 只打印前200个字符
        except Exception as e:
            print(f"测试 fetch 工具失败: {str(e)}")
        
        # 测试其他工具（如果有）
        # 可以根据实际可用工具添加更多测试
        
        # 测试 get_remote_tools 函数
        tools = await get_remote_tools(client.url)
        print(f"\n=== 测试 get_remote_tools 函数 ===")
        print(f"转换后的工具数量: {len(tools)}")
        for tool in tools:
            print(f"工具名称: {tool['function']['name']}")
        
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())