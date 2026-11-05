# PetPilot（宠物合伙人 MVP）

猫主人的 Personal Agent：用一句话 / 照片 / 语音记录猫的日常，自动分猫归档、纠错带版本来源、设提醒、生成就医准备摘要。

## 当前进度

阶段 2-3（周回顾 + 收口）开发完成。详细进度见 `docs/项目状态.md`。

## 启动方法（本机）

后端（端口 8001）：

```bash
cd backend && bash run.sh
```

前端（Vite，默认 5173，被占用会提示 5174 等）：

```bash
cd frontend && npm install && npm run dev
```

浏览器打开前端地址（如 http://localhost:5174/），验证码 `123456`。

前端功能：对话记录、纠错、提醒、就医摘要、周回顾、挂起补归属；照片通过聊天输入「＋」随消息发送（拍照/相册，最多 5 张）；底部麦克风「按住说话」转文字（浏览器识别，不支持时回退打字）。

## 验证方法

```bash
# 后端 mock 测试
cd backend && source .venv/bin/activate && MODEL_API_KEY="" python -m pytest -q

# 前端测试 / lint / 构建
cd frontend && npm test -- --run && npm run lint && npm run build

# 全套自检（在工具包根目录）
./verify.sh PetPilot 阶段3-1
```

## 环境变量（backend/.env，从 .env.example 复制）

| 变量 | 说明 |
| --- | --- |
| MODEL_BASE_URL | DeepSeek 接口地址，默认 https://api.deepseek.com |
| MODEL_NAME | 模型名，默认 deepseek-chat |
| MODEL_API_KEY | DeepSeek API Key（真实模型验收时才需要，留空走 mock） |
| FIXED_LOGIN_CODE | 固定验证码，默认 123456（仅合成体验空间） |
| DATABASE_URL | SQLite 路径，默认 sqlite:///./data/petpilot.db |
