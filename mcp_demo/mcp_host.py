import asyncio
from mcp_client import MCPClient

class MCPHost:
    def __init__(self):
        self.client = MCPClient()

    async def start(self):
        """启动本地MCP系统"""
        print("="*50)
        print("🚀 本地MCP Host 启动中...")
        print("="*50)

        try:
            # 连接服务器
            await self.client.connect_to_server("share/mcp_demo/mcp_local_server.py")
            # 进入交互循环
            await self.chat_loop()
        finally:
            # 自动清理资源
            await self.client.cleanup()
            print("\n👋 MCP系统已安全关闭")

    async def chat_loop(self):
        """交互式命令行循环"""
        print("\n📖 命令说明:")
        print("   add 数字1 数字2  → 计算加法")
        print("   time            → 获取当前时间")
        print("   quit            → 退出程序")
        print("-"*50)

        while True:
            query = input("\n请输入指令: ").strip()
            if not query:
                continue
            if query.lower() == "quit":
                break

            # 解析指令
            await self._handle_command(query)

    async def _handle_command(self, query: str):
        """处理用户指令"""
        parts = query.split()
        cmd = parts[0].lower()

        try:
            if cmd == "add" and len(parts) == 3:
                a = float(parts[1])
                b = float(parts[2])
                res = await self.client.call_tool("add", {"a": a, "b": b})
                print(f"📝 加法结果: {res}")

            elif cmd == "time":
                res = await self.client.call_tool("get_current_time", {})
                print(f"📝 当前时间: {res}")

            else:
                print("⚠️ 无效指令，请输入 add / time / quit")
                
        except Exception as e:
            print(f"❌ 执行失败: {str(e)}")

# 启动程序
if __name__ == "__main__":
    host = MCPHost()
    asyncio.run(host.start())
