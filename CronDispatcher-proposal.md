# CronDispatcher 方案设计

## 1. 需求概述

CronDispatcher 是一个面向 Kubernetes Namespace 级别的定时任务管理平台，专为华为云 CCI 2.0（Cloud Container Instance）环境设计。它通过声明式的 ConfigMap 驱动配置模式，实现定时任务（Cron Job）的容器化编排和全生命周期管理。

由于 CCI 2.0 当前并未原生支持 Kubernetes 标准的 `CronJob` 资源类型，但用户在数据采集、内容生成等业务场景中存在大量周期性 Pod 拉起的需求。CronDispatcher 通过在 CCI 2.0 Namespace 内部署一个常驻的调度容器，借助系统级 `crond` 守护进程 + Python 调度逻辑 + `ccictl` 命令行工具，向 CCI API 平面下发 Pod 创建/查询/删除指令，从而在 CCI 2.0 上对齐 Kubernetes 原生 CronJob 的核心能力。

主要解决的问题：

- **能力补齐**：在 CCI 2.0 缺少原生 CronJob 资源的前提下，提供等价的定时拉起 Pod 的能力。
- **声明式管理**：通过 ConfigMap 集中维护任务调度计划，避免在每个 Pod 模板中重复定义 schedule。
- **热更新**：调度规则、Pod 模板、GC 策略均支持 ConfigMap 修改后自动生效，无需重启容器。
- **自动垃圾回收**：按照成功/失败粒度对历史 Pod 进行清理，避免 Namespace 配额被耗尽。
- **无人值守**：内建健康检查与进程自愈，crond 与主进程异常退出可自动拉起。

## 2. 需求分析

### 2.1 Goals & Non-Goals

**Goals**

- G1. 在单个 Kubernetes Namespace 内提供基于 cron 表达式的定时任务调度能力，对接 CCI 2.0 的 Pod API。
- G2. 通过 ConfigMap 提供声明式任务定义、Pod 模板与 GC 策略管理，支持任意时刻热加载（30s 内生效）。
- G3. 支持 Unix 5 段 cron 与 Quartz 6 段 cron 两种表达式格式，对 Quartz 自动转换为标准 cron。
- G4. 自动对完成/失败的 Pod 执行垃圾回收，支持全局和按任务粒度的 success/failure 保留数配置。
- G5. 提供面向容器环境的进程管理（不依赖 systemd），支持 crond 与主程序的进程监控与自动重启。
- G6. 提供 Kubernetes Liveness/Readiness 探针所需的健康检查脚本。
- G7. 支持时区配置以适配跨区域的全球部署。
- G8. 支持 CCI 多 Region 部署（默认 `af-south-1`，可配置 `cn-north-4`、`cn-east-3` 等）。

**Non-Goals**

- NG1. **不**实现集群级别（cluster-scope）的定时任务调度，仅服务于本 Namespace。
- NG2. **不**实现任务的并发控制（如 Kubernetes CronJob 的 `concurrencyPolicy`），单实例一律按 cron 时间触发。
- NG3. **不**实现任务执行结果回调、链式编排等工作流能力。
- NG4. **不**实现 Pod 资源模板的可视化编辑能力，运维人员通过 yaml ConfigMap 维护。
- NG5. **不**对 Pod 内业务逻辑（数据处理、内容生成）的正确性负责。
- NG6. **不**支持基于事件（Event-driven）的触发机制，只支持基于时间表达式的触发。
- NG7. **不**实现高可用多副本调度（当前 deployment.yaml 配置 `replicas: 1`），相关多副本协调由后续版本评估。

### 2.2 交付范围

| 交付件           | 内容                                                                     | 说明                                                    |
| ---------------- | ------------------------------------------------------------------------ | ------------------------------------------------------- |
| 调度容器镜像     | `cron-dispatcher:<tag>`                                                  | 基于 CentOS 8 + Python 3 + cronie + ccictl              |
| 部署 YAML        | `config/deployment.yaml`                                                 | CCI 2.0 Deployment 资源定义                             |
| 任务配置模板     | `config/cron-dispatcher-config.yaml`                                     | tasks.yaml + gc-policy.yaml ConfigMap 示例              |
| 凭据 Secret 模板 | `config/cci-credentials-secrets.yaml`                                    | CCI AK/SK/Domain 的 Secret 模板                         |
| Pod 模板示例     | `podTemplates/nginx-test-template.yaml`                                  | 演示如何编写被 CronDispatcher 引用的 Pod 模板 ConfigMap |
| 文档             | `README.md`、`UNIT_TESTS.md`、`INTEGRATION_TESTS.md`、`TESTING_GUIDE.md` | 部署、运维与测试指南                                    |
| 单元测试         | `tests/unit/` 共 10 个测试文件                                           | 覆盖核心模块逻辑                                        |
| 集成测试         | `tests/integration/test_pod_creation.py`                                 | 真实 CCI 环境端到端验证                                 |

### 2.3 友商汇总

CronDispatcher 本质上是对 Kubernetes 原生 `CronJob` 在 CCI 2.0 单租户面上的简化实现，目标是补齐 CCI 2.0 当前缺失的定时任务能力。下表汇总当前主流方案的对比：

| 对比维度                    | Kubernetes 原生 CronJob                                 | 阿里云 ECI（弹性容器实例）                                             | AWS ECS@Fargate                                                                         | 本方案 (CronDispatcher on CCI 2.0)                       |
| --------------------------- | ------------------------------------------------------- | ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| 是否原生提供 CronJob 能力   | 是，标准 `batch/v1.CronJob`                             | 否，ECI 自身不提供 CronJob，需通过 ACK + ECI Pod 调用 K8s 原生 CronJob | 否，Fargate 不提供 CronJob，需借助 EventBridge Scheduler / Step Functions 触发 ECS Task | 否，本方案在 Namespace 内自建 Dispatcher 模拟            |
| 触发方式                    | kube-controller-manager 内置控制器                      | ACK 集群 controller-manager                                            | EventBridge Scheduler 周期 cron 表达式                                                  | 容器内 `crond` + `ccictl apply`                          |
| 调度规则维护                | `spec.schedule` 写在 CronJob 资源中                     | 同 K8s                                                                 | EventBridge Schedule 资源                                                               | ConfigMap `tasks.yaml` 集中维护                          |
| Pod 模板                    | `spec.jobTemplate` 内嵌                                 | 同 K8s                                                                 | Task Definition                                                                         | 独立 ConfigMap (`<name>-template`)                       |
| 并发控制                    | `concurrencyPolicy: Allow/Forbid/Replace`               | 同 K8s                                                                 | 调度器层面控制                                                                          | 不支持，按时间触发即创建                                 |
| 历史保留                    | `successfulJobsHistoryLimit` / `failedJobsHistoryLimit` | 同 K8s                                                                 | EventBridge / CloudWatch 自定义                                                         | `gc-policy.yaml` 全局 + 任务级保留                       |
| 时区支持                    | K8s 1.27+ `spec.timeZone`                               | 同 K8s                                                                 | EventBridge 支持                                                                        | `CRON_TIMEZONE` 环境变量 + 容器内 tzdata                 |
| 多副本 HA                   | controller-manager leader election                      | 同 K8s                                                                 | AWS 服务侧 HA                                                                           | 当前单副本，远期演进多副本 + leader-election（详见 6.4） |
| 部署粒度                    | 集群级                                                  | 集群级                                                                 | 账号级                                                                                  | Namespace 级                                             |
| 是否支持自定义 CRD/Operator | 支持                                                    | 支持                                                                   | N/A                                                                                     | **CCI 2.0 不支持自定义 CRD 与 Operator**                 |

**结论**：本方案受限于 CCI 2.0 当前不支持自定义 CRD/Operator 的事实，无法直接复用社区 CronJob 控制器；通过 ConfigMap + ccictl 的组合在 Namespace 内提供与原生 CronJob 等价的核心能力，作为后续 CCI 2.0 原生支持 CronJob 之前的过渡方案。

### 2.4 需求约束

