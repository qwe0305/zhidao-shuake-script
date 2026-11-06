# 知道刷课脚本 · AI 答题版

> 基于 [VermiIIi0n/fuckZHS](https://github.com/VermiIIi0n/fuckZHS)（MIT License）改造。
> 感谢原作者的逆向分析与屎山（bushi），本仓库在其基础上做了稳定性、AI 答题、可视化与部署的增强。

## ⚠️ 免责声明

**本项目仅供学习 Python 逆向工程、网络协议分析与自动化技术使用。**

- 使用本脚本产生的**一切后果由使用者自行承担**，包括但不限于：课程成绩作废、学术不端记录、账号封禁
- 请遵守你所在学校与平台的规定。刷课属于违反学术诚信的行为
- 作者不鼓励、不支持任何形式的学术不诚信行为

## 相比原版增强了什么

| 模块 | 说明 |
|---|---|
| `ai_provider.py` | **AI 答题**：接入 DeepSeek / 通义千问 / Kimi / 智谱等大模型，修复了原版 URL 拼接 bug，支持答案缓存与宽容解析 |
| `stability.py` | **稳定性**：断网自动等待恢复、风控自动冷却重试、超时指数退避，不再一崩就全线中断 |
| `monitor.py` | **进度面板**：浏览器打开 `http://127.0.0.1:8765`，实时查看完成率、错误统计与日志流 |
| `watchdog.py` | **看护进程**：进程挂了自动拉起、卡死自动重启（当日限 3 次），跨平台可用 |
| `logger.py` | 修复：原版每次启动清空日志（连看一眼 `-h` 都会清），现改为追加 + 自动滚动 |

### 修掉的原版 bug

1. **URL 拼接错误**：`api_base` 填官方文档要求的带 `/v1` 地址时，实际请求变成 `/v1/v1/...` → 404
2. **答案解析过严**：只认一种代码块格式，模型输出稍不同就抛异常
3. **配置校验条件反了**：用智慧树 AI 反而去校验 openai key
4. **配置升级丢字段**：只合并顶层，`ai.openai` 内部新增字段在旧配置里丢失

---

## 快速开始

### 1. 安装

```bash
git clone https://github.com/<你的用户名>/fuckZHS.git
cd fuckZHS
python -m venv .venv

# Windows
.venv\Scripts\activate
pip install -r requirements.txt

# Linux / macOS
source .venv/bin/activate
pip install -r requirements.txt
```

要求 Python 3.10+。

### 2. 登录

```bash
python main.py -q --show_in_terminal
```

终端会打印二维码，用智慧树 App 扫码。目前登录只支持二维码方式。

### 3. 拉取课程清单

```bash
python main.py --fetch
```

生成 `execution.json`，删掉不想刷的课程即可。

### 4. 开刷

```bash
python main.py                # 刷清单里全部课程
python main.py -c 114514      # 只刷指定课程
python main.py -s 2.0         # 指定播放倍速
```

课程 ID 在课程页面 URL 里：校内学分课是 `courseId=`，共享学分课是 `recruitAndCourseId=`。

### 5. 看进度

```bash
python monitor.py             # 浏览器打开 http://127.0.0.1:8765
```

---

## AI 答题配置

编辑 `config.json` 的 `ai` 段：

```jsonc
"ai": {
    "enabled": true,
    "use_zhidao_ai": false,          // false = 用下面的大模型答题
    "openai": {
        "provider": "deepseek",      // 预设：deepseek / dashscope / moonshot / zhipu / siliconflow / openai
        "api_key": "sk-你的key",     // 填这里，其他字段可以不动
        "api_base": "",              // provider 预设了就不用填
        "model_name": ""             // 同上
    }
}
```

| provider | 平台 | 默认模型 | 备注 |
|---|---|---|---|
| `deepseek` | DeepSeek | `deepseek-chat` | 便宜，推荐 |
| `dashscope` | 阿里通义 | `qwen-plus` | 有免费额度 |
| `moonshot` | Kimi | `moonshot-v1-32k` | |
| `zhipu` | 智谱 | `glm-4-flash` | 免费额度大 |
| `siliconflow` | 硅基流动 | `DeepSeek-V3` | 有免费模型 |
| `openai` | OpenAI | `gpt-4o-mini` | |

**不填 key 也能用**：`use_zhidao_ai: true`（默认）走智慧树自带 AI，准确率一般但免费；key 配置无效时也会自动降级到智慧树 AI，不会中断。

答案会缓存在 `aiexamAnswer/` 目录，同一套题不会重复请求。

---

## 后台运行与看护

```bash
# 前台跑（能看到二维码和进度条）
python main.py -q --show_in_terminal

# 后台静默跑（无窗口，输出写入 logs/stdout.log）
# Windows: 用任务计划程序启动 watchdog.py 即可
python watchdog.py            # 常驻看护，每 10 分钟检查一次
python watchdog.py --once     # 单次检查（适合配合系统计划任务）
```

看护逻辑：进程挂了自动重启（当日限 3 次）、日志 90 分钟无更新判定卡死自动重启、断网时等网络恢复再拉起、发现验证码会在 `logs/watchdog.log` 提示人工处理。

---

## 打包为 exe（免 Python 环境）

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --collect-all tiktoken --collect-all openai main.py
```

产物在 `dist/main.exe`。**注意**：打包后二维码登录、配置文件读写路径以 exe 所在目录为准。

---

## 目录结构

```
fuckZHS/
├── main.py          # 命令行入口
├── fucker.py        # 核心逻辑（原版，未大改）
├── ai_provider.py   # 大模型答题接入层（新增）
├── stability.py     # 网络重试 / 风控退避（新增）
├── monitor.py       # 进度面板（新增）
├── watchdog.py      # 看护进程（新增）
├── tests/           # 离线测试（新增）
├── README_ORIGINAL.md  # 原版文档
├── config.json      # 配置（自动生成，已被 gitignore）
└── cookies.json     # 登录凭证（已被 gitignore）
```

---

## 常见问题

**Q: 提示「疑是多窗口观看」？**
同一账号出现了两条观看流。检查是否在手机 App / 浏览器同时打开了课程；频繁重启也会导致服务器端旧会话未过期，等几分钟再启动即可。新版脚本遇到它会自动冷却重试。

**Q: 提示「captcha required」？**
平台风控要求验证码，脚本无法自动通过。用浏览器登录一次智慧树完成验证，然后重启脚本。

**Q: Clash 代理导致证书错误？**
在 `config.json` 的 `proxies` 里配置代理，或直接关掉系统代理（智慧树是国内站，直连更快）。

**Q: 断网了会怎样？**
新版会自动等待网络恢复（最多 15 分钟），恢复后继续刷，不会丢失已有进度。

---

## License

MIT License（遵循原项目）。使用本项目即表示你已阅读并同意顶部的免责声明。
