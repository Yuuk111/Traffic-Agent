# 构建阶段
FROM python:3.13 AS builder

WORKDIR /build

RUN python -m venv /opt/venv
# 激活虚拟环境
ENV PATH="/opt/venv/bin:$PATH"

# 复制依赖清单
COPY requirements.txt .

# 使用 pip 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 运行阶段
FROM python:3.13-slim

WORKDIR /app

# 设置环境变量，确保 Python 输出不被缓冲
ENV PYTHONUNBUFFERED=1

# 从构建阶段复制虚拟环境
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

COPY . .

EXPOSE 50051

CMD  ["python", "main.py"]