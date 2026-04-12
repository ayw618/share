流程示例（查询重写、意图识别、工具调用、结果返回）：
user: query{你好}
assistant: think{我应该采用哪些工具来回答这个问题，需要输出工具的参数，<action>tool_name(args)</action>}
>>>>action: 进行具体的执行，tool_name(args)
user: observation{工具执行结果}
assistant: think{好的，我已经得到了重写后的查询，用户的意图可能是创建，但不是很清晰，让我调用追问工具进行确认，<action>confirm_tool(args)</action>}
>>>>action: 进行具体的执行，调用无状态工具confirm_tool(args)
user: observation{确认工具执行结果}
assistant: think{好的，我已经完全了解了用户的意图，看来我需要创建完整的代码来满足用户的需求，<action>create_tool(args)</action>}
>>>>action: 连接具体的执行，create_tool(args)
user: observation{创建工具执行结果}
assistant: think{好的，我已经创建了完整的代码来满足用户的需求，接下来可以进行最终的回答了<final_answer>我已经按照你的要求完成了创建代码的任务</final_answer>}






