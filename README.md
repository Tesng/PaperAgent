# PaperAgent — 論文講義網站

把論文 PDF 丟進資料夾，agent 會整理成中文講義，用網頁瀏覽。

每份講義回答五件事：

| # | 問題 |
|---|---|
| 0 | **問題**：它要解決什麼？之前的方法缺了什麼？ |
| 1 | **核心想法**：能用一句話講出它的關鍵招數 |
| 2 | **資料流**：輸入、輸出、中間經過哪些模組（附論文原圖） |
| 3 | **怎麼訓練**：用什麼資料、什麼 loss |
| 4 | **證據與位置**：最能支持主張的實驗，以及它和前後篇的關係 |

## 使用方式

1. 把 PDF 放進 `papers/`（檔名隨意）。
2. 在這個資料夾開啟 Claude（Cowork 或 Claude Code），說：**「整理新論文」**。
   Agent 會依照 `AGENT.md` 的流程：讀全文 → 擷取架構圖與關鍵實驗圖 → 寫 `notes/<slug>.md` → 更新 `data/papers.json`。
3. 預覽網站：
   ```bash
   cd PaperAgent
   python3 -m http.server 8000
   ```
   打開 <http://localhost:8000>。（直接雙擊 `index.html` 會因瀏覽器安全限制讀不到講義。）

其他指令：「整理 `xxx.pdf`」、「重寫 `<slug>`」、「更新關聯」、「重建索引」，詳見 `AGENT.md` §2。

## 網站功能

- 論文卡片列表：架構圖縮圖、一句話核心想法、標籤；可搜尋（含講義全文）、依標籤篩選、排序。
- 講義頁：五個問題各有顏色、側邊目錄、公式（KaTeX）、點圖放大、「改良自 → 本篇 → 被延伸」脈絡連結、列印成 PDF。
- 自動深色模式（右上角可切換）。

## 部署到 GitHub Pages

1. 把整個資料夾推到一個 GitHub repo。
2. Settings → Pages → Source 選 **Deploy from a branch**，Branch 選 `main`、資料夾 `/ (root)`。
3. 幾分鐘後即可在 `https://<帳號>.github.io/<repo>/` 瀏覽。

> 根目錄的 `.nojekyll` 不能刪：GitHub Pages 預設會用 Jekyll 把有 frontmatter 的 `.md` 轉成 HTML，網站就讀不到講義原檔。

> 公開網站時要注意論文 PDF 與截圖的版權。不想上傳 PDF 的話，取消 `.gitignore` 裡 `papers/*.pdf` 那行的註解。

## 資料夾

```
papers/            放論文 PDF
notes/             講義（Markdown）
assets/figures/    從論文擷取的原圖
data/papers.json   網站索引（由腳本產生）
templates/         講義模板
scripts/           paper_tools.py：PDF 讀取、擷圖、檢查、建索引
work/              暫存區（可刪）
```

## 工具指令（agent 會自己用，你也可以手動跑）

```bash
pip install -r requirements.txt                       # 安裝 PyMuPDF
python3 scripts/paper_tools.py pending                 # 還沒整理的 PDF
python3 scripts/paper_tools.py text    <pdf> --slug <slug>   # 抽全文
python3 scripts/paper_tools.py figures <pdf> --slug <slug>   # 自動擷取候選圖
python3 scripts/paper_tools.py crop    <pdf> --page 3 --rect 0.1,0.05,0.9,0.4 --out <png>
python3 scripts/paper_tools.py new     <slug> --pdf <pdf>    # 從模板建立講義
python3 scripts/paper_tools.py check   [<slug>]              # 檢查講義
python3 scripts/paper_tools.py index                         # 重建網站索引
```
