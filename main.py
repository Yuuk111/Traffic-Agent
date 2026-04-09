import sys
import asyncio
import logging
import os
import contextlib
from grpc import aio
from pathlib import Path

# 引入 Agent
from app.agent.react_agent import SecurityReActAgent
from app.web.dashboard import ResponseEventStore, start_dashboard
# 引入 gRPC Servicer
pb2_path = str(Path(__file__).parent / "app" / "grpc_server" / "pb2")
if pb2_path not in sys.path:
    sys.path.append(pb2_path)
from app.grpc_server.servicer import LogAnalyzerServicer
from app.grpc_server.pb2 import insight_pb2_grpc

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
            logger.info(f"[Main] [开始分析] TraceID: {log_data['trace_id']} | IP: {log_data['source_ip']}")

            analysis_result = await agent.analyze_log(log_data)

            if analysis_result.get("is_attack"):
                logger.warning(f"[Main] 【拦截告警】 发现攻击！ TraceID: {log_data['trace_id']} | 分数: {analysis_result['confidence']} | 类型：{analysis_result['reason']}")
            else:
                logger.info(f"[Main] 【正常请求】 TraceID: {log_data['trace_id']} | 放行")
            
            queue.task_done()
        except Exception as e:
            logger.error(f"[Main] Agent 消费者引擎异常: {e}")

async def serve():
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_API_BASE_URL","https://api.deepseek.com/v1")
    model_name = os.getenv("OPENAI_MODEL_NAME","deepseek-chat")

    # 这个 store 是 Agent 和前端页面之间的“共享桥梁”。
    response_store = ResponseEventStore(max_items=100)
    security_agent = SecurityReActAgent(api_key, base_url, model_name, response_store=response_store)

    log_queue = asyncio.Queue(maxsize=1000)
    consumer_task = asyncio.create_task(agent_consumer_worker(log_queue, security_agent))
    # 在同一个进程中额外启动一个 HTTP 服务，提供页面和 SSE 推送。
    dashboard_runner = await start_dashboard(response_store=response_store, port=50052)
    logger.info("[Main] 前端页面正在 http://0.0.0.0:50052 上监听...")

    grpc_server = aio.server()
    servicer = LogAnalyzerServicer(log_queue=log_queue)
    insight_pb2_grpc.add_LogAnalyserServicer_to_server(servicer, grpc_server)

    grpc_listen_addr = "[::]:50051"
    grpc_server.add_insecure_port(grpc_listen_addr)
    logger.info(f"[Main] gRPC 服务器正在 {grpc_listen_addr} 上监听...")
    
    try:
        await grpc_server.start()
        await grpc_server.wait_for_termination()
    finally:
        # 收到 Ctrl+C 等终止信号后，先立刻停止 gRPC 服务，避免继续接收新请求。
        await grpc_server.stop(grace=0)

        # 主动取消后台消费者协程，让它从 queue.get() 等待中尽快退出。
        consumer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await consumer_task

        # 关闭 aiohttp 前端服务和现有 SSE 连接。
        await dashboard_runner.cleanup()

        # 关闭大模型客户端底层的 HTTP 连接，避免事件循环等待网络资源回收。
        await security_agent.client.close()

if __name__ == "__main__":
    asyncio.run(serve())
