import ast
import inspect
import os
import re
from string import Template
from typing import List, Callable, Tuple, Any, Dict
import json
import click
from dotenv import load_dotenv
from openai import OpenAI
import platform
import requests
import asyncio
from mcp_client import get_remote_tools
from prompt_template import react_system_prompt_template
from prompt_template_v2 import react_system_prompt_template_v2
from mcp_client import RemoteMCPClient

class ReActAgent:
    def __init__(self, tools: List[Callable], model: str, project_directory: str, mcp_base_urls: List[str] = None):
        self.tools = { func.__name__: func for func in tools }
        self.model = model
        self.project_directory = project_directory
        self.mcp_base_urls = mcp_base_urls or [] 
        self.client = OpenAI(
            base_url='https://api-inference.modelscope.cn/v1',
            api_key=ReActAgent.get_api_key(),
        )
        self.tools_openai = self.get_openai_tools()

    def run(self, user_input: str):
        messages = [
            {"role": "system", "content": self.render_system_prompt(react_system_prompt_template)},
            {"role": "user", "content": f"<question>{user_input}</question>"}
        ]

        while True:

            # 请求模型
            content, tool_calls = self.call_model(messages)

            # 检测 Thought
            thought_match = re.search(r"<thought>(.*?)</thought>", content, re.DOTALL)
            if thought_match:
                thought = thought_match.group(1)
                print(f"\n\n💭 Thought: {thought}")

            # 检测模型是否输出 Final Answer，如果是的话，直接返回
            if "<final_answer>" in content:
                print(json.dumps(messages, ensure_ascii=False, indent=2))
                final_answer = re.search(r"<final_answer>(.*?)</final_answer>", content, re.DOTALL)
                return final_answer.group(1)

            # 检测 Action
            action_match = re.search(r"<action>(.*?)</action>", content, re.DOTALL)
            if not action_match:
                # raise RuntimeError("模型未输出 <action>")
                error_msg = "模型未输出 <action> 或 </action> 标签"
                print(f"\n\n🔍 Observation：{error_msg}")
                obs_msg = f"<observation>{error_msg}</observation>"
                messages.append({"role": "user", "content": obs_msg})
                continue
            action = action_match.group(1)
            tool_name, args = self.parse_action_dict(action)
            # 检查是否解析错误
            if tool_name == "__ERROR__":
                error_msg = args.get("error", "工具调用格式错误")
                print(f"\n\n🔍 Observation：{error_msg}")
                obs_msg = f"<observation>{error_msg}</observation>"
                messages.append({"role": "user", "content": obs_msg})
                continue

            print(f"\n\n🔧 Action: {tool_name}({json.dumps(args, ensure_ascii=False, indent=2)})")
            # 只有终端命令才需要询问用户，其他的工具直接执行
            should_continue = input(f"\n\n是否继续？（Y/N）") if tool_name == "run_terminal_command" else "y"
            if should_continue.lower() != 'y':
                print("\n\n操作已取消。")
                return "操作被用户取消"

            try:
                observation = self.call_tool(tool_name, args)
            except Exception as e:
                observation = f"工具执行错误：{str(e)}"
            print(f"\n\n🔍 Observation：{observation}")
            obs_msg = f"<observation>{observation}</observation>"

            # 添加到消息
            messages.append({"role": "user", "content": obs_msg})

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """生成 OpenAI 格式的工具列表"""
        openai_tools = []
        
        # 本地工具
        for func in self.tools.values():
            name = func.__name__
            doc = inspect.getdoc(func) or ""
            signature = inspect.signature(func)
            
            # 构建参数 schema
            parameters = {
                "type": "object",
                "properties": {},
                "required": []
            }
            
            for param_name, param in signature.parameters.items():
                # 简单处理，实际应根据参数类型生成对应 schema
                parameters["properties"][param_name] = {
                    "type": "string",
                    "description": f"{param_name} 参数"
                }
                # 非可选参数
                if param.default == inspect.Parameter.empty:
                    parameters["required"].append(param_name)
            
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": doc,
                    "parameters": parameters
                }
            })
        
        # 远程 MCP 工具（如果有）
        for base_url in self.mcp_base_urls:
            remote_tools = asyncio.run(get_remote_tools(base_url))
            openai_tools.extend(remote_tools)
        
        return openai_tools
    # def runv2(self, user_input: str):
    #     # 生成 OpenAI 格式的工具列表
    #     openai_tools = self.get_openai_tools()
        
    #     messages = [
    #         {"role": "system", "content": self.render_system_prompt(react_system_prompt_template_v2)},
    #         {"role": "user", "content": user_input}
    #     ]

    #     while True:
    #         # 请求模型，传递 tools 参数
    #         response = self.client.chat.completions.create(
    #             model=self.model,
    #             messages=messages,
    #             tools=openai_tools,
    #             tool_choice="auto"  # 让模型自动决定是否使用工具
    #         )
            
    #         content = response.choices[0].message.content
    #         tool_calls = response.choices[0].message.tool_calls
            
    #         # 添加模型响应到消息
    #         messages.append({
    #             "role": "assistant",
    #             "content": content,
    #             "tool_calls": tool_calls
    #         })
            
    #         # 如果有工具调用，执行工具
    #         if tool_calls:
    #             for tool_call in tool_calls:
    #                 tool_name = tool_call.function.name
    #                 args = json.loads(tool_call.function.arguments)
                    
    #                 print(f"\n\n🔧 Action: {tool_name}({', '.join([f'{k}={v}' for k, v in args.items()])})")
                    
    #                 # 只有终端命令才需要询问用户
    #                 should_continue = input(f"\n\n是否继续？（Y/N）") if tool_name == "run_terminal_command" else "y"
    #                 if should_continue.lower() != 'y':
    #                     print("\n\n操作已取消。")
    #                     return "操作被用户取消"
                    
    #                 try:
    #                     # 执行本地工具
    #                     if tool_name in self.tools:
    #                         observation = self.tools[tool_name](**args)
    #                     # 执行远程 MCP 工具（如果实现）
    #                     else:
    #                         # 调用远程 MCP 工具
    #                         observation = asyncio.run(self.call_remote_tool(tool_name, args))
    #                 except Exception as e:
    #                     print(tool_name, args, e)
    #                     observation = f"工具执行错误：{str(e)}"
                    
    #                 print(f"\n\n🔍 Observation：{observation}")
                    
    #                 # 添加工具执行结果到消息
    #                 messages.append({
    #                     "role": "tool",
    #                     "tool_call_id": tool_call.id,
    #                     "name": tool_name,
    #                     "content": str(observation)
    #                 })
    #         else:
    #             # 没有工具调用，返回模型的直接回答
    #             return content
    
    def call_tool(self, tool_name: str, args: dict) -> str:
        """
        执行工具，支持本地工具和远程 MCP 工具
        
        Args:
            tool_name: 工具名称
            args: 工具参数
            
        Returns:
            工具执行结果
        """
        # 执行本地工具
        if tool_name in self.tools:
            try:
                args_list = list(args.values())
                observation = self.tools[tool_name](*args_list)
                return str(observation)
            except Exception as e:
                return f"工具执行错误：{str(e)}"
        # 执行远程 MCP 工具
        elif self.mcp_base_urls:
            # 执行异步函数
            try:
                return asyncio.run(self.call_remote_tool(tool_name, args))
            except Exception as e:
                return f"远程工具调用失败：{str(e)}"
        else:
            return f"工具 {tool_name} 未找到"

    def get_tool_list(self) -> str:
        """生成工具列表字符串，包含函数签名和简要说明"""
        # 从 get_openai_tools 获取所有工具
        openai_tools = self.tools_openai
        
        # 构建工具描述列表
        tool_descriptions = []
        for tool in openai_tools:
            function = tool["function"]
            name = function["name"]
            
            # 从 parameters 构建签名
            params = function["parameters"]
            param_list = []
            for param_name, param_info in params.get("properties", {}).items():
                param_type = param_info.get("type", "any")
                param_list.append(f"{param_name}: {param_type}")
            signature = f"({', '.join(param_list)})" if param_list else "()"
            
            doc = function["description"]
            tool_descriptions.append(f"- {name}{signature}: {doc}")

        return "\n".join(tool_descriptions)
    # 创建一个异步函数来调用远程工具
    async def call_remote_tool(self, tool_name, args):
        """调用远程 MCP 工具"""
        from mcp_client import RemoteMCPClient
        
        # 尝试连接每个 MCP 服务器
        for url in self.mcp_base_urls:
            client = None
            try:
                client = RemoteMCPClient(url)
                await client.connect()
                
                if not client.session:
                    continue  # 连接失败，尝试下一个服务器
                
                # 检查工具是否可用
                tools_response = await client.list_tools()
                available_tools = [t.name for t in tools_response.tools]
                
                if tool_name in available_tools:
                    # 调用工具
                    result = await client.call(tool_name, args)
                    return result
            except Exception as e:
                print(f"连接 MCP 服务器 {url} 失败: {str(e)}")
            finally:
                if client:
                    try:
                        await client.close()
                    except:
                        pass
        
        return f"未找到可用的 MCP 服务器提供工具 {tool_name}"
    
    def render_system_prompt(self, system_prompt_template: str) -> str:
        """渲染系统提示模板，替换变量"""
        tool_list = self.get_tool_list()
        file_list = ", ".join(
            os.path.abspath(os.path.join(self.project_directory, f))
            for f in os.listdir(self.project_directory)
        )
        return Template(system_prompt_template).substitute(
            operating_system=self.get_operating_system_name(),
            tool_list=tool_list,
            file_list=file_list
        )

    @staticmethod
    def get_api_key() -> str:
        """Load the API key from an environment variable."""
        load_dotenv()
        api_key = os.getenv("MODELSCOPE_API_KEY")
        if not api_key:
            raise ValueError("未找到 MODELSCOPE_API_KEY 环境变量，请在 .env 文件中设置。")
        return api_key

    def call_model(self, messages):

        print("正在请求工具")
        tools = self.tools_openai
        print("\n\n正在请求模型，请稍等...")
        response = self.client.chat.completions.create(
            model=self.model,
            tools=tools,
            messages=messages,
            tool_choice="auto"  # 让模型自动决定是否使用工具
        )
        content = response.choices[0].message.content
        tool_calls = response.choices[0].message.tool_calls
        messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
        return content, tool_calls

    # def parse_action(self, code_str: str) -> Tuple[str, List[str]]:
    #     match = re.match(r'(\w+)\((.*)\)', code_str, re.DOTALL)
    #     if not match:
    #         raise ValueError("Invalid function call syntax")

    #     func_name = match.group(1)
    #     args_str = match.group(2).strip()

    #     # 手动解析参数，特别处理包含多行内容的字符串
    #     args = []
    #     current_arg = ""
    #     in_string = False
    #     string_char = None
    #     i = 0
    #     paren_depth = 0
        
    #     while i < len(args_str):
    #         char = args_str[i]
            
    #         if not in_string:
    #             if char in ['"', "'"]:
    #                 in_string = True
    #                 string_char = char
    #                 current_arg += char
    #             elif char == '(':
    #                 paren_depth += 1
    #                 current_arg += char
    #             elif char == ')':
    #                 paren_depth -= 1
    #                 current_arg += char
    #             elif char == ',' and paren_depth == 0:
    #                 # 遇到顶层逗号，结束当前参数
    #                 args.append(self._parse_single_arg(current_arg.strip()))
    #                 current_arg = ""
    #             else:
    #                 current_arg += char
    #         else:
    #             current_arg += char
    #             if char == string_char and (i == 0 or args_str[i-1] != '\\'):
    #                 in_string = False
    #                 string_char = None
            
    #         i += 1
        
    #     # 添加最后一个参数
    #     if current_arg.strip():
    #         args.append(self._parse_single_arg(current_arg.strip()))
        
    #     return func_name, args
    
    def parse_action_dict(self, code_str: str) -> Tuple[str, dict]:
        """
        解析工具调用字符串，返回函数名和参数字典
        
        Args:
            code_str: 工具调用字符串，如 "fetch(url=\"https://example.com\", max_length=5000)"
            
        Returns:
            包含函数名和参数字典的元组
        """
        #match = re.match(r'([\w-]+)', code_str)
        # match = re.match(r'(\w+)\((.*)\)', code_str, re.DOTALL)
        match = re.match(fr'([\w-]+)\((.*)\)', code_str, re.DOTALL)
        if not match:
            print(code_str)
            return ("__ERROR__", {"error": f"工具调用格式错误，请使用正确的格式：function_name(parameters)"})

        func_name = match.group(1)
        args_str = match.group(2).strip()

        # 手动解析参数，特别处理包含多行内容的字符串
        args_dict = {}
        current_arg = ""
        in_string = False
        string_char = None
        i = 0
        paren_depth = 0
        current_key = None
        
        try:
            while i < len(args_str):
                char = args_str[i]
                
                if not in_string:
                    if char in ['"', "'"]:
                        in_string = True
                        string_char = char
                        current_arg += char
                    elif char == '(':
                        paren_depth += 1
                        current_arg += char
                    elif char == ')':
                        paren_depth -= 1
                        current_arg += char
                    elif char == '=' and paren_depth == 0 and not current_key:
                        # 遇到等号，当前内容为参数名
                        current_key = current_arg.strip()
                        current_arg = ""
                    elif char == ',' and paren_depth == 0:
                        # 遇到顶层逗号，结束当前参数
                        if current_key:
                            # 命名参数
                            args_dict[current_key] = self._parse_single_arg(current_arg.strip())
                        elif current_arg.strip():
                            # 位置参数，使用索引作为键
                            args_dict[str(len(args_dict))] = self._parse_single_arg(current_arg.strip())
                        current_key = None
                        current_arg = ""
                    else:
                        current_arg += char
                else:
                    current_arg += char
                    if char == string_char and (i == 0 or args_str[i-1] != '\\'):
                        in_string = False
                        string_char = None
                
                i += 1
            
            # 添加最后一个参数
            if current_arg.strip():
                if current_key:
                    # 命名参数
                    args_dict[current_key] = self._parse_single_arg(current_arg.strip())
                else:
                    # 位置参数，使用索引作为键
                    args_dict[str(len(args_dict))] = self._parse_single_arg(current_arg.strip())
            
            return func_name, args_dict
        except Exception as e:
            print(code_str, e)
            return ("__ERROR__", {"error": f"工具调用参数解析错误：{str(e)}"})
    def _parse_single_arg(self, arg_str: str):
        """解析单个参数"""
        arg_str = arg_str.strip()
        
        # 如果是字符串字面量
        if (arg_str.startswith('"') and arg_str.endswith('"')) or \
           (arg_str.startswith("'") and arg_str.endswith("'")):
            # 移除外层引号并处理转义字符
            inner_str = arg_str[1:-1]
            # 处理常见的转义字符
            inner_str = inner_str.replace('\\"', '"').replace("\\'", "'")
            inner_str = inner_str.replace('\\n', '\n').replace('\\t', '\t')
            inner_str = inner_str.replace('\\r', '\r').replace('\\\\', '\\')
            return inner_str
        
        # 尝试使用 ast.literal_eval 解析其他类型
        try:
            return ast.literal_eval(arg_str)
        except (SyntaxError, ValueError):
            # 如果解析失败，返回原始字符串
            return arg_str

    def get_operating_system_name(self):
        os_map = {
            "Darwin": "macOS",
            "Windows": "Windows",
            "Linux": "Linux"
        }

        return os_map.get(platform.system(), "Unknown")

