# Integration Tests Docker Guide

## 概述

这个脚本用于在Docker环境中运行CronDispatcher的集成测试，类似于单元测试脚本的工作方式。

## 环境要求

- **Python**: 需要Python 3.8+环境，使用`python3`命令
- **Docker**: 用于构建和运行集成测试镜像
- **CCI环境**: 需要有效的CCI账户和凭据

## 脚本功能

`scripts/run_integration_tests_docker.sh` 脚本会：

1. 构建集成测试Docker镜像（基于时间戳的唯一标签）
2. 运行集成测试容器
3. 执行pytest集成测试
4. 显示测试结果和日志
5. 自动清理容器和镜像

## 环境变量要求

在运行脚本前，需要设置以下CCI相关的环境变量：

```bash
export CCI_ACCESS_KEY="your_access_key"
export CCI_SECRET_KEY="your_secret_key"
export CCI_DOMAIN_NAME="your_domain_name"
export CCI_PROJECT_NAME="your_project_name"  # 可选，默认使用region名称
export CCI_REGION="af-south-1"              # 可选，默认af-south-1
export NAMESPACE="your-test-namespace"       # 可选，默认cron-dispatcher-integration-test
```

### NAMESPACE环境变量说明

- **作用**: 指定集成测试运行的Kubernetes namespace
- **默认值**: 如果不设置，会使用 `cron-dispatcher-integration-test`
- **用途**: 
  - 控制测试资源的创建位置
  - 实现测试环境隔离
  - 避免与其他环境的资源冲突

## 使用方法

### 1. 设置环境变量
```bash
# 在运行脚本前设置必要的环境变量
export CCI_ACCESS_KEY="..."
export CCI_SECRET_KEY="..."
export CCI_DOMAIN_NAME="..."
export CCI_REGION="af-south-1"        # 可选
export CCI_PROJECT_NAME="..."         # 可选
export NAMESPACE="your-test-namespace" # 可选，自定义测试namespace
```

### 2. 运行集成测试
```bash
# 添加执行权限（如果需要）
chmod +x scripts/run_integration_tests_docker.sh

# 运行集成测试
./scripts/run_integration_tests_docker.sh
```

## 脚本特性

- **唯一标签生成**: 基于时间戳和短随机值生成镜像标签
  - 格式: `20241201-143022-a3b9c2`
- **环境变量传递**: 自动将CCI配置传递给容器
- **隔离的ccictl配置**: 使用随机后缀避免覆盖现有配置
  - 格式: `cci-cluster-test-a3b9c2`, `cci-user-test-a3b9c2`, `cci-context-test-a3b9c2`

- **自动清理**: 测试完成后自动删除容器、镜像和临时ccictl配置
- **状态反馈**: 详细的执行状态和错误信息

## 输出示例

```
=== Starting Integration Test Docker Image Build ===
Building image: cron-dispatcher-integration-test:20241201-143022-a3b9c2
Image build successful

=== Running Integration Test Container ===
Running container: cron-dispatcher-it-container-a3b9c2
Note: Make sure CCI environment variables are set in your environment

=== Checking Test Results ===
Integration Tests executed successfully

=== Container Logs ===
--- Configuring ccictl Authentication ---
Using test configuration names with suffix: k7m2x8
Setting up ccictl cluster configuration...
Setting up ccictl credentials...
Setting up ccictl context...
ccictl configuration completed successfully!
--- Running Integration Tests ---
Verifying src module accessibility...
Python sys.path:
  /app
  /usr/lib/python36.zip
  /usr/lib64/python3.6
  ...
✓ src.pod_creator imported successfully
tests/integration/test_pod_creation.py::test_create_pod PASSED
--- Cleaning up ccictl Test Configuration ---
Removing temporary ccictl configuration...
ccictl configuration cleanup completed

=== Cleaning Up Resources ===
Container cleaned up

=== Image Cleanup ===
Test image removed successfully

=== Complete ===
Final exit code: 0
```

## 故障排除

### 1. 环境变量未设置
```
Error: Missing required CCI environment variables.
Please set CCI_ACCESS_KEY, CCI_SECRET_KEY, and CCI_DOMAIN_NAME.
```
**解决方案**: 确保设置了所有必要的环境变量

### 2. Docker构建失败
检查：
- Docker是否正在运行
- 网络连接是否正常（需要下载依赖）
- Dockerfile.integration-test是否存在

### 3. 集成测试失败
检查：
- CCI凭据是否正确
- 网络是否可以访问CCI服务
- 测试环境配置是否正确

## 与单元测试的区别

| 特性 | 单元测试 | 集成测试 |
|------|----------|----------|
| 镜像名称 | cron-dispatcher-unit-test | cron-dispatcher-integration-test |
| Dockerfile | Dockerfile.unit-test | Dockerfile.integration-test |
| 容器名前缀 | cron-dispatcher-ut-container | cron-dispatcher-it-container |
| 环境变量 | 无需外部配置 | 需要CCI环境变量 |
| 测试范围 | 单个组件 | 端到端集成 | 