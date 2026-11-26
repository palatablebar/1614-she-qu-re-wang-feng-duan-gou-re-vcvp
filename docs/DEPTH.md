# 业务模块与回归证据

AI/ML / 传统ML · 中型

## 功能模块

| 编号 | 业务模块 | 交付内容 | 核心文件 | 测试文件 |
| --- | --- | --- | --- | --- |
| M1 | `exchange_register` | 验签、换版与隔离 | `src/heatnom/exchange_register/contracts.py` `src/heatnom/exchange_register/parsing.py` `src/heatnom/exchange_register/service.py` | `tests/test_exchange_register.py` |
| M2 | `thermal_cutoff` | 按可见时点冻结样本和结果 | `src/heatnom/thermal_cutoff/contracts.py` `src/heatnom/thermal_cutoff/revisions.py` `src/heatnom/thermal_cutoff/service.py` | `tests/test_thermal_cutoff.py` |
| M3 | `degree_features` | 形成训练与当班共用的领域特征 | `src/heatnom/degree_features/contracts.py` `src/heatnom/degree_features/indicators.py` `src/heatnom/degree_features/service.py` | `tests/test_degree_features.py` |
| M4 | `intertie_demand` | 估计业务结果并输出本地归因 | `src/heatnom/intertie_demand/contracts.py` `src/heatnom/intertie_demand/estimator.py` `src/heatnom/intertie_demand/service.py` | `tests/test_intertie_demand.py` |
| M5 | `nomination_replay` | 逐窗校准并与历史基线比较 | `src/heatnom/nomination_replay/contracts.py` `src/heatnom/nomination_replay/calibration.py` `src/heatnom/nomination_replay/service.py` | `tests/test_nomination_replay.py` |
| M6 | `weather_drift` | 识别缺测、未建档与分布变动 | `src/heatnom/weather_drift/contracts.py` `src/heatnom/weather_drift/distribution.py` `src/heatnom/weather_drift/service.py` | `tests/test_weather_drift.py` |
| M7 | `heat_contracts` | 按业务规则锁定和分派资源 | `src/heatnom/heat_contracts/contracts.py` `src/heatnom/heat_contracts/domain.py` `src/heatnom/heat_contracts/service.py` | `tests/test_heat_contracts.py` |
| M8 | `grid_settlement` | 按版本发布、导出、回查与对账 | `src/heatnom/grid_settlement/contracts.py` `src/heatnom/grid_settlement/storage.py` `src/heatnom/grid_settlement/service.py` | `tests/test_grid_settlement.py` |
| M9 | `analog_evidence` | 外片区相近天气实测补证 | `src/heatnom/analog_evidence/contracts.py` `src/heatnom/analog_evidence/service.py` | `tests/test_analog_evidence.py` |
| M10 | `nomination_policy` | 本片区误差带、缓报裁决与保证量去重 | `src/heatnom/nomination_policy/contracts.py` `src/heatnom/nomination_policy/service.py` | `tests/test_nomination_policy.py` |
| M11 | `weather_drift` 寒潮判定 | 识别历史偏暖分布 | `src/heatnom/weather_drift/distribution.py` `src/heatnom/weather_drift/service.py` | `tests/test_cold_wave.py` |
| M12 | `nomination_replay` 时点回放 | 还原当班购热量、隔离迟到实测 | `src/heatnom/nomination_replay/replay_shift.py` | `tests/test_replay_shift.py` |

## 高风险边界

| 编号 | 可观察后果 | 处理位置 | 回归用例 |
| --- | --- | --- | --- |
| TRAP-14 | 同版互斥读数隔离后继续处理其他单据 | `src/heatnom/thermal_cutoff/service.py` | `tests/test_thermal_cutoff.py::test_exact_resends_and_conflicts` |
| TRAP-19 | 单据锁定优先于排队和默认动作 | `src/heatnom/heat_contracts/service.py` | `tests/test_heat_contracts.py::test_locked_cannot_book` |
| TRAP-23 | 可见日等于截止的单据属于下一个窗口 | `src/heatnom/thermal_cutoff/service.py` | `tests/test_thermal_cutoff.py::test_at_cut_is_future` |
| TRAP-26 | 陈旧发布请求保留已生效的派工版 | `src/heatnom/grid_settlement/service.py` | `tests/test_grid_settlement.py::test_stale_leaves_head` |
| TRAP-32 | 恒定训练轴避免除零和新偏移误放 | `src/heatnom/degree_features/service.py` | `tests/test_degree_features.py::test_constant_axis` |
| TRAP-42 | 未来修订绝不替换前序训练证据 | `src/heatnom/thermal_cutoff/service.py` | `tests/test_thermal_cutoff.py::test_late_revision_cannot_revise_past` |
| TRAP-43 | 回放没有正例时说明指标不可定义 | `src/heatnom/nomination_replay/service.py` | `tests/test_nomination_replay.py::test_no_positive_average_precision` |
| TRAP-44 | 未建档片区会拒识，异常流量高时禁止发布 | `src/heatnom/weather_drift/service.py` | `tests/test_weather_drift.py::test_unseen_blocks_when_majority` |
| TRAP-53 | 批中相邻样本不改变单条评分 | `src/heatnom/intertie_demand/service.py` | `tests/test_intertie_demand.py::test_point_invariance` |
| TRAP-54 | 账簿参数变化会改变模型摘要并重算 | `src/heatnom/intertie_demand/service.py` | `tests/test_intertie_demand.py::test_fitted_signature_tracks_source` |
| TRAP-61 | 外片区旁证样本不足或片区单一时只能留档不能定量 | `src/heatnom/analog_evidence/service.py` | `tests/test_analog_evidence.py::test_supported_analog_requires_enough_cases_and_two_donor_regions` |
| TRAP-62 | 误差带跨过最小申报量时只保下限、差额缓报 | `src/heatnom/nomination_policy/service.py` | `tests/test_nomination_policy.py::test_band_crossing_minimum_holds_the_uncertain_top_slice` |
| TRAP-63 | 可中断合同全停仍兑现保供、可中断量全缓 | `src/heatnom/nomination_policy/service.py` | `tests/test_nomination_policy.py::test_interruptible_shutdown_keeps_firm_minimum_but_holds_flexible_volume` |
| TRAP-64 | 储热与热源保证量跨单据各只占一次 | `src/heatnom/nomination_policy/service.py` | `tests/test_nomination_policy.py::test_cover_ledger_counts_each_guarantee_pool_only_once` |
| TRAP-65 | 迟到实测不改变当班回放购热量 | `src/heatnom/nomination_replay/replay_shift.py` | `tests/test_replay_shift.py::test_late_actuals_are_hidden_from_current_shift` |
