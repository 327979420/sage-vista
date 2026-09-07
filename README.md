# Sage Vista

个人美股技术研究与日终选股工具：查看候选及依据，结合大盘与行业背景，持续追踪和验证交易经验。项目不自动下单，不把匹配分数当作收益概率。

生产站点：<https://sage-vista-parallel.gizmo-allied-0s.workers.dev>。实际数据日和部署状态需核验，不能以本地版本代替。

## 文档入口

- [当前状态](docs/CURRENT_STATUS_ZH.md)：日期、版本、回测断点及机器来源。
- [产品与模块地图](docs/SAGE_VISTA_RULEBOOK_ZH.md)：项目做什么；按需进入具体业务规则。
- [执行与文档维护](docs/rules/01_GOVERNANCE.md)：唯一工作流程。Codex 从 [AGENTS.md](AGENTS.md) 接手。

定位实现时查 [代码地图](docs/CODEBASE_MAP_ZH.md)；任务进度查 [需求账本](docs/CHANGE_REQUESTS_ZH.md) 对应条目。历史设计与案例按需查阅；早期产品规格合并到 [产品历史](docs/archive/product-history.md)，已完成验收合并到 [验收历史](docs/archive/acceptance-history.md)。[研究记录](research/README.md) 保留原路径，不是日常接手清单。

动态因子数量、参数和状态不在 README 重复维护。文档目录不是待完成任务清单，旧设计不自动成为当前要求。

## 本地运行

```bash
npm install
npm run dev
```

## 验证入口

```bash
python3 -m unittest discover -s tests
npm test
```

按影响范围选择必要检查；以上是完整检查入口，并非每次文档或局部修改都要执行。
