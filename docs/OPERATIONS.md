# 当班处置

收到新一批换热片区申报时先运行 `validate`。有隔离记录时对照 `reasons` 回查来源单号，再通过 `preview` 确认是否仍能覆盖当班。

## 先重算再发布

1. 先看 `/api/replay` 的保留样本与基线证据。高风险与证据不足的对象会分别进入派工和人工队列。
2. 按本班外购热兆瓦时调低预算或增加预留。查看每个片区的已用数量及待分派原因，核对保护资源。
3. 确认派工窗口后发布。相同预览再次提交会返回原版，旧版请求遇到其他派工已发布时须重算。
4. 从 `/api/ledger` 查询版号，按摘要获取完整快照或下载 CSV 与现场票据复核。

本班主要动作是「编制峰段申报」。锁定已确认的储热和热源保证量，拆分保供与可中断补量。
数据含模拟异常，缺少可见证据或排班资源时如实返回等待或转人工。

## 寒潮班次处置

1. 先看 `drift.cold_wave`：`detected=true` 表示历史样本偏暖、模型可能低估，发布就绪会降为复核。
2. 逐单核对 `nomination_policy`：`evidence` 为 `local` 表示本片区误差带可用，`analog` 为外片区补证，`insufficient` 为证据不足。
3. `band_crosses_minimum=true` 或 `held_units>0` 的单据，只申报 `confirmed_units`，缓报量在原因中注明，不得自行补足。
4. 外片区补证只在 `analog_evidence.status=supported` 时可定量；`weak`、`no_analog` 仅留档，未建档片区不会生成本地标签证据。
5. 可中断合同全停时在 `POST /api/scenario` 或 CLI 加 `interruptible_off`，保供下限照常、可中断补量全部缓报。
6. `cover_ledger` 核对储热与热源保证量的跨单据占用，出现 `*_duplicate` 正数说明有重复抵扣被拦截。
7. 用 `shift_replay` 按决策时点回放：迟到实测只出现在后续班次，当班 `nominated_quantity` 不被改写。
