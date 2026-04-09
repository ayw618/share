import asyncio
from mcp_client import RemoteMCPClient

# 远程MCP服务器地址（你提供的）
REMOTE_MCP_URL = "https://arxiv.caseyjhand.com/mcp"


async def main():
    # 初始化远程客户端
    client = RemoteMCPClient(REMOTE_MCP_URL)
    
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
