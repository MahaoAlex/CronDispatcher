# CronDispatcher

## 功能概述

CronDispatcher 是基于 Kubernetes 的命名空间级 cron 任务管理平台，通过 ConfigMap 驱动的声明式配置模式，实现定时任务的容器化编排与生命周期管理。

## 功能详设

### 任务创建

1. `CronDispatcher`通过Deployment部署在CCI2.0的命名空间类，作用范围局限在本命名空间下，副本数为1。暂不做多活和主备，通过Deployment控制故障场景的自动拉起。
2. `CronDispatcher`基于CentOS的基础镜像，并配置健康检查，健康检查通过判断linux的`crond` 服务的状态进行。
3. 启用`crond`服务的日志，记录任务执行情况。
4. 通过读取本命名空间下Configmap中配置的定时任务信息，Configmap的名称为：`cron-dispatcher-config`。
5. `CronDispatcher`基于python实现，获取配置信息，基于ccictl进行pod的创建，刷新linux crontab
6. AWS的scheduled task基于EventBridge的Scheduled Standard触发。当前`CronDispatcher`暂不进行任务拉起失败场景的故障重试。
7. `CronDispatcher`的执行的结果为Crontab的规则，暂不校验具体的规则是否最终拉起CCI2.0的Pod任务。
8. `CronDispatcher`最终拉起的Pod拥有如下特殊标签：

```yaml
apiVersion: v1
kind: Pod
metadata:
  name："<your-task-name>-<uuid>" # Pod名称和实例唯一标识保持一致,uuid的阶段为9位
  labels:
    app.kubernetes.io/managed-by: CronDispatcher  # 管理工具
    cron-dispatcher.io/task-name: "your-task-name"  # 任务名称,cron-dispatcher-config中指定
    cron-dispatcher.io/instance: "<your-task-name>-<uuid>"  # 和Pod Name保持一致，实例唯一标识,uuid的阶段为9位
```

9.  设计中允许同镜像的两个pod同时运行。
10. 华为云后台做客户异常状态的监控
11. 通过Dispatcher容器的标准输出日志中进行跟踪记录拉起的Cron Pod
12. `CronDispatcher`需要使用ccictl工具进行Pod创建，ccictl遵循权限最小化原则，需要创建一个独立的华为云账号，并生成最小权限（增删改查CCI2.0的负载）的AK、SK信息。
13. 当前设计阶段不做`cron-dispatcher-config` 和 `cron-dispatcher-gc-policy`的热更新判断。

### 时区管理

1. `CronDispatcher` 默认按照UTC时间处理cron任务的时区，
2. 可以通过`CronDispatcher` 的`CronTimeZone`的环境变量进行指定。类似`CronTimeZone`：`Africa/Johannesburg`
### 任务清理

1. 基于CCI2.0的配额规则，需要对成功运行结束（Succeed）的任务Pod和任务执行失败的Pod进行清理。
2. 清理规则可以通过名为`cron-dispatcher-gc-policy`的configmap进行配置，默认的规则为保留最近成功3个、失败的最多保留3个，增加Pod标识。
3. 清理过程中会统一基于Pod的Label标签进行判断，判断`app.kubernetes.io/managed-by`进行统一判断
4. 清理过程中的保留，都是按照时间排序，保留时间最近的3个

## 系统关键输入

### cron-dispatcher-config

#### 1. 基本结构
* 使用 YAML 格式存储任务配置
* 顶层为任务列表（数组结构），支持定义多个 Cron 任务
* 每个任务包含以下核心字段：
    * name: 任务唯一标识符（必须）
    * schedule: Cron 表达式（必须）
    * podTemplatePath: Pod 配置文件路径（必须）
    * State: on / off，定义规则是否开启（可选，默认Turned on）
* 建议通过 ConfigMap 挂载方式提供 Pod **配置文件**，挂载到上述的`podTemplatePath`

#### 2. Cron 表达式规范

* 支持标准 Unix Cron 格式：分钟 小时 日 月 周
* 支持特殊字符：`*, ?, -, /, ,`

#### 3. Pod 配置文件要求

* 必须是符合 Kubernetes API 规范的Pod定义YAML
* 通过绝对路径指定，路径解析规则由 CronDispatcher 实现定义

#### 4.Configmap样例

1. **Namespace：cv-cd-generators**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cron-dispatcher-config
  namespace: cv-cd-generators
