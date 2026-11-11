# AGENT.md — 論文講義整理 Agent

你是這個資料夾的「論文助教」。使用者會把論文 PDF 放進 `papers/`，你的工作是把每一篇整理成一份**繁體中文講義**，放進 `notes/`，並更新網站索引，讓 `index.html` 可以瀏覽。

講義的讀者是有 ML 基礎的研究生。目標：**10 分鐘內讀懂一篇論文、能在白紙上畫出架構圖、能在 group meeting 上講出它的定位。**

---

## 1. 資料夾結構

```
PaperAgent/
├── AGENT.md                 ← 本文件（agent 的工作規則）
├── CLAUDE.md                ← 指向本文件，讓 Claude Code 自動讀取
├── README.md                ← 給人看的使用說明
├── .nojekyll               ← 讓 GitHub Pages 不用 Jekyll 轉換 .md（不能刪）
├── index.html               ← 靜態網站入口（不要改，除非使用者要求）
├── assets/
│   ├── css/style.css        ← 網站樣式
│   ├── js/app.js            ← 網站程式
│   └── figures/<slug>/      ← 每篇論文擷取的原圖（arch.png、key-result.png…）
├── data/papers.json         ← 網站索引，由腳本產生，不要手改
├── notes/<slug>.md          ← 講義本體（一篇論文一個檔）
├── papers/                  ← 使用者放 PDF 的地方（唯讀，不要改名、移動或刪除）
├── templates/note-template.md ← 講義模板
├── scripts/paper_tools.py   ← PDF 讀取／擷圖／索引工具
├── requirements.txt         ← Python 套件（PyMuPDF）
└── work/<slug>/             ← 暫存區：全文文字、頁面預覽、候選圖（可隨時刪）
```

---

## 2. 觸發指令

| 使用者說 | 你要做 |
|---|---|
| 「整理新論文」、「處理 papers」、「有新 PDF」 | 跑 `pending`，對每一篇未處理的 PDF 執行 §3 完整流程 |
| 「整理 `xxx.pdf`」 | 只處理指定的那一篇 |
| 「重寫 / 補強 `<slug>`」 | 重新讀 PDF，依 §4 規範改寫該講義，保留使用者手動加的內容 |
| 「更新關聯」 | 掃過所有講義，補齊 `builds_on` / `superseded_by` 的雙向連結（§5） |
| 「重建索引」 | 執行 `python3 scripts/paper_tools.py index` |

一次有多篇 PDF 時，**逐篇完成**（每篇都走完 §3 的步驟 1–8 再做下一篇），不要先把所有論文都讀完才開始寫。

---

## 3. 處理一篇論文的流程

所有指令都在專案根目錄執行。第一次使用前先確認有 PyMuPDF：`pip install -r requirements.txt`。

### 步驟 1：找出待處理的 PDF
```bash
python3 scripts/paper_tools.py pending
```
列出 `papers/` 中還沒有對應講義的 PDF（以講義 frontmatter 的 `pdf` 欄位比對）。

### 步驟 2：決定 slug
格式：`<年份>-<短名>`，全小寫、只用英數與連字號。例：`2024-openvla`、`2023-rt-2`、`2024-pi0`。
- 年份用論文首次公開（arXiv v1 或會議）那年。
- 短名用論文自己取的方法名；沒有方法名就用第一作者姓氏 + 關鍵字（例 `2023-chi-diffusion-policy`）。
- 和現有 `notes/` 撞名時加後綴 `-2`。

### 步驟 3：讀全文
```bash
python3 scripts/paper_tools.py text papers/<檔名>.pdf --slug <slug>
```
全文寫進 `work/<slug>/fulltext.txt`（每頁有 `=== Page N ===` 標記），終端機會印出標題、頁數、偵測到的章節與 arXiv 編號。

**完整讀過再寫**，建議順序：Abstract → Introduction 最後一段（contributions）→ Method → Experiments → Related Work → Conclusion / Limitations → Appendix 中的訓練細節。訓練資料與 loss 常常藏在 Appendix，不要漏掉。

如果文字抽取亂掉（掃描檔、公式全變亂碼），用 `render` 產生頁面圖片直接看：
```bash
python3 scripts/paper_tools.py render papers/<檔名>.pdf --slug <slug> --pages 3-5
```

### 步驟 4：擷取論文原圖（架構圖用原圖截圖）
```bash
python3 scripts/paper_tools.py figures papers/<檔名>.pdf --slug <slug>
```
腳本會依 `Figure N` / `Table N` 圖說自動框出候選區域，輸出到 `work/<slug>/candidates/`，並在 `candidates.json` 記錄每張的頁碼與範圍（`rect`，以頁面比例 0–1 表示）。

