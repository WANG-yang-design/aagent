# 部署说明

## 架构

```
Vercel（前端 React）  ←─ HTTPS API ─→  Railway/Render（后端 FastAPI）
```

---

## 一、后端部署（Railway 推荐）

### 1. 推送代码到 GitHub

```bash
git init
git add .
git commit -m "initial"
git remote add origin https://github.com/你的账号/aagent.git
git push -u origin main
```

### 2. 在 Railway 创建项目

1. 访问 [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. 选择你的仓库
3. 设置环境变量：

| 变量 | 值 |
|------|-----|
| `SECRET_KEY` | 随机32位字符串（重要！） |
| `CORS_ORIGINS` | 你的 Vercel 前端域名，如 `https://aagent.vercel.app` |
| `AI_API_KEY` | （可选，作为全局默认） |

4. Railway 会自动读取 `Procfile` 启动后端

### 3. 记录后端 URL

Railway 部署后会给你一个 URL，如：`https://aagent-production.up.railway.app`

---

## 二、前端部署（Vercel）

### 1. 在 Vercel 导入项目

1. 访问 [vercel.com](https://vercel.com) → New Project → Import Git Repository
2. **Root Directory** 填写：`frontend`
3. Framework Preset 选择：**Vite**

### 2. 设置环境变量

| 变量 | 值 |
|------|-----|
| `VITE_API_URL` | 你的 Railway 后端 URL，如 `https://aagent-production.up.railway.app` |

### 3. 点击 Deploy

Vercel 会自动构建 React 应用并发布。

---

## 三、本地开发

```bash
# 启动后端
pip install -r requirements.txt
python app.py

# 启动前端（新终端）
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173
```

---

## 四、用户使用流程

1. 打开网站 → 注册账号
2. 进入「设置」→ 填写自己的大模型 API Key 和邮箱配置
3. 进入「行情」→ 搜索股票 → AI 分析
4. 点击「加入持仓」→ 填写买入价格和数量
5. 进入「持仓」→ 查看盈亏 → 点击「卖出」结算
