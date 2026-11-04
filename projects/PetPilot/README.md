# PetPilot（宠物合伙人 MVP）

猫主人的 Personal Agent：用一句话 / 照片 / 语音记录猫的日常，自动分猫归档、纠错带版本来源、设提醒、生成就医准备摘要。

## 当前进度

阶段 2-1（后端地基 + 文字记录核心闭环）。详细进度见 `docs/项目状态.md`，范围见 `docs/阶段文档/阶段2-1技术开发文档.md`。

## 启动方法（本机，一条命令）

```bash
# 首次：装依赖（Python 3.12）
cd backend
/Users/liang/.local/bin/python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 每次启动：迁移数据库 + 起服务
bash backend/run.sh
```

打开浏览器访问 `http://localhost:8001/`，验证码固定 `123456`。（端口 8000 被其他项目占用，PetPilot 默认用 8001，可用 `PORT=xxxx` 环境变量覆盖）

## 验证方法

```bash
# mock 自动化测试（离线，不调真实模型）
cd backend && source .venv/bin/activate
MODEL_API_KEY="" python -m pytest -q

# 重启数据恢复检查
bash scripts/restart-check.sh

# 全套自检（在工具包根目录）
./verify.sh PetPilot 阶段2-1
```

## 环境变量（backend/.env，从 .env.example 复制）

| 变量 | 说明 |
| --- | --- |
| MODEL_BASE_URL | DeepSeek 接口地址，默认 https://api.deepseek.com |
| MODEL_NAME | 模型名，默认 deepseek-chat |
| MODEL_API_KEY | DeepSeek API Key（真实模型验收时才需要，留空走 mock） |
| FIXED_LOGIN_CODE | 固定验证码，默认 123456（仅合成体验空间） |
| DATABASE_URL | SQLite 路径，默认 sqlite:///./data/petpilot.db |
