## 目标
将 `scc-top/_docker_ctx_scc/` 中的量化交易系统核心代码移动到 `projects/quantsys/`，使其成为独立项目。

## 分析结果

### 当前结构
```
scc-top/_docker_ctx_scc/
├── src/quantsys/          # 量化核心代码 (~120个Python文件)
├── tools/scc/             # SCC工具重复代码 (~150个文件)
├── tools/mcp_bus/         # MCP总线服务
├── tools/a2a_hub/         # A2A Hub服务
├── tools/exchange_server/ # 交易所服务器
├── tools/unified_server/  # 统一服务器
└── configs/               # 配置文件
```

### 移动范围

**需要移动的目录：**
1. `src/quantsys/` → `projects/quantsys/src/quantsys/`
2. `configs/` → `projects/quantsys/configs/`
3. `contracts/` → `projects/quantsys/contracts/`
4. `tools/mcp_bus/` → `projects/quantsys/services/mcp_bus/`
5. `tools/a2a_hub/` → `projects/quantsys/services/a2a_hub/`
6. `tools/exchange_server/` → `projects/quantsys/services/exchange_server/`

**不需要移动（SCC工具重复代码）：**
- `tools/scc/` - 与根目录 `tools/scc/` 重复
- `tools/unified_server/` - 与 `scc-top/tools/unified_server/` 重复

## 执行步骤

### Phase 1: 创建目录结构
```bash
mkdir -p projects/quantsys/{src,configs,contracts,services,docs}
```

### Phase 2: 移动核心代码
```bash
# 量化核心
mv scc-top/_docker_ctx_scc/src/quantsys projects/quantsys/src/

# 配置
mv scc-top/_docker_ctx_scc/configs projects/quantsys/

# 合约
mv scc-top/_docker_ctx_scc/contracts projects/quantsys/

# 独立服务
mv scc-top/_docker_ctx_scc/tools/mcp_bus projects/quantsys/services/
mv scc-top/_docker_ctx_scc/tools/a2a_hub projects/quantsys/services/
mv scc-top/_docker_ctx_scc/tools/exchange_server projects/quantsys/services/
```

### Phase 3: 创建项目文件

**projects/quantsys/README.md**
```markdown
# Quantsys 量化交易系统

独立的项目，包含：
- 量化交易核心引擎
- 回测系统
- 实时执行系统
- MCP总线服务
- A2A Hub服务
- 交易所服务器
```

**projects/quantsys/requirements.txt**
- 从原目录收集依赖

**projects/quantsys/setup.py**
- Python包配置

### Phase 4: 更新导入路径

需要修改的文件：
1. `services/mcp_bus/server/main.py` 中的 `quantsys` 导入
2. 配置文件中的相对路径

### Phase 5: 清理原目录
```bash
# 删除已移动的内容
rm -rf scc-top/_docker_ctx_scc/src
rm -rf scc-top/_docker_ctx_scc/configs
rm -rf scc-top/_docker_ctx_scc/contracts
rm -rf scc-top/_docker_ctx_scc/tools/mcp_bus
rm -rf scc-top/_docker_ctx_scc/tools/a2a_hub
rm -rf scc-top/_docker_ctx_scc/tools/exchange_server

# 如果 tools/scc/ 和 tools/unified_server/ 是重复的，也可以删除
rm -rf scc-top/_docker_ctx_scc/tools/scc
rm -rf scc-top/_docker_ctx_scc/tools/unified_server
```

## 预期结果

```
projects/quantsys/
├── src/quantsys/              # 量化核心 (~120文件)
├── configs/                   # 配置文件 (~30文件)
├── contracts/                 # 合约定义
├── services/
│   ├── mcp_bus/              # MCP总线
│   ├── a2a_hub/              # A2A Hub
│   └── exchange_server/      # 交易所服务器
├── docs/                      # 项目文档
├── README.md
├── requirements.txt
└── setup.py
```

## 风险与注意事项

1. **导入路径变更** - MCP总线服务依赖 `quantsys` 模块，需要更新导入
2. **配置文件路径** - 需要检查配置文件中的硬编码路径
3. **Docker构建** - 如果有Dockerfile，需要更新COPY路径
4. **测试** - 移动后需要验证服务能否正常启动

## 回滚方案

如果出现问题，可以通过git回滚：
```bash
git reset --hard HEAD
git clean -fd
```

请确认此计划后，我将开始执行。