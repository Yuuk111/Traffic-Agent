import asyncio
import logging
from grpc import aio

logger = logging.getLogger(__name__)

# 假设我们有一个 gRPC 定义的服务，生成了相应的 Servicer 类
from .pb2 import insight_pb2, insight_pb2_grpc

class LogAnalyzerServicer(insight_pb2_grpc.LogAnalyserServicer): # 继承 grpc生成的Servicer类
    """
    gRPC Servicer 实现类，负责接收网关发送的日志数据，并将其放入 asyncio.Queue 中供 Agent 消费
    """
    def __init__(self, log_queue: asyncio.Queue):
        # 接收外部传入的 asyncio.Queue 实现生产/消费解耦
        self.log_queue = log_queue

    async def StreamLogs(self, request_iterator, context: aio.ServicerContext):
        """
        处理网关发来的请求
        """
        logger.info("[Agent Receiver] 已与网关建立 Stream 连接")
        processed_count = 0

        try:
            # 异步遍历输入流
            async for log_item in request_iterator:
                # 提取信息，组装字典
                log_data = {
                    "trace_id": log_item.trace_id,
                    "source_ip": log_item.source_ip,
                    "method": log_item.method,
                    "path": log_item.path,
                    "payload": log_item.payload
                }
                # 将日志数据放入队列，供后续分析使用
                await self.log_queue.put(log_data) 
                processed_count += 1
        except asyncio.CancelledError:
            logger.warning("[Agent Receiver] Stream 连接意外断开")
        except Exception as e:
            logger.error(f"[Agent Receiver] 处理日志时发生错误: {e}")
        
        logger.info(f"[Agent Receiver] Stream 连接关闭， 本次共接收 {processed_count} 条日志")

        #返回确认信息给网关
        return insight_pb2.AnalysisSummary(
            processed_count=processed_count,
            status="OK"
        )