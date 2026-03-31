
## gRPC 初始化 ##
+ 安装 gprcio 和 grpcio-tools
```
pip install grpcio grpcio-tools
```
+ 使用 protoc 编译 .proto 文件生成 Python 代码
```
python -m grpc_tools.protoc \
    -I./protos \
    --python_out=./app/grpc_server/pb2 \
    --grpc_python_out=./app/grpc_server/pb2 \
    ./protos/insight.proto
```