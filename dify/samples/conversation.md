# 验证样例：两晚两次会话

## 初始状态

- seekdb 已执行 `sql/init.sql`，`players` / `memories` / `turns` 为空；
- 记忆服务监听 `:8080`；
- Dify 应用已导入并发布，`player_id` 固定为 `player-001`。

恢复初始状态：

```sql
USE tavern;
DELETE FROM memories;
DELETE FROM turns;
DELETE FROM players;
```

## 场景一：老板记住你

**输入（第一晚）**

```
老板，我叫阿澈，我喜欢桂花酒，讨厌吵闹的客人。
```

**预期**

- 回复是酒馆老板口吻，接住“阿澈”“桂花酒”“安静”这些信息；
- seekdb 新增：`name=阿澈`、`preference=喜欢桂花酒`、`preference=讨厌吵闹的客人`；
- `turns` 新增一条本轮原话与回复。

**继续输入**

```
我最近在找一个叫'青铜钥匙'的东西。
```

**预期**：新增 `event` 记忆一条（原话），`turns` 再增一条。

## 场景二：换一个会话，老板还记得

**操作**：在 Dify 里新开一个会话（`conversation_id` 变化），`player_id` 仍是 `player-001`。

**输入**

```
老板，还记得我吗？
```

**预期**

- 回复里出现“阿澈”，并主动提到桂花酒（或安静的位置）等第一晚的信息；
- 不应把客人当第一次见面。

**核查方式**

1. 看回复文本是否包含 `阿澈`、`桂花酒`；
2. 看 seekdb：

```sql
SELECT player_id, kind, content FROM memories ORDER BY id;
```

应能看到 `name/阿澈`、`preference/喜欢桂花酒`、`preference/讨厌吵闹的客人`、`event/…青铜钥匙…`。

3. 看 Dify 的节点执行记录：「查询记忆（seekdb）」节点的响应里 `memories` 至少包含上述若干条；「记住这一轮」节点的响应里 `stored` 非空。

## 场景三：记忆为空时

**操作**：换 `player_id=player-002`，第一次进门。

**输入**

```
老板，第一次来，有什么推荐？
```

**预期**：老板像第一次见面，不编造这位客人的历史；`players` 新增 `player-002`，`memories` 只可能新增本轮 `event`。

## 服务侧等价回放

不开 Dify 也能验证同样的链路（Dify 的两个 HTTP 节点就是这两个接口）：

```bash
python scripts/demo.py --base-url http://127.0.0.1:8080
```

实际输出已保存在 [`demo-output.txt`](demo-output.txt)，seekdb 落库结果在 [`seekdb-rows.txt`](seekdb-rows.txt)。
