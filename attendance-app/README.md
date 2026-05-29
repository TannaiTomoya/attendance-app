# 日報・出退勤かんたん記録

> **重要:** このアプリは**正式な勤怠管理システムではありません**。  
> 社内確認用の簡易日報・出退勤・届出記録ツールです。  
> 正式な勤怠管理、休暇管理、給与計算、労務判断は、会社規定および法令に従って別途確認してください。

---

## 目的

従業員本人が毎朝紙で書いている日報と、休み・遅刻・早退などの連絡を、Webフォームで登録・確認できるようにすることです。

第一弾は、社内PC・会社メール・正式な管理担当者が整っていない段階での**暫定運用**を想定しています。DBを台帳とし、開発・保守担当者が管理画面で内容を確認する設計です。

---

## 解決する Pain

| 現状の課題 | 本アプリでの対応 |
|---|---|
| 朝イチで紙の日報を書いている | Webフォームで日報を登録 |
| 休み・遅刻・早退がメールや個別連絡ばかり | 届出フォームで一元記録 |
| 記録が散在し、確認が面倒 | 管理者画面・CSV出力で一覧確認 |
| 本格的な勤怠システム導入前の空白期間 | 簡易ツールで暫定対応 |

---

## 対象ユーザー

- **従業員本人** — 日報入力、退勤実績入力、届出作成
- **暫定の開発・保守担当者** — 管理者画面での確認、CSV出力
- **第一弾では対象外** — 正式な勤怠管理者、給与担当、一般公開ユーザー

---

## 第一弾でできること

- 朝の日報入力
- 退勤時の実績入力
- 勤務時間の自動計算（実退勤 − 実出勤 − 休憩分）
- 時間外労働の簡易計算（所定8時間超過分）
- 欠勤・遅刻・早退・有給などの届出作成
- 記録一覧表示（ダッシュボード・管理者画面）
- CSVダウンロード
- DB保存（Supabase）
- 管理者画面（簡易パスワード認証）
- Supabase 未接続時の `session_state` フォールバック

---

## 第一弾でやらないこと

- 本格ログイン（ユーザーアカウント管理）
- メール自動送信
- LINE通知の本実装
- PDF出力
- 承認ワークフロー
- 給与計算アプリとの連携
- 稟議申請・物品購入申請・弁当注文
- 有給付与の厳密自動計算
- 労務法令の厳密判定

---

## 画面構成

| 画面 | 主な機能 |
|---|---|
| 1. ダッシュボード | 本日の日報件数、未退勤件数、今月の勤務集計、届出件数 |
| 2. 朝の日報入力 | 日付・氏名・勤務区分・予定時刻・作業内容など |
| 3. 退勤時の実績確定 | 実出勤/退勤・休憩・勤務時間・時間外の自動計算 |
| 4. 届出作成 | 休暇種類・取得形態・理由・取得日数 |
| 5. 管理者確認画面 | 日報/勤怠/届出一覧、未退勤一覧（パスワード保護） |
| 6. CSV出力 | 各テーブルのCSVダウンロード |

---

## DB設計

Supabase（PostgreSQL）を台帳として使用します。LINE通知は台帳にしません。

### 1. `employees`

| カラム | 型（目安） | 説明 |
|---|---|---|
| id | uuid / text | 主キー |
| name | text | 氏名 |
| email | text | メールアドレス |
| role | text | 役割 |
| active | boolean | 有効フラグ |
| created_at | timestamptz | 作成日時 |

### 2. `daily_reports`

| カラム | 型（目安） | 説明 |
|---|---|---|
| id | uuid / text | 主キー |
| employee_name | text | 氏名 |
| employee_email | text | メールアドレス |
| date | date | 日付 |
| work_type | text | 勤務区分 |
| planned_start | text | 出勤予定時刻 |
| planned_end | text | 退勤予定時刻 |
| planned_break_minutes | integer | 休憩予定分 |
| work_content | text | 作業内容 |
| work_place | text | 作業場所 |
| memo | text | 備考 |
| status | text | 状態（例: 登録済 / 退勤済） |
| created_at | timestamptz | 作成日時 |

**勤務区分:** 通常勤務 / 有給休暇 / 欠勤 / 遅刻 / 早退 / 外出 / 特別休暇 / その他

### 3. `attendance_records`

| カラム | 型（目安） | 説明 |
|---|---|---|
| id | uuid / text | 主キー |
| employee_name | text | 氏名 |
| employee_email | text | メールアドレス |
| date | date | 日付 |
| actual_start | text | 実出勤時刻 |
| actual_end | text | 実退勤時刻 |
| actual_break_minutes | integer | 実休憩分 |
| work_minutes | integer | 勤務時間（分） |
| overtime_minutes | integer | 時間外労働（分） |
| status | text | 状態 |
| created_at | timestamptz | 作成日時 |