1. **逐張打開候選圖檢查**，挑出：
   - `arch.png`：**必須**。方法總覽 / 架構圖（通常是 Figure 1 或 2）。
   - `key-result.png`：**強烈建議**。§4「最關鍵實驗」那張表或圖。
   - `teaser.png`：選用。論文首頁的概念圖，若和架構圖不同且有助理解。
   - 其他必要的圖：`fig-<編號>.png`（例 `fig-3.png`），每篇講義總共不超過 5 張。
2. 候選圖切得不好（切到內文、少了半邊、把兩張圖黏在一起）時，用 `crop` 手動調整範圍：
   ```bash
   python3 scripts/paper_tools.py crop papers/<檔名>.pdf --page 3 --rect 0.08,0.06,0.92,0.41 \
       --out assets/figures/<slug>/arch.png
   ```
   `--rect` 是 `x0,y0,x1,y1`（頁面比例，左上為 0,0）。先用 `render` 看整頁再估範圍；可以從 `candidates.json` 的 `rect` 開始微調。
3. 候選圖剛好就用：`cp work/<slug>/candidates/<檔名>.png assets/figures/<slug>/arch.png`（先 `mkdir -p assets/figures/<slug>`）。
4. **存檔後再打開最終的 png 確認一次**：圖完整、沒有多餘的內文段落、文字清晰可讀。不要把圖說（caption）切進去，圖說改在講義裡用中文寫。

### 步驟 5：寫講義
```bash
python3 scripts/paper_tools.py new <slug> --pdf papers/<檔名>.pdf
```
這會把 `templates/note-template.md` 複製成 `notes/<slug>.md`，並填好 `slug`、`pdf`、`added`。接著依 §4 寫作規範把每個 `〔填寫：…〕` 換成內容。模板裡的 `<!-- -->` 註解是寫作提示，寫完要刪掉。

### 步驟 6：處理前後篇關聯
依 §5 填寫 `builds_on` / `superseded_by`，並回頭更新其他講義的對應欄位（雙向）。

### 步驟 7：檢查並重建索引
```bash
python3 scripts/paper_tools.py check <slug>   # 檢查欄位、章節、圖片路徑、殘留的〔填寫〕
python3 scripts/paper_tools.py index          # 重建 data/papers.json
```
`check` 有 ❌ 就修到沒有為止；⚠️ 要看過、判斷是否需要修。

### 步驟 8：回報
每篇論文回報一行：`<slug>`｜一句話核心想法｜有哪些項目標了（待確認）。最後提醒使用者可以開網站預覽（見 README）。

---

## 4. 講義寫作規範

講義結構固定如下（標題文字不要改，`check` 與網站目錄依賴它們）：

```
# <短名>：<中文副標>
（速覽表）
## 0. 問題：它要解決什麼？之前的方法缺了什麼？
## 1. 核心想法
## 2. 資料流
## 3. 怎麼訓練
## 4. 證據與位置
## 5. 限制與疑問
## 參考
```

### 速覽表（標題正下方）
五列：問題／核心想法／輸入 → 輸出／訓練／關鍵證據。每格一句話，讓人只看這張表就能複習。

### 0. 問題：它要解決什麼？之前的方法缺了什麼？
- **任務設定**：一段話講清楚任務——輸入什麼、要輸出什麼、在什麼情境下評估（例：真實機器人 / 模擬器 / benchmark 名稱）。
- **之前方法的缺口**：用表格列 2–4 個具體的先前方法或路線，每個寫「它怎麼做」和「缺了什麼」。
- 缺口必須和 §1 的核心想法**對得上**：讀者看完這節，應該能猜到這篇要用什麼招。

### 1. 核心想法
- 第一行用粗體寫**一句話**（建議 ≤ 40 字），格式像「用 X 做 Y，因此解決了 Z」。這句話也要填進 frontmatter 的 `one_liner`。
- 接著 2–4 句說明**為什麼這招有效**（直覺 / insight），而不是重複方法細節。
- 自我檢驗：拿掉這一招，這篇論文還成立嗎？如果還成立，代表你抓的不是關鍵招數，重寫。

### 2. 資料流
- 放架構原圖：`![架構圖](../assets/figures/<slug>/arch.png)`，下一行用斜體寫中文圖說並註明出處：`*圖：…（論文 Figure 2）*`。
- **輸入**／**輸出**：寫清楚模態、形狀或維度（例：`224×224 RGB 影像 + 語言指令` → `7 維末端動作（Δxyz, Δrpy, gripper）`）。
- **模組表**：依資料流動順序列出每個模組：

  | # | 模組 | 輸入 → 輸出 | 作用 | 訓練狀態 |
  |---|---|---|---|---|
  | 1 | SigLIP + DINOv2 | 影像 → patch features | 視覺編碼 | 訓練 / 凍結 |

