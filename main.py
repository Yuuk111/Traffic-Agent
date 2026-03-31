import asyncio
import logging
import os
from grpc import aio

# 引入 Agent
from app.agent.react_agent import SecurityReActAgent
from app.grpc_server.servicer import LogAnalyzerServicer

Format = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
logging.basicConfig(level=logging.INFO, format=Format)
logger = logging.getLogger(__name__)

# ======================================================
# 创建 Agent 消费循环
# ======================================================
async def agent_consumer_worker(queue: asyncio.Queue, agent: SecurityReActAgent):
    """
    后台守护协程: 持续从 Queue 中取出日志，交给 Agent 处理
    """
    logger.info("[Main] Agent 消费者引擎启动")
    while True:
        try:
            log_data = await queue.get()
            logger.info(f"[Main] [开始分析] TraceID: {log_data['trace_id']} | IP: {log_data['ip']}")

            analysis_result = await agent.analyze_log(log_data)

            if analysis_result.get("is_attack"):
                logger.warning(f"[Main] 【拦截告警】 发现攻击！ TraceID: {analysis_result['trace_id']} | 类型：{analysis_result['reason']}")
            else:
                logger.info(f"[Main] 【正常请求】 TraceID: {analysis_result['trace_id']} | 放行")
            
            queue.task_done()
        except Exception as e:
            logger.error(f"[Main] Agent 消费者引擎异常: {e}")

async def serve():
    api_key = os.getenv("OPENAI_API_KEY","DEFAULT_KEY")
    base_url = os.getenv("OPENAI_API_BASE_URL","https://api.chatgpt.com/v1")
    model_name = os.getenv("OPENAI_MODEL_NAME","deepseek-chat")

    security_agent = SecurityReActAgent(api_key, base_url, model_name)

    log_queue = asyncio.Queue(maxsize=1000)
    consumer_task = asyncio.create_task(agent_consumer_worker(log_queue, security_agent))

    grpc_server = aio.server()
    servicer = LogAnalyzerServicer(log_queue=log_queue)

    grpc_listen_addr = "[::]:50051"
    grpc_server.add_insecure_port(grpc_listen_addr)
    logger.info(f"[Main] gRPC 服务器正在 {grpc_listen_addr} 上监听...")
    
    await grpc_server.start()
    await grpc_server.wait_for_termination()

if __name__ == "__main__":
    asyncio.run(serve())
