# 开写前环境说明（技术线维护）

> 这份文档回答一个问题：**现在能不能直接开写？** 以及出问题时去哪看。
> 最后更新：2026-11-12

## 一条命令自检

```bash
python3 scripts/novel_doctor.py --project-root /home/liutingqiu/store
```

全绿即可开写。它会检查：Python/FTS5、00_memory 三件套、核心脚本、RAG 库与索引一致性、
实体质量（表头污染）、中文召回自测、git 状态、Obsidian 产物、手稿状态。有 FAIL 会直接给修复命令。

## 写一章会发生什么

```
/继续写
  → 写前读 00_memory（plan / state / character / foreshadowing）
  → plot_rag_retriever 生成 next_plot_context.md（已融合 Novel-RAG 高维记忆）
  → 正文落盘 03_manuscript/
  → 质量门禁 chapter_gate_check.py → gate_result.json
  → 自动同步：ingest 00_memory → RAG；导出 Obsidian 实体笔记 + Canvas
  → 开启 .git 时，30 分钟一次自动快照
```

同步失败只会打印警告，不会阻塞本章写作。

## Novel-RAG 的行为约定

- **库位置**：`<项目根>/.novel_rag/novel_memory.db`，每个小说项目独立，不碰全局记忆库。
- **mtypes**：`fact` / `inference`（必须带 premise 与 falsifier）/ `preference`（铁律）/
  `negresult`（已否证路线）/ `method` / `task`。
- **tier**：0 铁律、1 定稿、2 草案、3 正文已写、4 归档。tier 只做加权，不会压过相关性。
- **中文检索**：入库与查询统一用"中文二元组 + 英文单词"分词（fts_text 列）。
  旧库首次打开会自动重建 FTS 并回填。
- **幂等**：同一 `mtype|subject|claim` 重复写入只会更新，不会增殖。
- **取代链**：改纲用 `supersede()`，旧结论保留并压到末尾，不物理删除。
- **离题下沉**：查询无相关性信号的记忆分数 ×0.15，避免铁律每次都霸占 top-k；
  铁律仍会通过 `alerts` 单独出现在上下文里。

## Obsidian 产物的归属

- `00_worldview/entities/*.md` 与 `worldview_canvas.canvas` 是**生成物**，每次同步会重写。
  想改设定请改 `00_memory/`（plan / world_state / character_tracker），再让同步重新生成。
- `00_worldview/00_全景关系图谱.md` 同理，是 Mermaid 汇总页。

## 版本历史

- `/home/liutingqiu/store` 是 git 仓库（`main`），初始提交 `04fbd79`。
- `novel-snapshot.timer` 每 30 分钟提交一次快照（无改动则跳过）：
  `systemctl --user list-timers novel-snapshot.timer`
- 回滚：`git -C /home/liutingqiu/store log` 找到提交后 `git checkout <sha> -- 03_manuscript/第N章.md`。
- `.novel_rag/` 不进版本库（可重建），`.obsidian/workspace.json` 也不进。

## 与写作线（Codex）的协作通道

黑板：`~/.raw/mesh/blackboard.db`（raw.mesh），工具是 `raw_task`。

```bash
# 查收
raw_task {action:"poll", params:{recipient:"codex-gemini"}}
# 发送
raw_task {action:"send", params:{sender:"dsh-tech", recipient:"codex-gemini", text:"..."}}
```

分工：写作线 `codex-gemini` 只写 `00_memory/`、`03_manuscript/`；技术线 `dsh-tech`
只改 `scripts/`、`.github/`。跨线改动用黑板 create 登记任务。

## 已知限制

- 专有名词（境界名、宗门名、人名）当前是占位符，RAG 里对应实体也是占位名；定名后重建库即可。
- `raw_term` 依赖 tmux，本机未运行，暂不可用；协作只走 `raw_task`。
- CI 矩阵 3.9 钉在 `ubuntu-22.04`（`ubuntu-latest` 已无 3.9 构建）。
