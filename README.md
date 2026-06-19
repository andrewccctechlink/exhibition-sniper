# Exhibition Lead Sniper

展會名片掃描 → AI 分析 → 自動生成 Cold Email + Pitch Deck

## 功能

1. **名片 OCR** — Gemini Vision 掃描名片，提取姓名、公司、Email、電話
2. **公司 Enrichment** — Google Maps + Hunter.io + Snov.io + 網站爬取
3. **海關數據匹配** — 本地 Excel 搜索進出口記錄
4. **AI 寫 Email** — DeepSeek 生成 3 封個性化冷郵件
5. **Pitch Deck** — 自動生成 Morandi 風格 PowerPoint

## 部署

### Zeabur（推薦）

1. Push 到 GitHub
2. Zeabur → Import from GitHub → 自動識別 Python + Procfile
3. 設定環境變數（見下方）
4. 完成！

### 環境變數

| 變數 | 必填 | 說明 |
|------|------|------|
| `GEMINI_API_KEY` | ✅ | Google Gemini API Key（OCR + Pitch Deck） |
| `DEEPSEEK_API_KEY` | ✅ | DeepSeek API Key（寫 Email） |
| `HUNTER_API_KEY` | 選填 | Hunter.io（找 Decision Makers） |
| `SNOV_USER_ID` | 選填 | Snov.io User ID |
| `SNOV_SECRET` | 選填 | Snov.io Secret |
| `GOOGLE_MAPS_KEY` | 選填 | Google Maps Places API |
| `PORT` | 自動 | Zeabur 自動設定 |

### 本地開發

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=your_key
export DEEPSEEK_API_KEY=your_key
python server.py
```

## 結構

```
exhibition-sniper/
├── server.py           ← 主程式（Flask，一個 file 搞掂）
├── services/
│   ├── gemini.py       ← OCR + Pitch deck AI
│   ├── deepseek.py     ← Email 生成
│   └── enrichment.py   ← 公司資料搜集
├── local_customs.py    ← 海關數據讀取
├── pitch_deck.py       ← PowerPoint 生成
├── templates/
│   ├── index.html      ← 主介面
│   └── login.html      ← 登入頁
├── static/
│   └── app.js          ← 前端邏輯
├── database/           ← SQLite + 海關 Excel
├── storage/            ← 生成的 Pitch Deck 檔案
├── requirements.txt
├── Procfile
└── Dockerfile
```
