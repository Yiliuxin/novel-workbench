# 笔尖 AI 小说生成工作台 · 测试项目

基于真实项目 **Novel Workbench**（Spring Boot + React 的 AI 小说写作平台）设计的测试工程，
用于面试测试开发岗时展示「测试设计 + 自动化 + 安全/数据质量专项」能力。

## 目录结构

```
novel-workbench-test/
├── client.py                      # 零依赖 API 客户端（urllib 封装，统一响应/断言约定）
├── conftest.py                    # pytest 夹具：用户/作品/双用户隔离上下文
├── pytest.ini                     # pytest 配置（输出自包含 HTML 报告）
├── 测试用例设计.md                 # 测试策略 + 7 大模块详细用例表 + 缺陷示例 + 度量
├── 简历项目经验.md                 # 可直接粘贴进简历的项目经验文案
└── tests/
    ├── test_auth_api.py           # 模块A 认证与参数校验（11 用例）
    ├── test_book_api.py           # 模块B 作品 CRUD（7 用例）
    ├── test_permission_security.py# 模块S 安全/越权/角色矩阵（9 用例）
    ├── test_outline_ai.py         # 模块O 大纲与 AI 专项（6 用例）
    ├── test_data_quality.py       # 模块D 数据质量（6 用例，含 4 组参数化）
    ├── test_performance.py        # 模块P 性能与并发（4 用例）
    └── ui/
        └── test_ui_flows.py       # 模块U Web UI 端到端（Playwright，8 场景）
```

## 运行前提

1. 后端 Novel Workbench 已在 `http://localhost:8081` 启动（依赖本地 MySQL）。
2. 前端 vite 开发服务器已在 `http://localhost:5174` 启动（带 `/api` 代理到 8081）——仅 UI 用例需要。
3. 安装测试依赖：
   ```bash
   pip install pytest pytest-html playwright
   playwright install chromium          # 浏览器二进制；若默认路径有锁，可设 PLAYWRIGHT_BROWSERS_PATH 指向自定义目录
   ```

## 运行

```bash
cd novel-workbench-test
# 接口 / 安全 / 数据质量 / AI / 性能（需后端 8081 + MySQL）
pytest --html=report.html --self-contained-html
# UI 端到端（需额外启动 vite 5174）
pytest tests/ui/test_ui_flows.py --html=ui_report.html --self-contained-html
```

- 无 LLM Key 时系统走 mock 兜底：AI 生成接口每调用落 1 个节点、数量被钳制在 [1,10]，AI 专项用例验证**结构约束**（节点类型/父子归属/卷号接续/归属本书）；内容级一致性需配置 LLM Key 后验证。
- 接口/安全/数据质量/AI/性能共 **48 条用例已在本机实跑通过（48/48）**，报告见 `report.html`；UI 端到端 8 场景已在本机实跑通过（**8/8，13s**，Playwright，覆盖登录/注册/建书/大纲/协作），报告见 `ui_report.html`。
- **UI 用例已针对 antd 中文间距加固**：antd 会在相邻中文字符间插入空格（如「创建账号」→「创 建 账 号」），原精确文本定位会失配；现统一用「容忍空格的正则匹配」（`_btn`/`_txt`/`text=/.../`）定位，从根上消除误报。已在本机三服务齐跑环境实跑验证通过（8/8）。
- **UI 实跑说明**：浏览器自动化在本机被标记为敏感操作，需在本机执行并人工批准。运行前请确认三服务已起，并指定 Chromium 自定义路径（本机装在 `C:/Users/Yilia/pw-browsers`）：
  ```bash
  set PLAYWRIGHT_BROWSERS_PATH=C:\Users\Yilia\pw-browsers
  pytest tests/ui/test_ui_flows.py --html=ui_report.html --self-contained-html -v
  ```

## 设计亮点（面试可讲）

- **异常响应约定**：业务异常返回 HTTP 200 + body.code，断言看 code 而非状态码（易踩坑点）。
- **多租户越权（IDOR）**：以 Book 为权限主体，覆盖读/删/写越权与角色矩阵（OWNER/EDITOR/REVIEWER/VIEWER）。
- **AI 应用测试**：mock 兜底下验证节点类型/父子归属/卷号接续/数量钳制/归属本书等结构约束，内容级一致性在配 LLM Key 后专项验证。
- **数据质量**：大纲树完整性、中文/Emoji 编码保真、生成数量边界值。
- **零三方依赖**：仅用标准库，保证在任何隔离环境可直接运行。