**計算式:**

```
勤務時間（分） = 実退勤時刻 − 実出勤時刻 − 実休憩分
時間外労働（分） = max(勤務時間 − 480, 0)   ※所定労働時間 = 8時間
```

### 4. `leave_requests`

| カラム | 型（目安） | 説明 |
|---|---|---|
| id | uuid / text | 主キー |
| employee_name | text | 氏名 |
| employee_email | text | メールアドレス |
| request_date | date | 届出日 |
| target_date | date | 対象日 |
| leave_type | text | 休暇種類 |
| acquisition_type | text | 取得形態 |
| reason | text | 理由 |
| reason_detail | text | 理由の詳細・備考 |
| days_count | numeric | 取得日数 |
| status | text | 状態 |
| created_at | timestamptz | 作成日時 |

**休暇種類:** 有給休暇 / 欠勤 / 遅刻 / 早退 / 外出 / リフレッシュ休暇 / 特別休暇 / その他  
**取得形態:** 終日 / 半日休・前半 / 半日休・後半 / 時間単位 / 連休  
**理由:** 体調不良 / 通院 / 家族都合 / 私用 / 農作業 / 旅行 / 感染症 / 慶弔 / その他

### 5. `settings`

| カラム | 型（目安） | 説明 |
|---|---|---|
| id | uuid / text | 主キー |
| key | text | 設定キー |
| value | text | 設定値 |
| description | text | 説明 |

---

## Supabase 設定方法

### 1. プロジェクト作成

1. [Supabase](https://supabase.com/) でプロジェクトを作成
2. SQL Editor で上記5テーブルを作成
3. **Settings → API** から `Project URL` と `anon public key` を取得

### 2. Streamlit secrets の設定

プロジェクト直下に `.streamlit/secrets.toml` を作成します（Git管理しないこと）。

```toml
[supabase]
url = "https://your-project.supabase.co"
key = "your-anon-key"

[admin]
password = "your-admin-password"
```

### 3. ストレージの動作

| 状態 | 保存先 |
|---|---|
| Supabase 接続成功 | Supabase |
| secrets 未設定 / 接続失敗 | `st.session_state`（ブラウザセッション内のみ） |

管理者パスワードが secrets にない場合、ローカル開発用デフォルトは `admin` です。

---

## ローカル起動方法

### 前提

- Python 3.9 以上推奨

### 手順

```bash
cd attendance-app
pip install -r requirements.txt
streamlit run app.py
```

ブラウザで `http://localhost:8501` が開きます。

Supabase を設定しない場合でも、ローカル一時保存モードで動作確認できます。

---

## デプロイ方法

### Streamlit Community Cloud（推奨）

1. リポジトリを GitHub に push
2. [Streamlit Community Cloud](https://streamlit.io/cloud) でリポジトリを接続
3. **Main file path:** `attendance-app/app.py`
4. **Secrets** に Supabase 接続情報と管理者パスワードを設定

```toml
[supabase]
url = "https://your-project.supabase.co"
key = "your-anon-key"

[admin]
password = "your-admin-password"
```

### その他

- 社内サーバー / VPS 上で `streamlit run app.py` を常時起動
- Docker 化して社内環境へ配置

いずれの方法でも、**本番運用前にアクセス制限・HTTPS・パスワード管理**を確認してください。

---

## 注意書き

- 本アプリは**社内確認用の簡易記録ツール**であり、正式な勤怠管理システムではありません
- 有給残日数は第一弾では手入力または仮表示です
- 体調不良・通院などの詳細理由は、将来的に LINE 通知を入れる場合でも概要のみとし、詳細は管理画面で確認する設計です
- LINE通知は台帳にせず、DB（Supabase）を台帳とします
- ローカル一時保存モードのデータは、ブラウザを閉じると消える場合があります
- 給与・労務判断の最終確認は、必ず会社規定および法令に従って行ってください

アプリ画面下部にも同趣旨の注意書きを表示しています。

---

## 将来の改善予定

- 社内PC・会社メール環境への移行
- 正式な管理担当者への権限移譲
- 本格ログイン（ユーザー認証）
- メール自動送信（概要通知）
- LINE通知（概要のみ、詳細は管理画面）
- PDF出力
- 承認ワークフロー
- 給与計算アプリとの連携
- 有給付与・残日数の厳密管理
- 労務法令に基づく判定ロジック
- 従業員マスタ（`employees`）との連携強化

---

## 技術構成

- Python
- Streamlit
- Supabase
- pandas

## フォルダ構成

```
attendance-app/
├── app.py
├── requirements.txt
├── README.md
└── .gitignore
```