- **运行环境**：必须运行在华为云 CCI 2.0 之上；不支持自建 Kubernetes 集群。
- **API 通道**：调度容器需要能访问 CCI API（`cci.<region>.myhuaweicloud.com`）和 IAM API（`iam.<region>.myhuaweicloud.com`），通过公网或 VPCEP 任一方式。
- **认证方式**：必须通过 IAM AK/SK + Domain 进行身份认证，不支持 Token、临时凭据等其他方式。
- **依赖工具**：必须以 `/usr/local/bin/ccictl` 形式提供 ccictl 二进制（构建镜像时从 `cci-cn-south-4.obs.cn-south-4.myhuaweicloud.com/ccictl/ccictl` 下载）。
- **特殊 cron 关键字**：不支持 `@yearly`、`@daily`、`@hourly` 等 macro，调度容器内显式拒绝。
- **清理周期约束**：清理周期最小 30s，最大 24h，超出范围会被 clamp。
- **批量删除间隔**：`_delete_pods_batch` 在批次之间硬编码 sleep 60s 防止 API Server 压力。
- **资源限制**：deployment.yaml 中 CPU/Memory 申请均为 0，由 CCI 平台规格 `resource.cci.io/pod-size-specs: 2.00_4.0` 控制。
- **Python 版本**：3.8+。
- **Python 依赖**：`PyYAML>=6.0.1`、`python-crontab>=2.7.1`。

## 3. 解决方案

### 3.1 User Stories

**3.1.1 Story 1：业务侧新增定时任务**

> 作为业务团队成员，我希望在 `business-app-a` Namespace 中每天 12:45 触发一次 `daily-batch-task` Pod，以便获取最新的业务数据。

操作流程：

1. 在 `daily-batch-task-template` ConfigMap 的 `pod.yaml` 字段中维护 Pod 完整定义（容器镜像、命令、资源等）。
2. 在 `cron-dispatcher-config` ConfigMap 的 `tasks.yaml` 中追加一条任务记录：`name`、`schedule: "45 12 * * ? *"`、`podDefinitionConfigmap: daily-batch-task-template`、`state: "on"`。
3. 通过 `ccictl apply` 提交修改，CronDispatcher 在 30s 内检测到 ConfigMap 变更并重建系统 crontab，新任务即时生效。

**3.1.2 Story 2：临时关闭某个任务**

> 作为运维成员，由于上游服务异常，我希望临时停止 `data-sync-task` 的执行，但不希望丢失任务定义。

操作流程：

1. 在 `cron-dispatcher-config` ConfigMap 中将该任务的 `state` 由 `"on"` 改为 `"off"`。
2. CronDispatcher 在 30s 内检测变更并从 crontab 中移除该任务。
3. 排障完成后将 `state` 改回 `"on"`，任务恢复调度，无需重启 Dispatcher Pod。

**3.1.3 Story 3：调整 Pod 历史保留策略**

> 作为运维成员，由于 Namespace Pod 配额接近上限，我希望对失败 Pod 的保留数量从 3 降为 1，并把清理频率从 60m 改为 30m。

操作流程：

1. 修改 `cron-dispatcher-gc-policy` ConfigMap 中的 `global.failure: 1` 与 `cleanupInterval: "30m"`。
2. CronDispatcher 在 30s 内检测变更，重置 cleanup interval 与 last_cleanup_time，并立即触发一次清理。
3. 历史失败 Pod 在保留 1 个最新副本后被批量删除（`gc_batch_size=50`，每批之间 sleep 60s）。

### 3.2 架构影响分析

CronDispatcher 是 CCI 2.0 中独立的 Namespace 级附加组件，核心架构影响如下：

```
┌────────────────────────────── CCI 2.0 Namespace ──────────────────────────────┐
│                                                                                │
│  ┌──────────────────────────┐         ┌────────────────────────────────────┐  │
│  │  cron-dispatcher Pod     │         │  ConfigMaps                        │  │
│  │  (replicas: 1)           │◄────────┤  • cron-dispatcher-config (tasks)  │  │
│  │                          │  watch  │  • cron-dispatcher-gc-policy       │  │
│  │  ┌────────────────────┐  │         │  • <task>-template (pod 定义)      │  │
│  │  │ entrypoint.sh      │  │         └────────────────────────────────────┘  │
│  │  │   ↓                │  │                                                  │
│  │  │ process_manager.sh │  │         ┌────────────────────────────────────┐  │
│  │  │   ├─► crond        │──┼────┐    │  Secret                            │  │
│  │  │   └─► main.py      │  │    │    │  • cci-credentials                 │  │
│  │  └────────────────────┘  │    │    └────────────────────────────────────┘  │
│  │  ┌────────────────────┐  │    │                                              │
│  │  │ ccictl (CLI)       │  │    │    ┌────────────────────────────────────┐  │
│  │  └─────────┬──────────┘  │    │    │  Scheduled Pods                    │  │
│  └────────────┼─────────────┘    │    │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐  │  │
│               │ ccictl apply     │    │  │TaskA│ │TaskB│ │TaskC│ │ ... │  │  │
│               ▼                  │    │  └─────┘ └─────┘ └─────┘ └─────┘  │  │
│  ┌────────────────────────────────────────────────────────────────────────┐   │
│  │   CCI API (cci.<region>.myhuaweicloud.com) + IAM API                   │   │
│  └────────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────────┘
```

- **对 CCI 平台无侵入性**：不需要 CCI 提供新的 CRD 或控制器，只使用现有的 ConfigMap、Secret、Pod、Deployment 资源。
- **对业务 Pod 无侵入性**：业务 Pod 模板维持原样，只需放入 `<name>-template` ConfigMap 的 `data.pod.yaml` 字段。
- **依赖 ccictl**：调度容器内通过 ccictl 与 CCI API 交互，调用方式与人工运维一致。
- **多 Namespace 复用**：每个业务 Namespace 部署一份独立的 cron-dispatcher Deployment（`business-app-a`、`business-app-b` 等示例都在配置中体现）。

### 3.3 功能规格

#### 3.3.1 任务调度

- **调度引擎**：使用容器内的系统 `crond`（cronie 包），由 `python-crontab` 库读写 `/var/spool/cron/root`。
- **触发方式**：crontab 中每条任务调用 `/usr/local/bin/run_cron_job.sh python3 /app/src/pod_creator.py <task_name> <configmap_name>`。
- **环境变量传递**：`process_manager.sh` 在启动时把 `NAMESPACE`、`CCI*`、`KUBERNETES*` 等环境变量写入 `/etc/cron.d/cron-env`，再由 `run_cron_job.sh` 在执行前 `source` 加载，绕开 cron 默认环境受限的限制。
- **cron 表达式校验**：`validate_cron_expression` 拒绝特殊字符串（`@yearly`/`@daily` 等）；6 段 Quartz 自动转换为 5 段 Unix 格式（忽略 seconds 字段）。

#### 3.3.2 任务定义

`tasks.yaml` 字段说明：

| 字段                     | 类型        | 必填 | 说明                                      |
| ------------------------ | ----------- | ---- | ----------------------------------------- |
| `name`                   | string      | 是   | 任务唯一标识，作为 Pod 名前缀和 label 值  |
| `schedule`               | string      | 是   | Cron 表达式，支持 5 段 Unix / 6 段 Quartz |
| `podDefinitionConfigmap` | string      | 是   | 引用的 Pod 定义 ConfigMap 名称            |
| `state`                  | string/bool | 否   | `on`（默认）/`off`；支持布尔自动转换      |

#### 3.3.3 Pod 创建

`pod_creator.py` 流程：

1. 通过 `ccictl get configmap <configmap_name> -o yaml` 拉取 Pod 模板。
2. 读取 `data.pod.yaml` 字段并 YAML parse。
3. 生成 9 位随机 UUID（`uuid4().replace('-','')[:9]`），生成 Pod 名 `<task_name>-<uuid>`。
4. 注入 `metadata.name`、`metadata.namespace`、标准 labels 与 annotations。
5. 写入 `/tmp/pod-<uuid>.yaml`，调用 `ccictl apply -f` 创建 Pod。
6. 创建结束后清理临时文件。

强制注入的 labels：

```yaml
app.kubernetes.io/name: <task_name>
app.kubernetes.io/managed-by: cron-dispatcher
cron-dispatcher.io/task-name: <task_name>
cron-dispatcher.io/instance: <pod_name>
```

强制注入的 annotations：

```yaml
cron-dispatcher.io/created-by: cron-dispatcher
cron-dispatcher.io/creation-time: <UTC ISO8601>
cron-dispatcher.io/source-configmap: <configmap_name>
```

#### 3.3.4 配置热更新

`main.py` 主循环每 30s 检查一次：

- `watch_tasks_config_change`：通过 `os.path.getmtime` 对比 mtime，发生变化则重新加载 `tasks.yaml` 并重建 crontab。
- `watch_gc_policy_change`：检测 GC 策略文件 mtime 变化，重置 `cleanup_interval_seconds` 与 `last_cleanup_time`。

#### 3.3.5 垃圾回收

`pod_cleaner.py` 流程：

