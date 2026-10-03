# 歌词时序 eval（align_eval）——测试标准

`backend/lovktv/workers/align_eval.py` 是**只读**的对齐质检：给每首歌的
`lyrics.json` 打 ok / warn / BAD 判定和行级证据，是"每次迭代有没有变好"的
回归门槛。不写任何文件。只认线上容器里的数据。

## 判定标准

### 先估全局时钟偏移（唱段覆盖率）

歌词时钟和人声 stem 时钟可能差几秒到几十秒（歌词按别的母带做的）。穷举
`clock_shift_ms`，按**唱段时间被 cue 窗口覆盖的比例**（`clock_agreement`）
打分。覆盖率和"能不能唱"直接对应，不像 onset 匹配那样被重复段落骗出假偏移。

- 非零偏移只有在比 lag0 覆盖率高 ≥8 个百分点且 ≥55% 时才采纳——重复副歌
  撞出的假偏移一律回退到 lag0。
- `clock_agreement` < 50% → `measurable=false`：stem 和歌词对不上，
  不做行级挑错，只查结构，标 `unmeasurable`。

### 真行首 onset + 细切乐句边界

`vocal_regions` 的默认 merge_gap 会把相邻乐句并成一坨，拿句1的 onset 去量
句2 会把准时的行误判成晚 1 秒。所以：

- "行首"= 前面有 ≥600ms 静音的 region 起点；
- 但量残差时用**细切**（merge_gap 60ms）乐句边界，找 cue 起点 ±600ms 内
  最近的边界做锚——没有边界的行是乐句中起唱，不可测不报错。

### 行级 flag（仅对非 trusted、且 measurable 时）

| flag | 含义 | 严重度 |
|---|---|---|
| `silent-line-hard` | 唱段范围内行覆盖区间 stem+混音都静（挂在纯静音上） | 硬错 |
| `order-hard` | 与上行重叠 >3s | 结构性硬错 |
| `past-end` | 起点越过音频结尾 | 行级硬错（不升级全曲） |
| `reading-inline` | 日文行内嵌了读音层（`大丈夫ダイジョウブだいじょうぶ`） | 硬错 |
| `silent-line` | 行下人声 <20% 且非弱唱，或唱段范围外的静默行 | 只报不判 |
| `late` / `late-soft` / `early` | 行级时序残差，只报不判 | 信息 |
| `order` | 与上行重叠 >300ms | 信息 |
| `credit` / `echo-line` | staff/标题/括号echo行 | 不计入判定 |
| `stem-gap` | stem 漏了人声但混音有声 | 信息（分离器问题） |

**行级 early/late 不参与判定。** 在连唱（legato）的人声 stem 上，一个落在
乐句中段的 cue 无法和“这行确实显示晚了”区分——`viva la vida`、
`Get along`、`From Now On` 里大量 -1.5~-2.5s 的“late”全是 bleed onset 假锚。
残差数字仍在 `lines[].shift_ms` 里输出供人工看，但不进 verdict。

### 段级检查

| 检查 | 触发条件 | 严重度 |
|---|---|---|
| `uncovered` | 行间有唱段没人出词，且满足两个独立证据之一 | 硬错 |
| `dropped` | 源 `lyrics.lrc` 某行有唱段，但该文本在整条时间轴里不存在 | 硬错 |
| `clock-offset` | 全局偏移 ≥1.2s（覆盖率确认） | 硬错 |

`uncovered` 的两个证据取其一即可：

- **lrc 行戳佐证**：源 lrc 在同一时刻也标了行（±3s），且该行文本不在
  ±8s 内的任何 cue 里。有戳就不用过 voice 门——`勇气100%` 的 hook 被
  贴错 repeat，行戳还在原位置，是唯一能抓住的证据。
- **无声唱段 + 真唱**：无戳时要求 region 是新行 onset（前有 ≥600ms 静音）
  且 vocal stem 明显压过 karaoke stem（≥15%）。间奏、和声尾巴、器乐
  bleed 全部在这一步被洗掉。

`dropped` 用源 lrc 做文本存在性审计（经 `fold_ja_netease_kanji` 简→日汉字
归一），staff/注释行（中日英 staff 头、含 `・`/`/` 的复合角色、无假名
行）先剔除。

两类防误报：

- **弱人声**：stem 包络 8% 低阈值再验，弱唱行判 `stem-gap` 不判 early/silent。
- **唱段范围外的静默行**：首行 onset 前的标题卡、末段唱完后的 credit，
  是合法显示，`silent-line-hard` 降为 `silent-line`。

### trusted 时间轴

- `mugen`：`mugen.ass` 是人工真理，逐行对比 `lyrics.json` 行起点
  （±500ms、行数相同）。不一致即 BAD；stem 对不上只记 `stem-drift`/`stem-suspect`。
- `manual`：编辑器锁定的结果，不做逐行挑错，只查结构。

### 判定

- **BAD**：≥3 个硬 flag 行（含 `reading-inline`），或有 `uncovered`/
  `dropped`，或结构性损坏，或整段时钟偏移。唱的人能明显感觉到的错。
- **warn**：≤2 个硬 flag 行——边缘，值得看但不判死；或不可测时钟下有结构问题。
- **ok**：干净，或 stem 不可信但结构完整。

当前全库（36 首）实测：3 BAD——`勇气100%`（hook 被贴错 repeat，4 段有戳
漏句）、`扉をあけて`（3 处 `reading-inline`）、`Another Day of Sun`
（outro 唱段无词 + 一行越过音频尾）。其余 ok。

## 使用（在 43 的容器里跑）

```bash
sudo docker exec lov-ktv-lov-ktv-1 python -m lovktv.workers.align_eval --all --lines
```

迭代门槛：

```bash
sudo docker exec lov-ktv-lov-ktv-1 python -m lovktv.workers.align_eval \
  --save-baseline /app/data/eval/base.json
sudo docker exec lov-ktv-lov-ktv-1 python -m lovktv.workers.align_eval \
  --baseline /app/data/eval/base.json --lines
# 任何一首 bad_lines↑ / uncovered_ms↑ / on_time_pct↓2pt / ok→BAD 都列出并 exit 1
```

输出每行：`ok|warn|BAD  on=准时行数/可测行数  bad=硬错行数  miss=漏句数  drop=丢词数  med=残差中位`
加 `stem-drift`/`stem-suspect`/`clock-offset`/`unmeasurable`/`ass-diff`。
`--json`/`--out` 出完整明细。

## 各类 BAD 的修法

- `silent-line-hard` 成片：歌词挂在没唱/纯静音上，参考歌词版本对不上录音。
- `late` 成片且同向：整钟偏，查歌词候选的母带。
- `clock-offset`：歌词按另一个剪辑做的，换 LRC 源或整体回移。
- `uncovered`：漏唱段，agent 丢行或 LRC 版本缺段。
- `stem-drift`/`stem-suspect`：歌词没错，`vocals.wav`/`guide.m4a` 是别的母带，重新分离。
