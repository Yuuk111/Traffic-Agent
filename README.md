# 简易安全分析 Agent

这是一个基于 `gRPC + AsyncOpenAI + aiohttp` 的简易 Agent 项目。

项目当前包含两条核心链路：

- `gRPC` 服务监听 `50051`，接收上游网关持续推送的 HTTP 日志
- 前端页面监听 `50052`，实时展示每次调用大模型 API 后的响应内容

前端页面会根据模型 `Final Answer` 里的 `is_attack` 和 `confidence` 做风险区分：

- `is_attack: true` 且 `confidence >= 80`：紧急红色
- `is_attack: true` 且 `confidence >= 50`：高危橙色
- `is_attack: true` 且 `confidence < 50`：可疑棕橙色
- `is_attack: false`：安全绿色
- 暂时未解析出最终结论：灰色“分析中”

## 项目结构

```text
.
├── main.py                         # 项目入口，同时启动 gRPC 服务和前端页面
├── requirements.txt                # Python 依赖
├── Dockerfile                      # 容器构建文件
├── protos/
│   └── insight.proto               # gRPC 协议定义
└── app/
    ├── agent/
    │   └── react_agent.py          # 调用大模型进行日志分析
    ├── grpc_server/
    │   ├── servicer.py             # gRPC 服务实现
    │   └── pb2/                    # protobuf 生成代码
    └── web/
        └── dashboard.py            # 前端页面、历史接口和 SSE 推送
```

## 环境要求

- Python `3.13`
- 一个可用的大模型 API Key

## 安装依赖

```bash
pip install -r requirements.txt
```

## 环境变量

启动前请根据需要配置以下环境变量：

```bash
export OPENAI_API_KEY="你的 API Key"
export OPENAI_API_BASE_URL="https://api.deepseek.com/v1"
export OPENAI_MODEL_NAME="deepseek-chat"
```

说明：

- `OPENAI_API_KEY`：必填，大模型服务密钥
- `OPENAI_API_BASE_URL`：可选，默认是 `https://api.deepseek.com/v1`
- `OPENAI_MODEL_NAME`：可选，默认是 `deepseek-chat`

## 启动项目

```bash
python main.py
```

启动后会同时打开两个服务：

- `gRPC`: `127.0.0.1:50051`
- `Web UI`: `http://127.0.0.1:50052/`

## 前端页面说明

前端页面用于实时展示每次调用大模型 API 后的返回内容。

页面当前包含两部分数据来源：

- 历史记录：通过 `/api/responses` 从内存中读取最近若干条响应
- 实时推送：通过 `/events` 使用 `SSE` 持续接收新响应

注意：

- 当前 SSE 数据和历史记录都保存在内存中
- 服务重启后，页面历史记录会丢失
- 当前实现更适合本地学习和单实例调试

## gRPC protobuf 生成

如果你修改了 `protos/insight.proto`，需要重新生成 Python 代码：

```bash
python -m grpc_tools.protoc \
    -I./protos \
    --python_out=./app/grpc_server/pb2 \
    --grpc_python_out=./app/grpc_server/pb2 \
    ./protos/insight.proto
```

## Docker

项目已提供 `Dockerfile`，并暴露以下端口：

- `50051`：gRPC 服务
- `50052`：前端页面

构建镜像：

```bash
docker build -t simple-agent .
```

运行容器：

```bash
docker run \
  -e OPENAI_API_KEY="你的 API Key" \
  -e OPENAI_API_BASE_URL="https://api.deepseek.com/v1" \
  -e OPENAI_MODEL_NAME="deepseek-chat" \
  -p 50051:50051 \
  -p 50052:50052 \
  simple-agent
```

## 当前实现说明

当前版本是一个偏演示和学习用途的简易实现，特点如下：

- Agent 的分析结果主要依赖大模型返回的 `Final Answer`
- 前端只展示模型响应，不做持久化存储
- 页面通过内存 + SSE 实现实时刷新
- 进程退出时会主动关闭 gRPC、前端服务、后台协程和大模型客户端连接

如果后续要继续扩展，比较自然的方向包括：

- 为响应事件增加 `SQLite` 或 `Redis` 持久化
- 在前端展示原始日志内容和 Trace 维度筛选
- 为 Agent 增加真实的安全工具调用能力