1. 通过 `ccictl get pods -l app.kubernetes.io/managed-by=cron-dispatcher -o yaml` 拉取所有受管 Pod。
2. 按 `cron-dispatcher.io/task-name` 分组，并按 `status.phase` 区分 `Succeeded` / `Failed` 桶。
3. 按 `creationTimestamp` 倒序保留 N 条，多余的进入删除队列。
4. 优先匹配任务级策略（`tasks[].taskSelector.cron-dispatcher.io/task-name == <task>`），未命中则 fallback 到全局 `global.success/failure`。
5. 按 `gc_batch_size`（默认 50）分批，每批之间 sleep 60s。
6. `gc_dry_run=true` 时只打印 `[DRY RUN]` 日志，不实际删除。

#### 3.3.6 配置项总览

环境变量：

| 变量               | 必填 | 默认                                                    | 说明                                 |
| ------------------ | ---- | ------------------------------------------------------- | ------------------------------------ |
| `NAMESPACE`        | 否   | `default`（实际由 `fieldRef: metadata.namespace` 注入） | Kubernetes Namespace                 |
| `CRON_TIMEZONE`    | 否   | `UTC`                                                   | crond 时区，写入 `/etc/localtime`    |
| `CCI_REGION`       | 否   | `af-south-1`                                            | CCI Region，决定 cluster server 地址 |
| `GC_DRY_RUN`       | 否   | `false`                                                 | 是否启用 GC 干跑模式                 |
| `GC_BATCH_SIZE`    | 否   | `50`                                                    | 每批删除 Pod 数量                    |
| `CCI_ACCESS_KEY`   | 是   | -                                                       | IAM AK                               |
| `CCI_SECRET_KEY`   | 是   | -                                                       | IAM SK                               |
| `CCI_DOMAIN_NAME`  | 是   | -                                                       | IAM Domain                           |
| `CCI_PROJECT_NAME` | 否   | 与 `CCI_REGION` 相同                                    | IAM Project Name                     |

ConfigMap 挂载点：

- `/etc/cron-dispatcher-config/tasks.yaml`
- `/etc/cron-dispatcher-gc-policy/gc-policy.yaml`

### 3.4 风险及设计约束

| 风险                             | 描述                                                                | 缓解措施                                                                      |
| -------------------------------- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| R1. 单副本无 HA                  | `replicas: 1`，Pod 重建期间错过的 cron 触发不会补偿                 | CCI 平台保证 Pod 自动拉起；任务设计应幂等；后续评估多副本 leader-election     |
| R2. ccictl 阻塞                  | ccictl 调用 IAM/CCI API 可能因网络抖动而长时间未返回                | `execute_command_with_retry` 强制 timeout（30~60s） + 最多 3 次重试           |
| R3. 任务时钟漂移                 | 容器宿主机时钟漂移会影响 cron 触发时刻                              | 由 CCI 平台保障 NTP 同步；不在 Dispatcher 层处理                              |
| R4. ConfigMap mtime 不变更       | k8s 通过 inotify 投影时 mtime 可能不刷新                            | `os.path.getmtime` + 30s 主动轮询；`subPath` 挂载需谨慎                       |
| R5. cron 5 段 vs Quartz 6 段歧义 | Quartz 第三、五段使用 `?` 为占位符                                  | `_convert_quartz_to_cron` 直接丢弃 seconds 字段；运维注意 schedule 写法一致性 |
| R6. AK/SK 泄露                   | Secret 内明文 base64 易被读取                                       | RBAC 控制 Secret 访问；建议生产使用外部密钥管理；定期轮换                     |
| R7. Pod 模板变更未触发任务       | 修改 `<task>-template` ConfigMap 不会影响 crontab，仅影响下一次拉起 | Pod 创建时实时 `ccictl get configmap`，自然生效；无需热加载                   |
| R8. GC 风暴                      | 大批量历史 Pod 同时删除冲击 CCI API                                 | `gc_batch_size` 限流 + 批间 sleep 60s + 删除 timeout 30s + 重试 2 次          |

### 3.5 可选的替代方案

| 方案                           | 优势                     | 劣势                                                               | 决策                         |
| ------------------------------ | ------------------------ | ------------------------------------------------------------------ | ---------------------------- |
| Kubernetes 原生 `CronJob`      | 无需自建组件，社区成熟   | CCI 2.0 暂未提供 CronJob 资源类型                                  | 不可行，故走 Dispatcher 方案 |
| 调用方业务自带 cron            | 实现简单                 | 每个业务镜像内置 cron，运维分散；状态难统一管理                    | 不采纳                       |
| 使用 Argo Workflows            | 工作流能力强，社区活跃   | 引入额外重型组件，部署复杂；CCI 2.0 兼容性需评估                   | 不采纳，超出当前 Goal        |
| 基于 Kubernetes Operator + CRD | 声明式更彻底，可观测性好 | **经 CCI 平台团队确认，CCI 2.0 不支持自定义 CRD 与 Operator 部署** | **不可行**，被否决           |

**最终选型说明**：

由于 CCI 2.0 不支持自定义 CRD 与 Operator，本方案定位为对 Kubernetes 原生 `CronJob` 在单租户面（Namespace 内）的简化实现，具体差异如下：

- **裁剪项**：去掉 Job 中间对象，直接在 Pod 维度运转；不实现 `concurrencyPolicy`；不实现 `suspend` 字段（用 `state: on/off` 替代）。
- **保留项**：cron 表达式语法、Pod 模板、历史保留计数、时区配置、Pod 标签管理等核心能力对齐原生 CronJob。
- **演进方向**：待 CCI 2.0 后续版本原生支持 `batch/v1.CronJob` 后，可平滑迁移：本方案 `tasks.yaml` 可一一映射到原生 CronJob 资源。

## 4. 详细设计

### 4.1 模块X详细设计

#### 4.1.1 主调度模块（src/main.py）

类 `CronDispatcher` 关键属性与方法：

| 项                               | 说明                                                                    |
| -------------------------------- | ----------------------------------------------------------------------- |
| `MIN_INTERVAL_SECONDS=30`        | GC 清理周期下界                                                         |
| `MAX_INTERVAL_SECONDS=86400`     | GC 清理周期上界                                                         |
| `DEFAULT_INTERVAL_SECONDS=300`   | 解析失败时的默认清理周期                                                |
| `cron = CronTab(user='root')`    | python-crontab 操作 root 用户 crontab                                   |
| `_load_and_apply_config()`       | 启动时读取 tasks.yaml 与 gc-policy.yaml                                 |
| `update_crontab(tasks)`          | 移除带 `cron-dispatcher` 注释的旧任务，重新写入                         |
| `_process_task(task)`            | 校验 schedule、ConfigMap 存在性、state 字段，构造 cron 命令             |
| `validate_cron_expression(expr)` | 拒绝 `@daily` 等特殊词 + 借助 `python-crontab.setall` 校验              |
| `_convert_quartz_to_cron(expr)`  | 6 段 Quartz → 5 段 Unix（丢弃 seconds 字段）                            |
| `validate_configmap_exists(cm)`  | 调用 `ccictl get configmap` 验证模板存在                                |
| `_parse_interval_to_seconds(s)`  | 支持 `30s`、`5m`、`1h`、`1d`、纯数字（按 s）；越界 clamp                |
| `_run_cleanup()`                 | 当 `time.time() - last_cleanup_time >= cleanup_interval_seconds` 时触发 |
| `run()`                          | 30s 周期循环：检查配置变更 → 处理 GC                                    |

#### 4.1.2 Pod 创建模块（src/pod_creator.py）

- 入口：`pod_creator.py <task_name> <configmap_name>`，由 cron 触发。
- 单次执行，独立进程，无需常驻。
- 失败时 `sys.exit(1)` 由 cron/syslog 记录。

#### 4.1.3 Pod 清理模块（src/pod_cleaner.py）

- 由主进程调用，在主循环中周期性触发。
- 关键方法：`cleanup_pods` → `_group_pods_by_task` → `_cleanup_task_pods` → `_get_task_retention_policy` → `_delete_pods_batch`。

#### 4.1.4 CCI 认证模块（src/cci_auth_manager.py）

- 启动时调用 `load_credentials_from_env` 读取 4 个环境变量。
- `configure_ccictl` 顺序执行 4 条 ccictl 子命令：`set-cluster` → `set-credentials`（IAM auth-provider）→ `set-context` → `use-context`。
- ccictl 配置全部以非 shell 方式 `subprocess.run(shell=False)` 执行，避免参数注入。

#### 4.1.5 工具模块（src/utils.py）

