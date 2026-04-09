from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent
from datetime import datetime

# 创建MCP服务器实例，使用 FastMCP (高层 API)
server = FastMCP("simple-local-server")

# --------------------------
# 定义工具（Tools）
# --------------------------
@server.tool()
def add(a: float, b: float) -> float:
    """
    计算两个数的和
    Args:
        a: 第一个数
        b: 第二个数
    Returns:
        两数之和
    """
    return a + b

@server.tool()
def get_current_time() -> str:
    """
    获取当前系统时间
    Returns:
        格式化的时间字符串
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# --------------------------
# 定义资源（Resources）
# --------------------------
@server.resource("config://server-info")
def get_server_info() -> TextContent:
    """返回服务器基本信息（静态资源）"""
    return TextContent(
        text="Simple Local MCP Server v1.0.0\n支持工具：加法计算(add)、获取时间(get_current_time)"
    )

# 运行服务器（默认使用STDIO传输层，与Client通信）
if __name__ == "__main__":
    server.run()