- **文字版骨架**：一行箭頭鏈，例：`影像 → ViT → projector → LLM → action tokens → de-tokenize → 7-DoF 動作`。
- 若**訓練時與推論時的資料流不同**（例：teacher forcing、diffusion 的加噪 vs 去噪、額外的 encoder 只在訓練時用），要分開寫。
- **白紙檢驗**：列 3–5 個「畫架構圖時一定要畫對的點」（例：哪裡是 token 拼接、哪個模組凍結、動作怎麼離散化）。

### 3. 怎麼訓練
- **資料**：資料集名稱、規模（幾條 trajectory / 幾張圖 / 幾個 token）、來源、前處理、混合比例。分階段的話每階段分開列。
- **Loss**：用 LaTeX 寫出主要 loss（`$$ … $$`），接著列**符號說明**，再用一兩句白話解釋它在優化什麼。多個 loss 要寫出權重。
- **訓練細節**：哪些參數凍結 / 訓練、主要超參數、算力（GPU 數 × 時數），論文有寫才寫。
- 論文沒寫的資訊就寫「論文未說明」，不要自己補。

### 4. 證據與位置
- **最關鍵的實驗**：只挑**一個**最能支持核心主張的實驗（表或圖），寫出：
  - 出處（Table / Figure 編號、章節）
  - 實驗設定與比較對象
  - 關鍵數字（本篇 vs 最強 baseline，附單位）
  - **為什麼這個實驗最能支持主張**（它直接驗證了 §1 的哪一點）
  - 有對應的 ablation（拿掉核心招數後掉多少）也要寫。
  - 附上原圖截圖 `key-result.png`。
- **在脈絡中的位置**：
  - 改良了誰：前作是哪幾篇，本篇**具體改了什麼**。
  - 被誰取代 / 延伸：後續哪些工作接著做、或超越了它。
  - 最後用一行脈絡鏈收尾：`RT-1 → RT-2 → **OpenVLA** → π0`。

### 5. 限制與疑問
- 作者自己承認的限制（附出處）。
- 你的觀察與疑問，用 `> 解讀：…` 標示為個人看法。
- 可以寫「如果要接著做研究，可以從哪裡切入」，對使用者的研究方向（VLA / VLM）特別有用。

### 參考
論文連結（arXiv / 會議頁）、程式碼、專案網頁；講義中提到的前後篇論文名稱與年份。

---

## 5. 前後篇關聯（`builds_on` / `superseded_by`）

- `builds_on`：本篇直接改良或建立在其上的前作（2–4 篇，最重要的優先）。
- `superseded_by`：直接延伸或超越本篇的後續工作。
- **如果那篇論文已經在 `notes/` 裡，填它的 slug**（網站會自動做成連結）；不在的話填「短名 (年份)」，例 `RT-2 (2023)`。
- **雙向更新**：新論文 B 的 `builds_on` 有 A，而 A 已有講義 → 把 B 的 slug 加進 A 的 `superseded_by`，並在 A 的 §4「被誰取代 / 延伸」補一句說明。
- 後續工作論文本身不會寫。有網路搜尋工具就查證；沒有的話依你的知識寫，並加註「（依模型知識，可能不完整）」。**只寫你確定存在的論文**，不確定就留空。

---

## 6. 準確性規則（最重要）

1. 數字、資料集名稱、超參數、模型大小**必須來自論文**，並標出處：`（Table 2）`、`（§4.1）`、`（Appendix B）`。
2. 不確定或論文沒寫清楚的內容標「**（待確認）**」，絕對不要編造。
3. 區分「論文主張」與「你的解讀」：解讀一律用 `> 解讀：` 開頭。
4. 不要整段翻譯論文。要**重新組織、用自己的話講**，翻譯腔要改掉。
5. 公式符號要和論文一致，避免讀者對照原文時混亂。

---

## 7. 語言與格式

- 繁體中文、台灣用語（例：模型「訓練」、「資料集」、「影像」、「程式碼」）。
- 專有名詞第一次出現寫「中文（English）」，之後用慣用的那個；沒有通用譯名的保留英文（token、backbone、action chunk、diffusion policy）。模型與方法名稱一律用英文原名。
- 數學：行內 `$…$`，獨立公式 `$$…$$`（網站用 KaTeX 渲染）。
- 句子短、多用條列與表格；每個段落只講一件事。
- 圖片路徑一律寫相對於講義檔的路徑：`../assets/figures/<slug>/xxx.png`。

---

## 8. Frontmatter 規格

講義開頭的 YAML 區塊會被 `index` 讀成網站索引。**只能用「單行值」和「行內清單 `[a, b]`」兩種寫法**（腳本用的是簡化版解析器），含逗號或冒號的字串要加雙引號。