| 函数                         | 说明                                              |
| ---------------------------- | ------------------------------------------------- |
| `execute_command_with_retry` | 通用 subprocess 包装：timeout、retry、stderr 捕获 |
| `safe_yaml_load`             | 仅接受 dict/list 类型 YAML，避免 string injection |
| `safe_yaml_dump`             | 自动 `os.makedirs` 父目录，写 YAML                |
| `cleanup_temp_file`          | 安全删除 `/tmp/pod-*.yaml`                        |
| `get_ccictl_command`         | 拼接 `/usr/local/bin/ccictl <cmd> -n <ns>`        |

#### 4.1.6 日志模块（src/logger_config.py）

- `setup_logger(name, log_file)` 同时挂载 StreamHandler（stdout）+ RotatingFileHandler（10MB × 5 backup）。
- 日志格式：`%(asctime)s - %(name)s - %(levelname)s - %(message)s`。

#### 4.1.7 容器进程管理（scripts/process_manager.sh）

- `start_crond`：写 `/etc/cron.d/cron-env` + 创建 `/usr/local/bin/run_cron_job.sh` 包装脚本 → `crond -n -s -m off &`。
- `start_main_app`：`python3 /app/src/main.py &`，记录 PID 到 `/var/run/cron-dispatcher.pid`。
- `monitor_processes`：每 30s 检查 PID，异常退出自动重启。
- `cleanup`（trap SIGTERM/SIGINT）：先杀主进程，再杀 crond，最大 10s 优雅时间。

#### 4.1.8 健康检查（scripts/health_check.sh）

| 模式          | 用途               | 检查项                                       |
| ------------- | ------------------ | -------------------------------------------- |
| `--liveness`  | K8s liveness 探针  | crond + main.py 进程是否在运行               |
| `--readiness` | K8s readiness 探针 | crond + main.py + 关键目录（带 10 分钟缓存） |
| `--verbose`   | 人工排障           | 全量打印                                     |

### 4.2 UI详细设计

不涉及。CronDispatcher 不提供前端 UI，所有交互通过 ccictl 与 ConfigMap/Secret 完成。

### 4.3 API设计

#### 4.3.1 对外API变更（服务自身API）

不涉及。CronDispatcher 不对外暴露 HTTP/gRPC API，使用方通过 ConfigMap 声明任务。

#### 4.3.2 周边API调用变更

CronDispatcher 调用以下 CCI / IAM API（通过 `ccictl` 命令行间接调用）：

| 操作           | 命令                                                                              | 用途                                |
| -------------- | --------------------------------------------------------------------------------- | ----------------------------------- |
| 获取 ConfigMap | `ccictl get configmap <name> -o yaml -n <ns>`                                     | 校验 ConfigMap 存在 + 拉取 Pod 模板 |
| 创建 Pod       | `ccictl apply -f /tmp/pod-<uuid>.yaml`                                            | 拉起任务 Pod                        |
| 列出 Pod       | `ccictl get pods -l app.kubernetes.io/managed-by=cron-dispatcher -o yaml -n <ns>` | GC 数据来源                         |
| 删除 Pod       | `ccictl delete pod <pod_name> -n <ns>`                                            | GC 删除                             |
| IAM 认证       | `ccictl config set-credentials --auth-provider=iam`                               | 启动期一次性配置                    |

底层 HTTP API 终端：

- `https://cci.<region>.myhuaweicloud.com`
- `https://iam.<region>.myhuaweicloud.com`

VPC 部署时通过 VPCEP + Private Zone CNAME 解析（详见 README.md）。

### 4.4 数据库设计

#### 4.4.1 数据建模

不涉及。CronDispatcher 不使用任何数据库，所有运行时状态以以下形式持久化：

- ConfigMap（Kubernetes etcd）：任务定义、GC 策略、Pod 模板。
- Secret（Kubernetes etcd）：CCI 凭据。
- Pod 资源（Kubernetes etcd）：调度产生的实际任务实例。
- 容器内文件：`/var/spool/cron/root`（crontab）、`/var/log/cron-dispatcher/*.log`、`/etc/cron.d/cron-env`、`/var/run/*.pid`。这些文件均不要求持久化，重建即可恢复。

#### 4.4.2 数据字典与升级方案

不涉及（无数据库 schema）。ConfigMap schema 升级策略：

| 字段                        | 兼容性          | 说明                                         |
| --------------------------- | --------------- | -------------------------------------------- |
| `tasks[].state`             | 向前兼容 bool   | 历史 yaml 写 `state: true` 仍可被识别为 `on` |
| `tasks[].schedule`          | 同时支持 5/6 段 | 6 段自动剥离 seconds，不破坏现有 5 段配置    |
| `gc-policy.cleanupInterval` | 字符串 + 数字   | 兼容 `60`（秒）和 `60m`                      |

### 4.5 可观测性设计

#### 4.5.1 指标设计

**当前版本**：未暴露 Prometheus / OpenTelemetry 指标，可观测性主要依赖日志。

**规划指标**（**优先级：低，作为后续迭代实现**）：

| 指标名                                         | 类型      | 标签                                                        | 含义                                                  |
| ---------------------------------------------- | --------- | ----------------------------------------------------------- | ----------------------------------------------------- |
| `cron_dispatcher_task_trigger_total`           | Counter   | `task_name`, `result=success/fail`                          | 任务触发次数（以 cron 触发计数，不包含 Pod 创建成败） |
| `cron_dispatcher_pod_create_total`             | Counter   | `task_name`, `result=success/fail`                          | Pod 创建结果计数                                      |
| `cron_dispatcher_pod_create_duration_seconds`  | Histogram | `task_name`                                                 | 单次 Pod 创建耗时分布                                 |
| `cron_dispatcher_gc_deleted_total`             | Counter   | `task_name`, `phase=Succeeded/Failed`, `dry_run=true/false` | GC 删除 Pod 计数                                      |
| `cron_dispatcher_gc_run_duration_seconds`      | Histogram | -                                                           | 单次 GC 流程耗时                                      |
| `cron_dispatcher_ccictl_call_duration_seconds` | Histogram | `verb=get/apply/delete`, `result=success/fail`              | ccictl 调用耗时分布                                   |
| `cron_dispatcher_config_reload_total`          | Counter   | `source=tasks/gc-policy`, `result=success/fail`             | 热加载次数                                            |
| `cron_dispatcher_active_tasks`                 | Gauge     | -                                                           | 当前 crontab 中已激活任务数                           |

**暴露方案**：

- 主进程内置 HTTP `/metrics` 端点（建议端口 9100），由 Prometheus 抓取。
- 同时关键事件落 LTS 文本日志，便于在没有 Prometheus 的环境下也可基于日志做指标统计。

**触发计数补充**：cron 触发由系统 `crond` 完成，主进程感知不到具体触发时机；指标埋点需在 `pod_creator.py` 进程入口注入，并通过共享文件 / Pushgateway 等方式上报。该改造在迭代中评估。

#### 4.5.2 日志和事件

日志类别：

| 文件                                       | 来源                   | 内容                                           |
| ------------------------------------------ | ---------------------- | ---------------------------------------------- |
| `/var/log/cron-dispatcher/dispatcher.log`  | main.py CronDispatcher | 启动信息、配置加载、crontab 重建、cleanup 调度 |
| `/var/log/cron-dispatcher/pod-creator.log` | pod_creator.py         | 每次任务触发的 Pod 创建过程与结果              |
| `/var/log/cron-dispatcher/pod-cleaner.log` | pod_cleaner.py         | GC 流程、保留策略匹配、批量删除结果            |
| `/var/log/cron-dispatcher/cci-auth.log`    | cci_auth_manager.py    | ccictl 配置过程                                |
| `/var/log/cron-dispatcher/utils.log`       | utils.py               | 子进程调用与重试                               |
| stdout                                     | 所有模块               | 同步打印，便于 `kubectl/ccictl logs` 查看      |
| `/var/log/cron.log`                        | crond 自身             | cron 任务触发记录                              |

日志通过 `logconfigs.logging.openvessel.io` annotation 集成到 LTS（Log Tank Service）：

```yaml
logconfigs.logging.openvessel.io: '{"default-config":{"container_files":{"container-0":"stdout.log;/var/log/cron-dispatcher/*.log"}, ...}}'
logconf.k8s.io/fluent-bit-log-type: lts
```

事件设计：当前不发送 Kubernetes Event（`v1.Event`），所有信息以日志形式输出。

### 4.6 配置项和特性开关设计

CronDispatcher 不引入运行时灰度（无 A/B 开关），所有配置经由两类来源生效：

