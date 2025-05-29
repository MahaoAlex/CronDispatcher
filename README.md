# CronDispatcher Design Proposal

## Feature Overview

CronDispatcher is a Kubernetes namespace-level cron job management platform that implements containerized orchestration and lifecycle management of scheduled tasks through a declarative configuration mode driven by ConfigMap.

## Detailed Feature Design

### Task Creation

1. `CronDispatcher` is deployed in CCI2.0 namespaces through Deployment, with scope limited to the current namespace and replica count of 1. Multi-active and master-slave configurations are not implemented currently; automatic recovery in failure scenarios is controlled through Deployment.
2. `CronDispatcher` is based on CentOS base image and configured with health checks. Health checks are performed by monitoring the status of the Linux `crond` service.
3. Enable logging for the `crond` service to record task execution status.
4. Read scheduled task information from ConfigMap in the current namespace. The ConfigMap name is: `cron-dispatcher-config`.
5. `CronDispatcher` is implemented in Python, retrieves configuration information, creates pods using ccictl, and refreshes the Linux crontab.
6. AWS scheduled tasks are triggered by EventBridge rule which type is `Scheduled Standard`. Currently, `CronDispatcher` does not implement failure retry for task launch failures.
7. The execution result of `CronDispatcher` is Crontab rules. It does not validate whether the specific rules ultimately launch CCI2.0 Pod tasks.
8. Pods launched by `CronDispatcher` have the following special labels:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: "<your-task-name>-<uuid>" # Pod name and instance unique identifier are consistent, uuid is 9 digits
  labels:
    app.kubernetes.io/managed-by: CronDispatcher  # Management tool
    cron-dispatcher.io/task-name: "your-task-name"  # Task name, specified in cron-dispatcher-config
    cron-dispatcher.io/instance: "<your-task-name>-<uuid>"  # Consistent with Pod Name, instance unique identifier, uuid is 9 digits
```

9. The design allows two pods with the same docker image to run simultaneously.
10. Huawei Cloud backend monitors customer abnormal status.
11. Track and record launched Cron Pods through stdout logs of the Dispatcher container.
12. `CronDispatcher` needs to use the ccictl tool for Pod creation. ccictl follows the principle of least privilege and requires creating an independent Huawei Cloud account and generating AK/SK information with minimal permissions (CRUD operations for CCI2.0 workloads).
13. The current design phase does not implement hot update detection for `cron-dispatcher-config` and `cron-dispatcher-gc-policy`.

### Timezone Management

1. `CronDispatcher` processes cron task timezones according to UTC time by default.
2. Can be specified through the `CronTimeZone` environment variable of `CronDispatcher`. For example, `CronTimeZone`: `Africa/Johannesburg`

### Task Cleanup

1. Based on CCI2.0 quota rules, garbage collection is needed for successfully completed (Succeeded) task Pods and failed task Pods.
2. Pod cleanup is configured at the Task dimension through a ConfigMap named `cron-dispatcher-gc-policy`.
3. `cron-dispatcher-gc-policy` supports Task-level configuration + global default rules structure. Task-level matching is done through the taskSelector field.
4. Global default rules are configured through the Global section. The default rule is to retain the latest 3 successful and up to 3 failed pods, with Pod identification added.
5. During cleanup, unified judgment is based on Pod Label tags, specifically checking `app.kubernetes.io/managed-by`.
6. Retention during cleanup is sorted by time, keeping the 3 most recent ones.
7. Supports enabling simulated cleanup through environment variable GC_DRY_RUN=true, which only outputs the list of Pods to be deleted without executing actual deletion.
8. Supports batch deletion mechanism. Configure the number of Pods to clean per batch through environment variable GC_BATCH_SIZE. By default, a maximum of 50 Pods are deleted at a time to avoid excessive API Server pressure.

## Key System Inputs

### cron-dispatcher-config

#### 1. Basic Structure
* Uses YAML format to store task configuration
* Top level is a task list (array structure), supporting definition of multiple Cron tasks
* Each task contains the following core fields:
    * name: Unique task identifier (required)
    * schedule: Cron expression (required)
    * podTemplatePath: Pod configuration file path (required)
    * State: on / off, defines whether the rule is enabled (optional, default is on)
* Recommend providing Pod **configuration files** through ConfigMap mount, mounted to the above `podTemplatePath`

#### 2. Cron Expression Specification

* Supports standard Unix Cron format: minute hour day month week
* Supports special characters: `*, ?, -, /, ,`

#### 3. Pod Configuration File Requirements

* Must be Pod definition YAML compliant with Kubernetes API specifications
* Specified through absolute path, path resolution rules are defined by CronDispatcher implementation

#### 4. ConfigMap Examples

1. **Namespace: cv-cd-generators**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cron-dispatcher-config
  namespace: cv-cd-generators
data:
  tasks.yaml: |
    - name: custom-row-generator
      schedule: "0 0/1 * * ? *"  # Triggers at minute 0 of every hour, executes once per hour
      podTemplatePath: /etc/cron-templates/custom-row-generator-pod.yaml
      state: on
    - name: delta-rule-based-row-generator
      schedule: "6 0/1 * * ? *"  # Triggers at minute 6 of every hour, executes once per hour (6-minute delay)
      podTemplatePath: /etc/cron-templates/delta-rule-based-row-generator-pod.yaml
      state: on
    - name: editorial-row-generator
      schedule: "0/30 * * * *"  # Triggers every 30 minutes (at 0 and 30 minutes)
      podTemplatePath: /etc/cron-templates/editorial-row-generator-pod.yaml
      state: on
    - name: layout-cachenator
      schedule: "0 0 1 1 ? *"  # Triggers at midnight on January 1st every year (executes once per year)
      podTemplatePath: /etc/cron-templates/layout-cachenator-pod.yaml
      state: off
    - name: layout-generator
      schedule: "30 0/3 * * ? *"  # Triggers at minute 30 of every 3 hours (0:30, 3:30, 6:30, etc.)
      podTemplatePath: /etc/cron-templates/layout-generator-pod.yaml
      state: on
    - name: personalised-context-row-generator
      schedule: "30 0/6 * * ? *"  # Triggers at minute 30 of every 6 hours (0:30, 6:30, 12:30, 18:30)
      podTemplatePath: /etc/cron-templates/personalised-context-row-generator-pod.yaml
      state: on
    - name: placeholder-row-generator
      schedule: "30 1 * * ? *"  # Triggers at 1:30 AM every day (executes once per day)
      podTemplatePath: /etc/cron-templates/placeholder-row-generator-pod.yaml
      state: on
    - name: rule-based-row-generator
      schedule: "0 0/1 * * ? *"  # Triggers at minute 0 of every hour, executes once per hour
      podTemplatePath: /etc/cron-templates/rule-based-row-generator-pod.yaml
      state: on
    - name: user-context-rule-row-generator
      schedule: "30 1 * * ? *"  # Triggers at 1:30 AM every day (executes once per day)
      podTemplatePath: /etc/cron-templates/user-context-rule-row-generator-pod.yaml
      state: off
```

