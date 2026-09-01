# M05本地验收报告

状态：`verified`（等待独立审核）
基线：`dbb867202b5f0380c58d32190c9b68ff944233f2`
规则提交：`af8331d`
实现提交：`4f93eb3`
影子入口与测试提交：`12c554d`

## 完成范围

- `services/selectors/`成为唯一新formal `ModelAssessment 2.x`身份生产层。
- 复杂多因子与个人形态从同一`GateEvent 2.x`和同一批`TechnicalEvidence 2.x`开始。
- 复杂多因子只整理证据引用、缺项和风险，不计算分数或排名。
- 个人形态V3专属事实使用`favorite_pattern.v3.*`身份并复用现有同一纯事实函数；共享事实不重算、不冒充。
- V1／V2和当前无需同日MACD的宽口径观察保持显式legacy只读。
- 每日与回放新增同源影子入口，默认生产入口和输出不变。

## 关键反例

- GateEvent、股票池、行情或TechnicalEvidence身份不一致失败关闭。
- 缺一项M04证据、证据批次被篡改或出现未知GateEvent失败关闭。
- legacy `ModelAssessment 1.x`不能进入formal 2.x消费者。
- 个人形态专属事实若使用共享因子ID冒充，验证失败。
- assessment身份或内容被篡改，验证失败。
- formal缺失不会自动改走legacy。
- 输出出现评分、权重、排名、市场／行业调整或交易计划字段，验证失败。

## 验收结果

- M05专项：15项通过。
- M03—M05定向：72项通过。
- 完整Python：489项通过。
- `PYTHONHASHSEED=0/1/42/12345`：每轮54项通过。
- 治理状态：19项通过。
- Python编译：通过。
- 前端lint、TypeScript、生产构建：通过。
- 前端测试：11项通过。
- `git diff --check`：通过。
- 测试前后未产生意外文件或范围外变化。

## 固定样本结论

- 新formal个人形态事实与旧V3相同固定行情样本的四项命中、阶段和风险阻断一致。
- complex判断直接引用M04证据ID；未调用M03门卫或M04因子检测器重新计算。
- 每日与回放对同一输入得到相同assessment身份和内容。

## 明确未完成

- 未合并`main`，未部署或生产启用。
- 未修改评分、排行、市场／行业、交易计划、总账或评价。
- 未修改工作流、网站、Discord、`public/`、`automation/`或生产缓存。
- M06—M10和M12均未开始。