- **环境变量**：写在 `deployment.yaml` 的 `env` / `envFrom`，需要重启 Dispatcher Pod 才能生效；用于环境维度（命名空间、Region、时区、AK/SK）和稳定性兜底（GC dry-run、批量大小）。
- **ConfigMap 字段**：`cron-dispatcher-config`（任务定义）与 `cron-dispatcher-gc-policy`（清理策略），通过 `ccictl apply` 修改后由主循环在 30s 内热加载，**无需重启 Pod**。

下表「影响行为（含历史行为）」一栏：若该项首次引入即为当前形态，标注 **首版即此**；若曾发生过形态变更（来自仓库 git 历史或代码注释），简述前后差异并标注关联 commit。「同步清理的组件历史配置」描述变更生效后租户需要手动收敛的"残留物"，避免变更后系统中存在不一致状态。

| 开关 / 配置项 | 影响行为（含历史行为） | 默认值 | 开启行为 | 关闭行为 | 配置方式 | 周边依赖 | 推荐配置 | 同步清理的组件历史配置 |
|---------------|------------------------|--------|----------|----------|----------|----------|----------|------------------------|
| `GC_DRY_RUN` | 控制 GC 是否真实删除 Pod。**首版即此**：作为上线前预演开关引入。 | `false` | `true`：仅打印 `[DRY RUN] Would delete pod <name>` 日志，不调用 `ccictl delete` | `false`：调用 `ccictl delete pod`，物理删除符合策略的 Pod | `deployment.yaml` 的 `env`，重启 Pod 生效 | `pod_cleaner.py`、ccictl `delete pod` 权限 | 生产稳态 `false`；变更 `gc-policy` 前临时开 `true` 走完一轮验证再回切 | 验证完成回切后，`/var/log/cron-dispatcher/main.log` 中残留的 `[DRY RUN]` 日志可保留观察 1 个 GC 周期后清理 |
| `GC_BATCH_SIZE` | 单次 GC 调用 ccictl 的批量删除上限，节流瞬时 API 压力。**首版即此**：批间 `sleep 60s` 是配套常量，未做配置化。 | `50` | 任意正整数：按该数量一批删除，批与批之间固定 `sleep 60s` | `0` 或负数 / 非数字：`int()` 解析失败导致 Pod CrashLoop（无兜底逻辑） | `deployment.yaml` 的 `env`，重启 Pod 生效 | `pod_cleaner.py` 批删循环 | 单 Namespace Pod 总量 < 1000 时保持 `50`；超过 1000 调小到 `30` 并将 `cleanupInterval` 同步缩短 | 无 |
| `tasks[].state` | 任务级软开关（`on/off`）。**历史行为**：早期解析存在大小写敏感缺陷（commit `8ca736e`: "make sure the cron task switch can be parsed correctly"），现版本统一小写比较。 | `on` | `on`：写入系统 crontab，按 `schedule` 周期触发 | `off`：从 crontab 中移除，任务定义保留在 ConfigMap，可随时切回 | ConfigMap `cron-dispatcher-config.tasks.yaml`，`ccictl apply` 后 30s 内生效 | 关联的 `<task>-template` ConfigMap 必须存在 | 故障期间临时停用使用 `off`；永久下线再删除整条任务并联动删除 template ConfigMap | `state=off` 仅停止新触发，已存在的 Pod 不会自动清理；如需立即回收：`ccictl delete pods -l cron-dispatcher.io/task-name=<task>` |
| `tasks[].schedule` | 任务的 cron 表达式。**历史行为**：早期使用 `croniter` 库（commit `869580c`: "replace croniter lib"），现切换为 `python-crontab` 与系统 cronie 对齐，避免库与 crond 行为不一致。 | 无（必填） | 合法 5/6 段 cron：按规则触发；6 段 Quartz 中的秒位由 cronie 忽略 | 非法 cron：当条任务跳过，主循环日志记录解析错误，其它任务不受影响 | ConfigMap `cron-dispatcher-config.tasks.yaml`，热加载 30s 内生效 | 系统 `crond`（cronie 包） | 写入注释标注语义与时区；改动前用 `crontab.guru` 校验 | 修改 schedule 后旧周期产生的 Pod 由 GC 自然清理 |
| `tasks[].podDefinitionConfigmap` | 指向业务 Pod 模板 ConfigMap 名称，其 `data.pod.yaml` 字段保存完整 Pod 定义。**首版即此**。 | 无（必填） | 引用名存在：每次触发先 `ccictl get configmap` 拉取模板，注入 UUID 与标签后 `apply` | 引用名不存在：触发失败，记录 ERROR，跳过本次（不影响其它任务） | ConfigMap `cron-dispatcher-config.tasks.yaml`，热加载 30s 内生效 | 对应 `<name>-template` ConfigMap | 命名规范 `<task>-template`，与任务名一一对应 | 删除任务后必须同步删除 `<name>-template` ConfigMap，否则成为孤儿配置 |
| `gc-policy.cleanupInterval` | GC 周期。**首版即此**：通过 ConfigMap 暴露为可热更新字段，代码侧保留 5m 兜底。 | `60m`（YAML）；缺省时代码兜底 `5m` | 合法时间字符串（`30m`、`1h`、`6h`）：按该周期触发 | 非法格式：日志告警并按代码常量 `5m` 兜底，不影响主循环 | ConfigMap `cron-dispatcher-gc-policy.gc-policy.yaml`，30s 内热加载并立即触发一次 GC | `pod_cleaner.py` | Pod 量 < 200 保持 `60m`；Pod 量大或保留数低，调到 `30m`；不要短于 `5m`（小于代码强制下限） | 修改后无需手动清理；下次 GC 即按新周期执行 |
| `gc-policy.global.success` / `gc-policy.global.failure` | 全局保留数：成功 / 失败 Pod 各自保留最近 N 个。**首版即此**：双字段拆分自服务首版。 | `3` / `3` | 正整数 N：按 `creationTimestamp` 倒序保留 N 个，超出删除 | `0`：清空所有该状态 Pod；`-1` 或非数字：`int()` 解析异常被主循环捕获，按上次有效策略继续 | ConfigMap `cron-dispatcher-gc-policy.yaml` | `pod_cleaner.py` 分组逻辑 | 失败保留 ≥ 1 以便排障；成功保留按 Namespace 配额裁剪 | 下次 GC 自然回收，无需手动清理 |
| `gc-policy.tasks[].success` / `gc-policy.tasks[].failure` | 任务级保留数，覆盖 `global`。**首版即此**。 | 不配置（落入 `global`） | 显式整数：仅该任务采用此值 | 不配置或字段缺失：使用 `global` 默认 | ConfigMap `gc-policy.yaml` 的 `tasks` 数组，与 `tasks[].name` 严格匹配 | `pod_cleaner.py`、`tasks[].name` 命名一致性 | 仅对关键 / 长任务单独配置；非关键任务保持全局即可 | 删除任务级配置后由 global 接管，下次 GC 自动调整 |
| `gc-policy.labelSelector.matchLabels` | GC 扫描 Pod 时使用的 label selector，决定哪些 Pod 纳入清理范围。**首版即此**。 | `app.kubernetes.io/managed-by: cron-dispatcher` | 任意 label：仅匹配的 Pod 纳入 GC | 留空：默认全 Namespace 扫描，**不推荐**（会回收非 Dispatcher 创建的 Pod） | ConfigMap `cron-dispatcher-gc-policy.yaml` | `pod_creator.py` 必须保证创建 Pod 时打齐这些 label | 与 `pod_creator.py` 注入 label 严格一致；新增 label 维度需先升级 `pod_creator.py` 再改 selector | 修改 selector 后旧 label 的 Pod 不再被回收，需手动清理：`ccictl delete pods -l <旧 label>` |
| `NAMESPACE` | Dispatcher 工作的命名空间。**首版即此**：通过 Downward API 注入避免人工配错。 | 实际 Pod 所在 namespace（Downward API），代码兜底 `default` | Downward API：自动注入运行时 namespace | 显式覆盖：固定字符串值，会与 Pod 所在 namespace 解耦，仅用于本地调试 | `deployment.yaml` 的 `env` + `valueFrom.fieldRef: metadata.namespace` | k8s Downward API | 始终使用 Downward API，避免误配置导致跨 Namespace 操作 | 无 |
| `CRON_TIMEZONE` | 系统 crond 时区，影响所有 cron 表达式触发时间。**历史行为**：早期 cron 子进程未继承主进程环境变量，导致 `TZ` 缺失触发偏移（commit `5839bb5`: "Inherit relevant environment variables from the main process environment to the Cron environment"），现已通过 `process_manager.sh` 注入。 | `UTC` | IANA 时区字符串（`Asia/Shanghai`、`Asia/Singapore` 等） | 为空或非法：crond 回退 UTC | `deployment.yaml` 的 `env`，重启 Pod 生效 | 镜像内 tzdata（CentOS 8 默认包含）；`process_manager.sh` 的环境变量注入逻辑 | 多区域同模板部署：统一 `UTC`，业务侧自行换算；单区域：本地时区 | 切换时区后 cron 触发时刻语义变化，建议在切换窗口先批量 `state=off`，校验后再 `on` |
| `CCI_REGION` | ccictl 调用的 CCI API 域名拼接。**首版即此**。 | `af-south-1` | 合法 region 名（`cn-north-4`、`cn-south-4` 等） | 非法 region：ccictl 调用 DNS 失败，所有触发 / GC 失败但主进程不退出（liveness 探针可能告警） | `deployment.yaml` 的 `env`，重启生效 | DNS 可达 + VPCEP 配置（详见 README 网络章节） | 与租户实际 CCI 实例 region 严格一致；切换前先在新 region 创建 VPCEP 端点 | 切 region 后旧 region Pod 不再受管，需在旧 region 手动清理或停服迁移 |
| `CCI_ACCESS_KEY` / `CCI_SECRET_KEY` / `CCI_DOMAIN_NAME` / `CCI_PROJECT_NAME` | IAM AK/SK 认证四元组。**历史行为**：早期 ccictl 配置存在认证失败问题（commit `f3a9bb7`: "fix ccictl auth error"），现由 `cci_auth_manager.py` 在容器启动时统一调用 `ccictl config set-credentials` 注入。 | 无（必填） | 全部正确：启动期配置 ccictl auth-provider；运行期所有 ccictl 命令携带 token | 任一缺失或错误：启动期日志 ERROR，liveness 探针失败 → Pod CrashLoop | `deployment.yaml` 的 `envFrom: secretRef: cci-credentials`（base64 编码） | IAM 用户需具备目标 Namespace 的 Pod / ConfigMap CRUD 权限 | 单 Dispatcher 一套独立 AK/SK；轮换时滚动更新 Secret 后 `ccictl rollout restart deployment cron-dispatcher` | 轮换后立即删除 Secret 旧版本（`ccictl delete secret cci-credentials-<old-version>`），避免残留泄露面 |