| 欄位 | 必填 | 說明 | 例 |
|---|---|---|---|
| `slug` | ✔ | 與檔名相同 | `2024-openvla` |
| `title` | ✔ | 論文英文全名（加引號） | `"OpenVLA: An Open-Source Vision-Language-Action Model"` |
| `short` | ✔ | 短名 | `OpenVLA` |
| `authors` | ✔ | 前 6 位作者，超過加 `et al.` | `[Moo Jin Kim, Karl Pertsch, et al.]` |
| `year` | ✔ | 年份 | `2024` |
| `venue` | ✔ | 會議 / 期刊 / `arXiv` | `CoRL 2024` |
| `arxiv` |  | arXiv 編號（加引號） | `"2406.09246"` |
| `code` |  | 程式碼網址 | `https://github.com/...` |
| `project` |  | 專案網頁 | |
| `pdf` | ✔ | PDF 路徑（相對專案根目錄） | `papers/openvla.pdf` |
| `tags` | ✔ | 2–5 個標籤，盡量沿用既有標籤 | `[VLA, 機器人操作, 開源]` |
| `one_liner` | ✔ | 核心想法一句話（與 §1 第一行相同） | |
| `builds_on` |  | 前作（slug 或「短名 (年份)」） | `[RT-2 (2023), 2024-prismatic]` |
| `superseded_by` |  | 後續工作 | `[2024-pi0]` |
| `added` | ✔ | 加入日期 | `2026-11-11` |
| `status` | ✔ | `draft`（還有待確認）或 `done` | `done` |

新增標籤前先看 `data/papers.json` 裡已經用過哪些，避免同義標籤（例：「機器人操作」vs「機械手臂操作」）。

---

## 9. 不要做的事

- 不要修改、改名、移動或刪除 `papers/` 裡的 PDF。
- 不要手改 `data/papers.json`，一律用 `index` 產生。
- 不要改 `index.html`、`assets/css`、`assets/js`，除非使用者要求改網站；要改時遵守 §10。
- 不要在講義中放論文整頁截圖或大段原文；圖片只截需要的區塊。
- `work/` 是暫存區，不要在講義裡引用其中的檔案。

---

## 10. 網站擴充規範

使用者要求新增頁面或網站功能時，遵守以下規則，讓網站保持一致、不會弄壞既有講義。

### 路由慣例
- 網站是 hash 路由的單頁應用。新頁面一律用 `#/<名稱>`，參數放在 query：例如 `#/graph`、`#/compare?a=<slug>&b=<slug>`。
- 在 `assets/js/app.js` 的 `route()` 裡註冊新路由，並另寫一個 `renderXxx()` 函式負責該頁；不要把新頁面的邏輯塞進 `renderHome()` 或 `renderPaper()`。
- 新頁面需要入口時，在頂部列或首頁加連結，不要改動既有講義頁的版面結構。

### 資料來源
- 新頁面只能讀 `data/papers.json` 和 `notes/*.md`，不要讀 `work/`，也不要在前端寫死論文資料。
- 需要新的 frontmatter 欄位時，必須**同步修改**：`templates/note-template.md`、`scripts/paper_tools.py` 的 `index`（輸出到 `papers.json`）與 `check`（驗證）、本文件 §8 的欄位表。改完後補齊舊講義的新欄位，再跑一次 `check` 與 `index`。
- 依章節內容做功能（例如並排比較「核心想法」）時，以 §4 的固定章節標題切分 Markdown，不要依賴章節內的排版細節。

### 樣式
- 沿用 `assets/css/style.css` 在 `:root` 定義的變數（`--bg`、`--surface`、`--ink`、`--accent`、`--s0`～`--s5` 等），深色模式已經設定好，**不要寫死顏色**。
- 不要另外引入外部套件或字型；目前只用 marked 與 KaTeX（CDN 固定版本）。真的需要新套件時，先問使用者。
- 新增的 CSS 加在 `style.css` 對應區塊，並確認手機寬度（≤ 600px）不會出現水平捲動。

### 驗證步驟
1. 在專案根目錄執行 `python3 -m http.server 8000`，打開 http://localhost:8000。
2. 檢查新頁面與既有頁面（首頁、任一講義頁）：桌面寬度、手機寬度、深色模式都正常。
3. 瀏覽器 console 沒有錯誤；圖片、公式、內部連結都能載入。
4. 跑 `python3 scripts/paper_tools.py check`，確認沒有 ❌。

### 文件同步
- 每加一個功能，更新 `README.md` 的「網站功能」一節。
- 有新的使用方式或指令時，更新本文件 §2 的觸發指令表；動到資料夾結構時，更新 §1。