data:
  tasks.yaml: |
    - name: custom-row-generator
      schedule: "0 0/1 * * ? *"  # 每小时的第0分钟触发，即每小时执行一次
      podTemplatePath: /etc/cron-templates/custom-row-generator-pod.yaml
      state: on
    - name: delta-rule-based-row-generator
      schedule: "6 0/1 * * ? *"  # 每小时的第6分钟触发，即每小时执行一次（延迟6分钟）
      podTemplatePath: /etc/cron-templates/delta-rule-based-row-generator-pod.yaml
      state: on
    - name: editorial-row-generator
      schedule: "0/30 * * * *"  # 每30分钟触发一次（0分和30分）
      podTemplatePath: /etc/cron-templates/editorial-row-generator-pod.yaml
      state: on
    - name: layout-cachenator
      schedule: "0 0 1 1 ? *"  # 每年1月1日午夜0点触发（每年执行一次）
      podTemplatePath: /etc/cron-templates/layout-cachenator-pod.yaml
      state: off
    - name: layout-generator
      schedule: "30 0/3 * * ? *"  # 每3小时的第30分钟触发（0:30、3:30、6:30等）
      podTemplatePath: /etc/cron-templates/layout-generator-pod.yaml
      state: on
    - name: personalised-context-row-generator
      schedule: "30 0/6 * * ? *"  # 每6小时的第30分钟触发（0:30、6:30、12:30、18:30）
      podTemplatePath: /etc/cron-templates/personalised-context-row-generator-pod.yaml
      state: on
    - name: placeholder-row-generator
      schedule: "30 1 * * ? *"  # 每天凌晨1:30触发（每天执行一次）
      podTemplatePath: /etc/cron-templates/placeholder-row-generator-pod.yaml
      state: on
    - name: rule-based-row-generator
      schedule: "0 0/1 * * ? *"  # 每小时的第0分钟触发，即每小时执行一次
      podTemplatePath: /etc/cron-templates/rule-based-row-generator-pod.yaml
      state: on
    - name: user-context-rule-row-generator
      schedule: "30 1 * * ? *"  # 每天凌晨1:30触发（每天执行一次）
      podTemplatePath: /etc/cron-templates/user-context-rule-row-generator-pod.yaml
      state: off
```

2. **Namespace：data-ingest**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cron-dispatcher-config
  namespace: cv-cd-generators
data:
  tasks.yaml: |
    - name: bouquets-ingest-scheduler
      schedule: "45 12 * * ? *"  # 每天12点45分触发
      podTemplatePath: /etc/cron-templates/bouquets-ingest-scheduler-pod.yaml
      state: off
    - name: boxoffice-ingest-scheduler
      schedule: "0 */6 * * ? MON-FRI"  # 每周一到周五，每隔6小时的0分触发（0:00、6:00、12:00、18:00 ）
      podTemplatePath: /etc/cron-templates/boxoffice-ingest-scheduler-pod.yaml
      state: on
    - name: bulk-agnostic-vod-ingest-scheduler
      schedule: "30 */1 * * ? *"  # 每小时的第30分钟触发，即每小时执行一次（延迟30分钟）
      podTemplatePath: /etc/cron-templates/bulk-agnostic-vod-ingest-scheduler-pod.yaml
      state: off
    - name: epg-channels-ingest-scheduler
      schedule: "45 12 * * ? *"  # 每天12点45分触发
      podTemplatePath: /etc/cron-templates/epg-channels-ingest-scheduler-pod.yaml
      state: off
    - name: epg-ingest-scheduler
      schedule: "0 6 * * ? *"  # 每天6点0分触发
      podTemplatePath: /etc/cron-templates/epg-ingest-scheduler-pod.yaml
      state: on
    - name: exploraapps-ingest-scheduler
      schedule: "59 12 * * ? *"  # 每天12点59分触发
      podTemplatePath: /etc/cron-templates/exploraapps-ingest-scheduler-pod.yaml
      state: off
    - name: gotv-ingest-scheduler
      schedule: "30 */1 * * ? *"  # 每小时的第30分钟触发，即每小时执行一次（延迟30分钟）
      podTemplatePath: /etc/cron-templates/gotv-ingest-scheduler-pod.yaml
      state: on
    - name: imdb-ingest-scheduler
      schedule: "15 19 * * ? *"  # 每天19点15分触发
      podTemplatePath: /etc/cron-templates/imdb-ingest-scheduler-pod.yaml
      state: on
    - name: movielens-ingest-scheduler
      schedule: "0 6 ? * MON-FRI *"  # 每周一到周五，6点0分触发
      podTemplatePath: /etc/cron-templates/movielens-ingest-scheduler-pod.yaml
      state: off
    - name: showmax-ingest-scheduler
      schedule: "55 20 * * ? *"  # 每天20点55分触发
      podTemplatePath: /etc/cron-templates/showmax-ingest-scheduler-pod.yaml
      state: off
    - name: vod-ingest-scheduler
      schedule: "30 */1 * * ? *"  # 每小时的第30分钟触发，即每小时执行一次（延迟30分钟）
      podTemplatePath: /etc/cron-templates/vod-ingest-scheduler-pod.yaml
      state: on
```

### cron-dispatcher-gc-policy 

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cron-dispatcher-gc-policy
  namespace: cv-cd-generators  # 与任务配置保持同一命名空间
data:
  gc-policy.yaml: |
    # 垃圾回收策略配置
    retentionPolicy:
      successPods:
        maxRetained: 3           # 保留最近成功的3个Pod
        sortBy: creationTimestamp # 按创建时间排序（最新的保留）
        order: descending        # 降序排列（最新的在前）
      failedPods:
        maxRetained: 3           # 保留最近失败的3个Pod
        sortBy: creationTimestamp # 按创建时间排序
        order: descending        # 降序排列
    labelSelector:
      matchLabels:
        app.kubernetes.io/managed-by: CronDispatcher # 筛选由CronDispatcher管理的Pod
    cleanupInterval: "60m"  # 清理任务执行间隔（每60分钟执行一次）
    timeToLive: "1h"       # 超出保留数量的Pod的存活时间上限（保留1小时）
```