**热更新与重启对照**

| 类别 | 配置项 | 生效方式 | 时延 |
|------|--------|----------|------|
| ConfigMap 热更新 | `tasks[]` 全部字段、`gc-policy` 全部字段 | `ccictl apply` 后由主循环检测 | ≤ 30s |
| 必须重启 Pod | 所有环境变量（`GC_DRY_RUN`、`GC_BATCH_SIZE`、`NAMESPACE`、`CRON_TIMEZONE`、`CCI_REGION`、`CCI_*` 凭证） | `ccictl rollout restart deployment cron-dispatcher` | 取决于 Pod 重启耗时（约 10–30s） |

**灰度策略**：CronDispatcher 一律全量切换；如确需灰度，按 Namespace 维度部署独立 Dispatcher 实例分批升级，避免在单实例内引入运行时开关。

## 5. 性能

性能目标与基线：

- **任务触发精度**：受系统 crond 限制，分辨率为分钟级；当 Pod 数量 ≤100 时单次任务触发开销 < 5s（拉取 ConfigMap + apply）。
- **配置加载**：`tasks.yaml` 解析时间随任务数线性增长，实测 50 任务级别 < 100ms。
- **GC 周期**：单次 GC 调用 `ccictl get pods` 一次，按任务分组在内存中处理；100 个 Pod 内 < 2s。
- **批删流控**：`gc_batch_size=50` + 批间 sleep 60s，意味着 1000 个 Pod 删除完毕需要 ≥(1000/50-1)\*60 = 1140s（约 19 分钟）。
- **配置检查频率**：30s 间隔，CPU 占用可忽略。
- **资源规格**：deployment.yaml 使用 `resource.cci.io/pod-size-specs: 2.00_4.0`（2 vCPU / 4GiB 内存），常态空闲 CPU < 5%、内存占用 < 200MiB。

## 6. 可靠性

### 6.1 故障管理

| 故障            | 检测                                     | 处理                                                |
| --------------- | ---------------------------------------- | --------------------------------------------------- |
| crond 进程退出  | `process_manager.sh` 30s 检查 PID        | 自动 `start_crond` 重启                             |
| main.py 退出    | `process_manager.sh` 30s 检查 PID        | 自动 `start_main_app` 重启                          |
| ccictl 调用失败 | `execute_command_with_retry` 返回 False  | 最多重试 3 次，仍失败则记录错误日志，不影响后续触发 |
| ConfigMap 缺失  | `validate_configmap_exists`              | 跳过该任务，告警日志                                |
| YAML 解析失败   | `safe_yaml_load` 返回 None               | 不更新 crontab，保持原状                            |
| cron 表达式非法 | `validate_cron_expression`               | 跳过该任务                                          |
| Pod 创建失败    | `ccictl apply` 非零退出                  | 最多重试 3 次，记录错误并清理临时文件               |
| 容器整体崩溃    | K8s liveness probe（30s 周期，3 次失败） | CCI 重启 Pod；控制循环依赖 Deployment `Always`      |

### 6.2 系统防呆

- **特殊关键字过滤**：`@daily/@hourly` 等 macro 在 `validate_cron_expression` 中显式拒绝，避免被 cronie 行为差异坑到。
- **Quartz 转换**：6 段表达式自动转换为 5 段，避免运维误用。
- **state 字段类型容错**：自动支持布尔 `True/False` → `on/off` 字符串。
- **GC 周期 clamp**：`<30s` 钳到 30s，`>24h` 钳到 24h，避免误配置导致清理失控。
- **Dry Run 模式**：通过 `GC_DRY_RUN=true` 验证策略后再开启实际删除。
- **ConfigMap 校验前置**：任务 schedule 写入 crontab 前必须先确认 `podDefinitionConfigmap` 存在。

### 6.3 过载控制

- GC 删除批量大小（`GC_BATCH_SIZE=50`）+ 批间 sleep 60s，保护 CCI API。
- ccictl 调用超时 30~60s + 重试 ≤3 次，避免调用堆积。
- 配置检查 30s 周期，避免空转。
- 单 Pod 创建串行执行（cron 触发同名任务不会并发，因 cron 自身按时间触发）。

### 6.4 冗余设计

**当前版本**：单副本（`replicas: 1`），主进程或 crond 异常时由 `process_manager.sh` 在容器内自动拉起；Pod 整体故障时由 CCI Deployment 控制器重新调度，期间错过的 cron 触发不会补偿。

**后续迭代方向**（**优先级：中**）：

- **多副本 + Leader Election**：将 `replicas` 提升到 ≥2，所有副本同时运行健康检查与配置加载，但仅 Leader 负责写 crontab、触发 cron、调度 GC。
- **Lease 选型限制**：CCI 2.0 **不支持** `coordination.k8s.io/v1.Lease` 资源；因此不能直接复用 client-go `leaderelection` 包。可选实现：
  - 基于 ConfigMap 的乐观锁：通过 `metadata.annotations` 中写入持有者与租约时间戳，结合 `resourceVersion` 做 CAS（参考早期 K8s Master HA 实现）。
  - 基于 Namespace 内自定义 Lock 文件（PV）的方案——CCI Pod 默认不挂载共享卷，性价比低，不推荐。
- **故障切换 SLA**：目标 Leader 失联后 ≤60s（一个 lease TTL）触发切换，且新 Leader 在 30s 内重建 crontab。

### 6.5 资源残留

- **临时文件**：`/tmp/pod-<uuid>.yaml` 在 `pod_creator.py` finally 块中删除。
- **历史 Pod**：`pod_cleaner.py` 周期清理，避免 Namespace 配额泄漏。
- **日志**：`RotatingFileHandler` 限制 10MB × 5 份，自动滚动。
- **PID 文件**：`/var/run/*.pid` 在 `cleanup` trap 中删除。

### 6.6 健康检查

- **Liveness Probe**：执行 `/usr/local/bin/health_check.sh --liveness`
  - `initialDelaySeconds: 30`
  - `periodSeconds: 30`
  - `timeoutSeconds: 10`
  - `failureThreshold: 3`
- **Readiness Probe**：执行 `/usr/local/bin/health_check.sh --readiness`
  - `initialDelaySeconds: 15`
  - `periodSeconds: 10`
  - `timeoutSeconds: 5`
  - `failureThreshold: 3`
- **Docker HEALTHCHECK**：`--interval=30s --timeout=10s --start-period=5s --retries=3`。

