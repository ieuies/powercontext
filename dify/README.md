# 酒馆老板的记性（Dify × seekdb）

一个会记住你的酒馆 NPC。你在第一晚说了名字、口味和正在找的东西；第二晚换个会话再进门，老板会主动提起这些事。

- **Dify** 负责流程编排：接收输入 → 调 HTTP 接口查记忆 → 组 prompt 调模型 → 调 HTTP 接口写记忆 → 回复。
- **seekdb** 负责持久化与检索：`players` / `memories` / `turns` 三张表；记忆召回走 seekdb 的**全文索引**（`MATCH ... AGAINST`），不是把历史整段塞进 prompt。

## 目录

```
dify/
├── app.yml                     # Dify Chatflow DSL（导入这一个文件）
├── sql/init.sql                # seekdb 建库建表
├── service/                    # 记忆服务（Python 标准库 + pymysql）
│   ├── main.py
│   └── requirements.txt
├── scripts/
│   ├── demo.py                 # 两晚会话的端到端回放
│   ├── validate_dsl.py         # DSL 静态校验
│   └── capture_evidence.sh     # 生成本目录 samples/ 的证据
└── samples/
    ├── conversation.md         # 验证样例：输入、步骤、预期
    ├── demo-output.txt         # 实际运行输出
    └── seekdb-rows.txt         # 实际写入 seekdb 的行
```

## 环境

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Dify | 1.x（DSL `version: 0.1.5`，`advanced-chat`） | 任何支持 Chatflow 的 1.x 均可导入 |
| seekdb | 1.4.0 | 需要 `ik` 全文分词器（官方镜像自带） |
| Python | 3.11+ | 只依赖 `pymysql` |
| 模型 | OpenAI 兼容接口 | DSL 里占位为 `openai_api_compatible / gpt-4o-mini`，导入后按你的模型改绑 |

## 启动步骤

### 1. 初始化 seekdb

```bash
mysql -h127.0.0.1 -P2881 -uroot < sql/init.sql
```

验证：

```bash
mysql -h127.0.0.1 -P2881 -uroot -D tavern -e "SHOW TABLES;"
# players / memories / turns
```

### 2. 启动记忆服务

```bash
pip install -r service/requirements.txt
TAVERN_DB_HOST=127.0.0.1 TAVERN_DB_PORT=2881 TAVERN_DB_USER=root TAVERN_DB_PASSWORD= TAVERN_PORT=8080 \
  python service/main.py
```

健康检查：

```bash
curl http://127.0.0.1:8080/health
# {"status": "ok"}
```

> Dify 跑在 Docker 里时，`app.yml` 中的 `host.docker.internal:8080` 可直接用；如果 Dify 与服务在同一台机器的进程里，把两处 URL 改成 `127.0.0.1:8080`。

### 3. 导入 Dify 应用

1. Dify → 工作室 → 导入 DSL → 选择 `app.yml`；
2. 打开应用，在「老板开口」LLM 节点里把模型换成你环境里可用的模型（保持 OpenAI 兼容协议即可）；
3. 确认两个 HTTP 请求节点的地址能通（见上一步的说明）；
4. 发布应用。

应用入口：Dify 的聊天界面，或 `POST /v1/chat-messages`（`response_mode: streaming`）。

## 验证样例

见 [`samples/conversation.md`](samples/conversation.md)。核心是**两晚、两个会话**：

| 步骤 | 输入 | 预期 |
| --- | --- | --- |
| 第一晚 | `老板，我叫阿澈，我喜欢桂花酒，讨厌吵闹的客人。` | 老板回应，并把 `name`、两条 `preference` 写入 seekdb |
| 第一晚 | `我最近在找一个叫'青铜钥匙'的东西。` | 写入一条 `event` |
| 第二晚（新会话） | `老板，还记得我吗？` | 回复里出现“阿澈”“桂花酒”等第一晚的信息 |

跨会话证据直接查库：

```bash
mysql -h127.0.0.1 -P2881 -uroot -D tavern -e "SELECT player_id, kind, content FROM memories ORDER BY id;"
```

服务侧可以不开 Dify 先自测（等价于 Dify 的两个 HTTP 节点）：

```bash
python scripts/demo.py --base-url http://127.0.0.1:8080
# 末尾输出：OK: 跨会话记忆命中 name / preference / event
```

实际输出见 [`samples/demo-output.txt`](samples/demo-output.txt)，seekdb 实际写入的行见 [`samples/seekdb-rows.txt`](samples/seekdb-rows.txt)。

DSL 静态校验：

```bash
python scripts/validate_dsl.py app.yml
# OK: 5 nodes, 4 edges, references resolved
```

## seekdb 在应用中承担什么

| 表 | 作用 |
| --- | --- |
| `players` | 客人档案，保存名字（`name`） |
| `memories` | 长期记忆：`name` / `preference` / `event`，带 `ik` 全文索引 |
| `turns` | 每轮原始对话，用于“最近聊了什么” |

两个实际作用点：

1. **写入**：「记住这一轮」节点把本轮提取出的事实写进 `memories`，把原话写进 `turns`；
2. **检索**：「查询记忆」节点用当前这句话在 `memories.content` 上做全文检索（`MATCH ... AGAINST`），只把命中的少数几条交给模型——这是 seekdb 在功能上的实际作用，而不是仅仅当个连接配置。

## 已知限制

- 记忆抽取用的是规则（正则）识别中文里的名字与偏好，复杂表述可能抽不到；抽不到时会退化为一条 `event` 原话。
- 全文检索对中文依赖 `ik` 分词器；若你的 seekdb 没有该分词器，请把 `init.sql` 里的 `WITH PARSER ik` 去掉（检索仍可用，召回会粗一些）。
- 本仓库的开发环境没有可用的 Dify 运行时（Docker Hub 不可达、无模型 Key），因此**DSL 只做了静态校验**（节点、边、变量引用），没有在本机完成真实导入；导入后请按上面的步骤 1-3 验证一次。
- `app.yml` 里的模型名与 base_url 均为占位，需按你的环境改绑。
