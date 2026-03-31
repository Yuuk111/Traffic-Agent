# app/agent/react.agent.py
import re
import json
import logging
from openai import AsyncOpenAI

# from app.tools.threat_intel import check_ioc
logger = logging.getLogger(__name__)

class SecurityReActAgent:
    """"基于 ReAct 框架的安全分析 Agent"""
    def __init__(self, api_key: str, base_url: str, model_name: str):
        # 初始化 OpenAI 客户端
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        # 注册工具箱
        self.tools ={

        }

        # System Prompt 
        self.system_prompt = """
你是一个顶级的 Web 安全分析师。
你的任务是分析 HTTP 日志，判断是否存在安全威胁(比如SQLi, XSS, 路径穿越, SSTi)，并提供详细的分析报告。

你目前没有任何工具可以使用，但后续可能扩展。

你【必须】严格遵循以下思考流程:
Thought: 思考这段日志可能存在的安全威胁类型，列出所有可能的威胁，并分析每种威胁的可疑点，以及需要调用什么工具(目前无工具可用，仅需分析)。
Action: 要调用的工具名称 (如果没有工具可用则写 "None")
Action Input: 要传递给工具的输入 (如果没有工具可用则写 "None")

(系统会返回 Observation: 工具的输出结果，但目前没有工具，所以永远是 "None")

当你得出确切结论时，【必须】输出最终的 JSON 判定结果：
Final Answer: {"is_attack": true/false, "confidence": 0-100, "attack_type": "具体类型或 Normal", "reason": "判定理由"}
"""

    async def analyze_log(self, log_data: dict) -> dict:
        """
        ReAct Agent 的核心分析函数
        """

        context = self.system_prompt + f"\n\n 待分析的 HTTP 日志:\n{json.dumps(log_data, indent = 2)}\n"

        # 最大思考轮数
        max_steps = 5
        
        for step in range(max_steps):
            try:
                # 异步请求大模型
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": context}],
                    temperature=0.0
                )

                agent_reply = response.choices[0].message.content.strip()
                logger.info(f"[Agent] Step {step+1} 思考结果:\n{agent_reply}\n")
                context += f"\n{agent_reply}\n"

                # 判断是否得到最终结论 
                if "Final Answer:" in agent_reply:
                    json_str = agent_reply.split("Final Answer:")[1].strip()
                    json_str = re.sub(r'```json|```', '', json_str) # 移除可能的代码块标记
                    result = json.loads(json_str)
                    return result
                
                # 判断是否调用工具 (目前无工具可用，所以暂时不处理)
                # elif "Action:" in agent_reply:
            except Exception as e:
                logger.error(f"[Agent] Agent 分析异常 {e}")
                return {
                    "is_attack": False,
                    "confidence": 0,
                    "reason": f"Agent 内部错误 {str(e)}"}
        
        # 超过最大思考轮数仍未得出结论，返回不确定结果
        return {
            "is_attack": False,
            "confidence": 0,
            "reason": "Agent 无法得出结论，超过最大思考轮数"
        }