### 6.7 SLI/SLO治理

不涉及。

**说明**：本方案是对 Kubernetes 原生 `CronJob` 在 CCI 2.0 单租户面（Namespace 内）的简化实现，作为解决方案交付给单租户使用。CronDispatcher 自身既不是云服务的对外接口，也不参与云服务的可用性度量；其 SLI/SLO 由部署方（业务团队）按需自行定义，不构成对 CCI 云服务整体 SLI/SLO 的影响，故本设计文档不涉及该项治理。

### 6.8 数据可靠性设计

不涉及（CronDispatcher 自身不持有业务数据）。元数据持久化由 CCI/Kubernetes etcd 保证。

### 6.9 租户可靠性设计

CronDispatcher 严格按 Namespace 隔离：

- 一个 Namespace 部署一份 cron-dispatcher Deployment；
- ccictl 所有命令均带 `-n <namespace>` 限制操作范围；
- GC 列表使用 label selector + namespace，避免误删其他 Namespace 资源。

跨租户复用时各租户独立 Secret + 独立 Deployment，互不影响。

## 7. 安全/隐私/韧性

### 7.1 Low Level 威胁分析

| 威胁       | 来源                                      | 影响                                             | 缓解                                                                                          |
| ---------- | ----------------------------------------- | ------------------------------------------------ | --------------------------------------------------------------------------------------------- |
| AK/SK 泄露 | Secret 被未授权读取                       | 攻击者可在 Namespace 内以管理员身份创建/删除资源 | RBAC 限制 Secret 访问；定期轮换；建议接入企业 KMS                                             |
| 命令注入   | 任务 `name` / `configmap_name` 含特殊字符 | 通过 cron 表达式拼接逃逸                         | `pod_creator.py` 参数走 argv 而非 shell；ccictl 调用使用列表形式                              |
| YAML 注入  | 恶意 ConfigMap 的 `pod.yaml` 字段         | 创建特权 Pod                                     | `safe_yaml_load` 拒绝非 dict/list；下游由 CCI Admission 防护；建议 RBAC 限定 ConfigMap 写权限 |
| 拒绝服务   | 配置极短 cron `* * * * *` 高频拉起        | Namespace Pod 配额耗尽                           | `gc_policy` 自动清理；建议配额管控                                                            |
| 日志泄露   | 日志包含 stderr 中的凭据                  | 凭据外泄                                         | `cci_auth_manager.py` 仅日志输出操作名，不打印 AK/SK；详见 7.2.3                              |

### 7.2 安全/隐私/韧性设计

#### 7.2.1 安全隔离设计

- **Namespace 隔离**：所有 ccictl 操作硬编码 `-n <namespace>`。
- **进程隔离**：crond 与 main.py 各自独立进程，相互不可见配置文件以外的状态。
- **权限**：`/etc/cron-dispatcher-config` 与 `/etc/cron-dispatcher-gc-policy` 以 `readOnly: true` 挂载。
- **临时文件**：`/tmp/pod-<uuid>.yaml` 文件名带 9 位随机 UUID，避免符号链接攻击。

#### 7.2.2 认证与权限设计

- **入站认证**：CronDispatcher 自身不接收外部请求，无入站鉴权需求。
- **出站认证**：通过 `ccictl` 的 IAM auth-provider 模式，AK/SK + Domain 通过命令行参数注入到 ccictl kubeconfig。
- **最小权限**：建议 IAM 策略只授予 ConfigMap.get、Pod.create/get/delete、Secret.get（启动时） 权限。

#### 7.2.3 日志安全

- 凭据相关日志仅输出操作类型（如 `set-cluster`、`set-credentials`），不输出参数值。
- ConfigMap 内容写入日志前不过滤，因此 ConfigMap 不应放入凭据信息（建议运维约束）。
- 日志通过 LTS 集中存储，依赖 LTS 的访问控制。

### 7.3 数据安全设计

#### 7.3.1 数据安全风险识别

| 风险               | 数据类型                     | 处理                          |
| ------------------ | ---------------------------- | ----------------------------- |
| AK/SK              | 高敏感凭据                   | Secret 存储 + RBAC + 定期轮换 |
| Pod 模板 ConfigMap | 业务配置（含镜像地址、命令） | 一般敏感；RBAC 控制写入       |
| Cron 表达式        | 调度计划                     | 低敏感                        |
| 日志               | 运行状态                     | 低敏感；通过 LTS 控制访问     |

#### 7.3.2 数据保护设计

- **传输**：ccictl 与 CCI/IAM API 全程 HTTPS。
- **静态**：Kubernetes Secret 默认在 etcd 内 base64 存储；建议启用 etcd 加密（CCI 平台特性）。

#### 7.3.3 密钥管理

**默认实现**：通过 Kubernetes Secret（`cci-credentials`）持有 AK/SK，运维人员手工执行 `echo -n "<value>" | base64` 后写入 Secret 并 `ccictl apply`。容器启动时通过 `valueFrom.secretKeyRef` 注入到 `CCI_ACCESS_KEY` / `CCI_SECRET_KEY` / `CCI_DOMAIN_NAME` / `CCI_PROJECT_NAME` 环境变量。

**KMS 接入**：作为可选项，是否对接华为云 KMS / 企业 Vault 由租户根据自身安全合规要求决定，不在本方案的默认实现范围内。租户可自行扩展：

- 用 External Secrets Operator 等组件将 KMS 中的密钥同步到 K8s Secret。
- 或自定义 sidecar 在容器启动前从 KMS 拉取并写入临时文件，再由 `entrypoint.sh` 注入环境变量。

本方案保持 K8s Secret + base64 的最小依赖实现，便于在 CCI 2.0 默认能力下即可部署。

#### 7.3.4 证书生命周期管理

不涉及（CronDispatcher 自身不签发或托管证书；HTTPS 证书由 CCI/IAM 服务托管）。

### 7.4 隐私保护设计

#### 7.4.1 隐私PIA分析

不涉及。

**说明**：CronDispatcher 仅处理调度元数据（任务名、cron 表达式、Pod 模板引用），不收集、不存储、不传输任何个人数据。为避免误用，**使用说明（README）需明确约束：CronDispatcher 不能应用于涉及个人隐私数据处理的业务场景**；如有此类业务需求，需由业务方单独评估并向数据保护官（DPO）发起 PIA 流程。

#### 7.4.2 隐私保护方案设计

不涉及。

## 8. 生产就绪

### 8.1 升级和回退

#### 8.1.1 特性开关及白名单

不涉及（无运行时灰度开关）。

#### 8.1.2 特性开启

任务级开启路径：在 `cron-dispatcher-config` ConfigMap 中将 `state` 设为 `"on"`，CronDispatcher 30s 内自动加入 crontab。

#### 8.1.3 特性回退

任务级回退：将 `state` 改为 `"off"`，CronDispatcher 30s 内自动从 crontab 移除该任务。

镜像级回退：通过 `ccictl rollout undo deployment/cron-dispatcher` 回退到上一版本镜像。

#### 8.1.4 升级-> 回退 -> 再升级

- 镜像滚动升级策略：`maxUnavailable: 25%`、`maxSurge: 100%`、`progressDeadlineSeconds: 600`。
- 由于 `replicas: 1`，新旧 Pod 切换期间任务调度暂停 ≤30s（取决于 readiness 通过时间）。
- 回退仅依赖镜像 tag 切换，无 schema 迁移；可以无限次升级/回退。

#### 8.1.5 升级影响

- 升级期间错过的 cron 触发不会补偿（与 K8s CronJob `Forbid + missingDeadline` 行为一致）。
- crontab 由新 Pod 重建，无需迁移状态文件。

### 8.2 HCS 兼容性

不涉及。

**说明**：CCI 2.0 当前未下沉支持 HCS（HUAWEI CLOUD Stack）混合云场景，本方案的运行依赖项（`ccictl` 二进制下载源、`cci.<region>.myhuaweicloud.com` API 端点）均为公有云基础设施。HCS 适配将在 CCI 2.0 服务下沉到 HCS 时统一规划，当前不在交付范围内。

#### 8.2.1 操作系统依赖

- **基础镜像**：CentOS 8（vault.centos.org 镜像源）。
- **系统包**：`python3`、`python3-pip`、`cronie`、`curl`、`wget`、`unzip`、`procps-ng`。
- **可执行文件**：`/usr/local/bin/ccictl`（构建时下载）、`/usr/sbin/crond`。
- **目录依赖**：`/var/log/cron-dispatcher`、`/etc/cron-dispatcher-config`、`/etc/cron-dispatcher-gc-policy`、`/var/run`、`/var/spool/cron`。
- **不依赖** systemd / dbus，可在最小化容器中运行。