# ----- tools -----
def read_file(file_path):
    """用于读取文件内容"""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def write_to_file(file_path, content):
    """将指定内容写入指定文件"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content.replace("\\n", "\n"))
    return "写入成功"

def run_terminal_command(command):
    """
    用于执行终端命令
    
    Args:
        command: 终端命令字符串
    Returns:
        执行结果字符串
    """
    import subprocess
    run_result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return "执行成功" if run_result.returncode == 0 else run_result.stderr

def rewrite_query(query):
    """
    用户查询里太多模糊字段，用于重写查询
    Args:
        query: 用户的模糊查询
    Returns:
        rewrite_query: 重写后的具体查询
    """
    prompt = f"""
    请根据用户查询，重写查询，使查询更具体。
    用户查询：{query}
    """
    
    message = [{"role": "user", "content": prompt}]
    client = OpenAI(
        base_url='https://api-inference.modelscope.cn/v1',
        api_key=ReActAgent.get_api_key(),
    )
    response = client.chat.completions.create(
        model='Qwen/Qwen3-Coder-480B-A35B-Instruct',
        messages=message,
    )
    content = response.choices[0].message.content
    return "重写后的查询：" + f"{content}"

def recognize_intent(query):
    """
    根据用户查询，识别用户意图
    Args:
        query: 用户查询
    Returns:
        intent: 用户意图描述
    """
    prompt = f"""
    请根据用户查询，识别用户意图。
    用户查询：{query}
    """
    message = [{"role": "user", "content": prompt}]
    client = OpenAI(
        base_url='https://api-inference.modelscope.cn/v1',
        api_key=ReActAgent.get_api_key(),
    )
    response = client.chat.completions.create(
        model='Qwen/Qwen3-Coder-480B-A35B-Instruct',
        messages=message,
    )
    content = response.choices[0].message.content
    return "用户意图：" + f"{content}"

def continue_to_ask(ask_content: str):
    """
    用户意图还不够清晰，模型无法得到明确的目的，需要进一步追问用户意图得到具体的意图描述
    Args:
        ask_content: 需要向用户询问的内容
    Returns:
        query: 用户输入的内容
    """

    # 处理命名参数的情况
    if ask_content.startswith('ask_content='):
        # 提取等号后面的内容
        ask_content = ask_content[len('ask_content='):]
        # 去除引号
        if (ask_content.startswith('"') and ask_content.endswith('"')) or \
           (ask_content.startswith("'") and ask_content.endswith("'")):
            ask_content = ask_content[1:-1]
    
    print(f"\n\nAI询问：{ask_content}")
    query = input(f"用户输入：")
    return query

def create(
    instruction_config: str="",
    interaction_config: str="", 
    tools_config: str="", 
    instruction_generator: str="",
    interaction: str="",
    tools: str="",
    reward_function: str=""
):
    """
    说明：可以创建7类文件，instruction_config、interaction_config、tools_config配置文件为yaml格式，instruction_generator、interaction、tools、reward_function为代码文件为python格式
    Args:
        instruction_config: 指令配置文件名称
        interaction_config: 交互配置文件名称
        tools_config: 工具配置文件名称
        instruction_generator: 指令生成器代码文件名称
        interaction: 交互代码文件名称
        tools: 工具代码文件名称
        reward_function: 奖励函数代码文件名称
    Returns:
        answer: 最终的创建结果说明
    """
    # 项目根目录
    ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
    # 最终的回答
    answer = ""
    # 调用大模型
    client = OpenAI(
        base_url='https://api-inference.modelscope.cn/v1',
        api_key=ReActAgent.get_api_key(),
    )
    
    # 进行指令配置文件创建
    if instruction_config:
        instruction_config_path = os.path.join(ROOT_DIR, f"{instruction_config}.yaml")
        # 根据特有的指令配置提示词模板，创建指令配置文件
        prompt_instruction_config = f"""
        生成指令配置的yaml文件，用```yaml ``` 包裹内容
        """
        # 调用大模型
        response = client.chat.completions.create(
            model='Qwen/Qwen3-Coder-480B-A35B-Instruct',
            messages=[{"role": "user", "content": prompt_instruction_config}],
        )
        content = response.choices[0].message.content
        yaml_match = re.search(r"```yaml(.*?)```", content, re.DOTALL)
        if yaml_match:
            yaml_content = yaml_match.group(1)
        # 写入文件
        with open(instruction_config_path, "w", encoding="utf-8") as f:
            f.write(yaml_content.replace("\\n", "\n"))
        answer.append(f"已完成创建指令配置文件{instruction_config_path}")
    # 其他文件的创建同理






    return "，".join(answer)

def create_py(content):
    """
    创建工具
    Args:
        args: 工具参数
    Returns:
        answer: 工具创建结果说明
    """
    return create(
        instruction_config=args["instruction_config"],
        interaction_config=args["interaction_config"],
        tools_config=args["tools_config"],
        instruction_generator=args["instruction_generator"],
        interaction=args["interaction"],
        tools=args["tools"],
        reward_function=args["reward_function"]
    )
@click.command()
@click.argument('project_directory',
                type=click.Path(exists=True, file_okay=False, dir_okay=True))
def main(project_directory):
    project_dir = os.path.abspath(project_directory)

    tools = [read_file, write_to_file, run_terminal_command, continue_to_ask]
    mcp_base_urls = [
        "https://mcpmarket.cn/mcp/0542036c39c9056c228f4592", 
        "https://mcpmarket.cn/mcp/5e836ae41d7d3c35f7d4ba89",
        "https://mcpmarket.cn/mcp/17f1653efa4f96e5603b815a",
        "https://mcpmarket.cn/mcp/ca3c2ca3ca76c3e144389bf9"
    ]
    agent = ReActAgent(tools=tools, model='Qwen/Qwen3-Coder-480B-A35B-Instruct', project_directory=project_dir, mcp_base_urls=mcp_base_urls)

    task = input("请输入任务：")

    final_answer = agent.run(task)

    print(f"\n\n✅ Final Answer：{final_answer}")

if __name__ == "__main__":
    main()