2. **Namespace: data-ingest**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cron-dispatcher-config
  namespace: data-ingest
data:
  tasks.yaml: |
    - name: bouquets-ingest-scheduler
      schedule: "45 12 * * ? *"  # Triggers at 12:45 PM every day
      podTemplatePath: /etc/cron-templates/bouquets-ingest-scheduler-pod.yaml
      state: off
    - name: boxoffice-ingest-scheduler
      schedule: "0 */6 * * ? MON-FRI"  # Triggers at minute 0 every 6 hours, Monday to Friday (0:00, 6:00, 12:00, 18:00)
      podTemplatePath: /etc/cron-templates/boxoffice-ingest-scheduler-pod.yaml
      state: on
    - name: bulk-agnostic-vod-ingest-scheduler
      schedule: "30 */1 * * ? *"  # Triggers at minute 30 of every hour, executes once per hour (30-minute delay)
      podTemplatePath: /etc/cron-templates/bulk-agnostic-vod-ingest-scheduler-pod.yaml
      state: off
    - name: epg-channels-ingest-scheduler
      schedule: "45 12 * * ? *"  # Triggers at 12:45 PM every day
      podTemplatePath: /etc/cron-templates/epg-channels-ingest-scheduler-pod.yaml
      state: off
    - name: epg-ingest-scheduler
      schedule: "0 6 * * ? *"  # Triggers at 6:00 AM every day
      podTemplatePath: /etc/cron-templates/epg-ingest-scheduler-pod.yaml
      state: on
    - name: exploraapps-ingest-scheduler
      schedule: "59 12 * * ? *"  # Triggers at 12:59 PM every day
      podTemplatePath: /etc/cron-templates/exploraapps-ingest-scheduler-pod.yaml
      state: off
    - name: gotv-ingest-scheduler
      schedule: "30 */1 * * ? *"  # Triggers at minute 30 of every hour, executes once per hour (30-minute delay)
      podTemplatePath: /etc/cron-templates/gotv-ingest-scheduler-pod.yaml
      state: on
    - name: imdb-ingest-scheduler
      schedule: "15 19 * * ? *"  # Triggers at 7:15 PM every day
      podTemplatePath: /etc/cron-templates/imdb-ingest-scheduler-pod.yaml
      state: on
    - name: movielens-ingest-scheduler
      schedule: "0 6 ? * MON-FRI *"  # Triggers at 6:00 AM, Monday to Friday
      podTemplatePath: /etc/cron-templates/movielens-ingest-scheduler-pod.yaml
      state: off
    - name: showmax-ingest-scheduler
      schedule: "55 20 * * ? *"  # Triggers at 8:55 PM every day
      podTemplatePath: /etc/cron-templates/showmax-ingest-scheduler-pod.yaml
      state: off
    - name: vod-ingest-scheduler
      schedule: "30 */1 * * ? *"  # Triggers at minute 30 of every hour, executes once per hour (30-minute delay)
      podTemplatePath: /etc/cron-templates/vod-ingest-scheduler-pod.yaml
      state: on
```

### cron-dispatcher-gc-policy 

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cron-dispatcher-gc-policy
data:
  gc-policy.yaml: |
    global:  # Global default rules (effective when no Task match is found)
      success: 3  # Number of successful tasks to retain
      failure: 3  # Number of failed tasks to retain
    tasks:  # Task-level configuration (higher priority than global)
      - taskSelector:  # Label selector to match specific Task
          cron-dispatcher.io/task-name: "your-task-name-A"  # Task name
        success: 5  # Retain 5 successful tasks for this Task
        failure: 2  # Retain 2 failed tasks for this Task
      - taskSelector:
          cron-dispatcher.io/task-name: "your-task-name-B"  # Task name
        success: 10  # Retain 10 successful tasks
        failure: 5  # Retain 5 failed tasks
    labelSelector:
      matchLabels:
        app.kubernetes.io/managed-by: CronDispatcher # Filter Pods managed by CronDispatcher
    cleanupInterval: "60m"  # Cleanup task execution interval (every 60 minutes)
    timeToLive: "1h"       # Maximum survival time for Pods exceeding retention count (retain for 1 hour)
```