### 8.3 日志、监控与告警

- **日志**：通过 LTS 注解集成（见 4.5.2）。
- **监控**：当前不暴露指标，规划指标见 4.5.1。
- **告警**：本方案不涉及具体告警阈值与通知渠道的定义。租户可基于 LTS 自有的关键字匹配规则（如 `ERROR`、`[FAIL]`、`Failed to create Pod`）按需配置告警，不在 CronDispatcher 默认交付件中。

## 9. 资料

### 9.1 需求是否设计资料修改

#### 9.1.1 客户侧资料

不另行提供独立资料，**直接复用仓库根目录的 `README.md`**。`README.md` 已覆盖以下内容，可作为业务方使用手册：

- 概览与架构说明
- ConfigMap 配置格式与示例（任务、Pod 模板、GC 策略）
- 部署步骤（凭据、配置、Deployment）
- 环境变量、健康检查、Pod 标签
- Cron 表达式与时区
- 故障排查与调试命令

#### 9.1.2 运维侧资料

已存在以下运维资料，本需求不涉及修改，仅可能需补充：

- `README.md`：部署、配置、故障排查（已完整）。
- `INTEGRATION_TESTS.md`：集成测试 Docker 流程。
- `UNIT_TESTS.md`：单元测试运行说明。
- `TESTING_GUIDE.md`：测试整体指南。

### 9.2 资料模块设计

#### 9.2.1 基本概念

- **Cron Dispatcher**：CCI 2.0 Namespace 内的常驻定时任务调度服务。
- **Task**：一条定时任务定义，包括 cron 表达式与 Pod 模板引用。
- **Pod Template ConfigMap**：单独维护的 ConfigMap，`data.pod.yaml` 字段为 Pod YAML。
- **GC Policy**：垃圾回收策略，分全局与任务级两层配置。

#### 9.2.2 功能原理

参见第 3.2 / 3.3 节架构图与功能规格。

#### 9.2.3 计费说明

不涉及。

**说明**：CronDispatcher 自身不引入独立计费项。相关费用通过以下两部分由 CCI 平台统一计费：

- CronDispatcher 部署 Pod 自身的资源消耗（CPU / 内存 / 存储 / 网络）。
- CronDispatcher 下发并由 CCI 平台拉起的业务 Pod 的资源消耗。

租户在 CCI 控制台查看 Namespace 维度账单即可获得完整费用视图。

### 10. 测试建议

#### 10.1 单元测试

- 测试目录：`tests/unit/`，共 10 个测试文件。
- 覆盖范围：`logger_config`、`utils`、`cci_auth_manager`、`pod_creator`、`pod_cleaner`、`main` 全模块；正向、负向、边界场景。
- 执行方式：`scripts/run_unit_tests.sh` 或 `scripts/run_unit_tests_docker.sh`。
- 覆盖率目标：根据 `UNIT_TESTS.md`，建议 `--fail-under=80`。

#### 10.2 集成测试

- 测试目录：`tests/integration/`，目前 `test_pod_creation.py` 一个用例。
- 测试场景：
  - 端到端验证：在真实 CCI Namespace 中创建 ConfigMap → 通过 PodCreator 创建 Pod → 通过 ccictl 校验 Pod 已创建。
  - 资源命名带随机后缀，避免并发冲突。
- 执行方式：`scripts/run_integration_tests_docker.sh`，需提供 CCI 凭据环境变量。
- 资源清理：当前 teardown 已禁用以方便人工排障，长期建议恢复。

#### 10.3 建议补充的测试场景

- 配置热更新：tasks.yaml 修改后 30s 内生效的端到端测试。
- GC 干跑模式：`GC_DRY_RUN=true` 下不实际删除的验证。
- 异常恢复：杀死 crond / main.py 后 process_manager.sh 自动重启。
- 多 Region 部署：不同 `CCI_REGION` 下 ccictl 配置正确性。

### 11. 需求分解

#### 11.1 US/Task分解及工作量

按照本设计文档对应的项目代码实际完成情况，将已实现部分按模块拆分为以下 User Story / Task。工作量按人天（PD）评估，作为后续追溯与新成员熟悉项目的参照；对于 todo.md 中确认延后的演进项，单独列出供下一迭代评估。

**已交付模块（当前版本）**

| ID       | US/Task                                       | 模块/文件                                                                                                                                      | 关键交付件                                                                | 工作量(PD) | 状态   |
| -------- | --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- | ---------- | ------ |
| US-01    | 主调度服务（配置加载、热更新、crontab 重建）  | `src/main.py`                                                                                                                                  | `CronDispatcher` 类、`run` 主循环                                         | 5          | 已完成 |
| US-02    | Pod 动态创建                                  | `src/pod_creator.py`                                                                                                                           | 从 ConfigMap 拉取模板、UUID 注入、ccictl apply                            | 3          | 已完成 |
| US-03    | Pod 垃圾回收（按全局/任务级保留策略）         | `src/pod_cleaner.py`                                                                                                                           | 分组、排序、批量删除、Dry Run                                             | 4          | 已完成 |
| US-04    | CCI 认证管理                                  | `src/cci_auth_manager.py`                                                                                                                      | 环境变量加载、ccictl IAM auth-provider 配置                               | 2          | 已完成 |
| US-05    | 公共工具（命令重试、YAML 解析、临时文件清理） | `src/utils.py`                                                                                                                                 | `execute_command_with_retry`、`safe_yaml_load/dump`、`get_ccictl_command` | 1.5        | 已完成 |
| US-06    | 统一日志（stdout + 滚动文件）                 | `src/logger_config.py`                                                                                                                         | `setup_logger` 函数                                                       | 0.5        | 已完成 |
| US-07    | 容器进程管理（crond + 主进程，含自愈）        | `scripts/process_manager.sh`                                                                                                                   | start/stop/monitor/restart 全套命令                                       | 2          | 已完成 |
| US-08    | 容器入口与健康检查                            | `scripts/entrypoint.sh`、`scripts/health_check.sh`                                                                                             | liveness / readiness / verbose 三模式                                     | 1.5        | 已完成 |
| US-09    | 镜像与运行环境                                | `Dockerfile`、`Dockerfile.unit-test`、`Dockerfile.integration-test`、`requirements.txt`                                                        | CentOS 8 + Python + cronie + ccictl                                       | 1          | 已完成 |
| US-10    | 部署 YAML 与配置示例                          | `config/deployment.yaml`、`config/cron-dispatcher-config.yaml`、`config/cci-credentials-secrets.yaml`、`podTemplates/nginx-test-template.yaml` | 多 Namespace 示例配置                                                     | 1          | 已完成 |
| US-11    | 单元测试                                      | `tests/unit/` 共 10 个文件                                                                                                                     | logger / utils / auth / creator / cleaner / main 全模块覆盖               | 3          | 已完成 |
| US-12    | 集成测试                                      | `tests/integration/test_pod_creation.py`                                                                                                       | 真实 CCI 环境 Pod 创建端到端用例                                          | 2          | 已完成 |
| US-13    | 文档                                          | `README.md`、`UNIT_TESTS.md`、`INTEGRATION_TESTS.md`、`TESTING_GUIDE.md`                                                                       | 部署 / 测试 / 故障排查                                                    | 1.5        | 已完成 |
| **小计** |                                               |                                                                                                                                                |                                                                           | **28 PD**  |        |

**后续迭代候选项**（来源于 todo.md 确认结果）

| ID    | US/Task                                                   | 来源       | 优先级 | 预估工作量(PD) | 状态   |
| ----- | --------------------------------------------------------- | ---------- | ------ | -------------- | ------ |
| US-14 | 可观测性指标埋点（Prometheus `/metrics` 端点 + LTS 写入） | todo.md #3 | 低     | 5              | 待规划 |
| US-15 | 多副本 + 基于 ConfigMap 的 Leader Election                | todo.md #4 | 中     | 8              | 待规划 |
| US-16 | 友商对齐补充（CCI 2.0 原生 CronJob 平滑迁移设计）         | todo.md #1 | 低     | 2              | 待规划 |

#### 11.2 外部需求清单

不涉及。

**说明**：本方案在 CCI 2.0 现有能力（Deployment、Pod、ConfigMap、Secret、`ccictl`）之上闭环实现，不需要向 CCI 平台、IAM、LTS、KMS、HCS 等周边团队提出新增外部需求。`README.md` 中已记录的 VPCEP + Private Zone 部署也是租户侧的网络配置，不构成对周边团队的研发需求。
