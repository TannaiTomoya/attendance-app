"""日報・出退勤かんたん記録 — Streamlit アプリ（第一弾）"""

from __future__ import annotations

import io
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

STANDARD_WORK_MINUTES = 480  # 8時間

WORK_TYPES = [
    "通常勤務",
    "有給休暇",
    "欠勤",
    "遅刻",
    "早退",
    "外出",
    "特別休暇",
    "その他",
]

LEAVE_TYPES = [
    "有給休暇",
    "欠勤",
    "遅刻",
    "早退",
    "外出",
    "リフレッシュ休暇",
    "特別休暇",
    "その他",
]

ACQUISITION_TYPES = [
    "終日",
    "半日休・前半",
    "半日休・後半",
    "時間単位",
    "連休",
]

REASONS = [
    "体調不良",
    "家族都合",
    "私用",
    "農作業",
    "旅行",
    "感染症",
    "慶弔",
    "その他",
]

DISCLAIMER = (
    "※このアプリは社内確認用の簡易日報・出退勤・届出記録ツールです。"
    "正式な勤怠管理、休暇管理、給与計算、労務判断は会社規定および法令に従って確認してください。"
)

LOCAL_KEYS = ("daily_reports", "attendance_records", "leave_requests", "employees", "settings")
DEFAULT_ADMIN_PASSWORD = "admin"

# ---------------------------------------------------------------------------
# ページ設定・初期化
# ---------------------------------------------------------------------------


def init_page() -> None:
    st.set_page_config(
        page_title="日報・出退勤かんたん記録",
        page_icon="📋",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def init_session_state() -> None:
    for key in LOCAL_KEYS:
        if key not in st.session_state:
            st.session_state[key] = []
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False
    if "paid_leave_balance" not in st.session_state:
        st.session_state.paid_leave_balance = 10.0
    if "_supabase_client" not in st.session_state:
        st.session_state._supabase_client = None
    if "storage_mode" not in st.session_state:
        st.session_state.storage_mode = detect_storage_mode()


# ---------------------------------------------------------------------------
# ストレージ（Supabase / session_state フォールバック）
# ---------------------------------------------------------------------------


def _read_supabase_config() -> tuple[str | None, str | None]:
    try:
        supabase_cfg = st.secrets.get("supabase", {})
        url = supabase_cfg.get("url")
        key = supabase_cfg.get("key")
        if url and key:
            return str(url), str(key)
    except Exception:
        pass
    return None, None


def _create_supabase_client(url: str, key: str):
    from supabase import create_client

    return create_client(url, key)


def detect_storage_mode() -> str:
    """Supabase 接続可能なら 'supabase'、それ以外は 'local'。"""
    url, key = _read_supabase_config()
    if not url or not key:
        st.session_state._supabase_client = None
        return "local"
    try:
        client = _create_supabase_client(url, key)
        st.session_state._supabase_client = client
        return "supabase"
    except Exception:
        st.session_state._supabase_client = None
        return "local"


def use_supabase() -> bool:
    return st.session_state.get("storage_mode") == "supabase"


def get_supabase_client():
    if use_supabase():
        return st.session_state.get("_supabase_client"), True
    return None, False


def get_admin_password() -> str:
    try:
        password = st.secrets.get("admin", {}).get("password")
        if password:
            return str(password)
    except Exception:
        pass
    return DEFAULT_ADMIN_PASSWORD


def is_db_mode() -> bool:
    return use_supabase()


def storage_mode_label() -> str:
    return "Supabase" if use_supabase() else "ローカル一時保存（session_state）"


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now().isoformat()


def today_str() -> str:
    return date.today().isoformat()


def month_start(d: date | None = None) -> date:
    d = d or date.today()
    return d.replace(day=1)


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def parse_time(value: Any) -> time | None:
    if value is None:
        return None
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.time()
    text = str(value)
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def time_to_str(value: time | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%H:%M")


def calculate_work_minutes(
    start: time | None,
    end: time | None,
    break_minutes: int,
) -> int:
    if start is None or end is None:
        return 0
    start_dt = datetime.combine(date.today(), start)
    end_dt = datetime.combine(date.today(), end)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    total = int((end_dt - start_dt).total_seconds() // 60) - break_minutes
    return max(total, 0)


def calculate_overtime(work_minutes: int) -> int:
    return max(work_minutes - STANDARD_WORK_MINUTES, 0)


def minutes_to_hours_text(minutes: int) -> str:
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}時間{mins}分"


def df_to_csv_download(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def show_footer() -> None:
    st.divider()
    st.caption(DISCLAIMER)


# ---------------------------------------------------------------------------
# データアクセス（Supabase 優先 → 未接続時は session_state）
# ---------------------------------------------------------------------------


def _local_append(table: str, record: dict) -> None:
    st.session_state[table].append(record)


def _local_replace(table: str, records: list[dict]) -> None:
    st.session_state[table] = records


def _local_all(table: str) -> list[dict]:
    return list(st.session_state.get(table, []))


def fetch_all(table: str) -> list[dict]:
    if use_supabase():
        client = st.session_state.get("_supabase_client")
        if client:
            try:
                response = client.table(table).select("*").execute()
                return response.data or []
            except Exception as exc:
                st.warning(f"Supabase 取得失敗のためローカルデータを表示します: {exc}")
    return _local_all(table)


def insert_record(table: str, record: dict) -> None:
    if use_supabase():
        client = st.session_state.get("_supabase_client")
        if client:
            try:
                client.table(table).insert(record).execute()
                return
            except Exception as exc:
                st.warning(f"Supabase 保存失敗のためローカルに保存します: {exc}")
    _local_append(table, record)


def update_record(table: str, record_id: str, updates: dict) -> None:
    if use_supabase():
        client = st.session_state.get("_supabase_client")
        if client:
            try:
                client.table(table).update(updates).eq("id", record_id).execute()
                return
            except Exception as exc:
                st.warning(f"Supabase 更新失敗のためローカルを更新します: {exc}")
    records = _local_all(table)
    for i, row in enumerate(records):
        if row.get("id") == record_id:
            records[i] = {**row, **updates}
            break
    _local_replace(table, records)


def find_daily_report(target_date: str, employee_email: str) -> dict | None:
    for row in fetch_all("daily_reports"):
        if row.get("date") == target_date and row.get("employee_email") == employee_email:
            return row
    return None


def find_attendance_record(target_date: str, employee_email: str) -> dict | None:
    for row in fetch_all("attendance_records"):
        if row.get("date") == target_date and row.get("employee_email") == employee_email:
            return row
    return None


# ---------------------------------------------------------------------------
# 集計
# ---------------------------------------------------------------------------


def filter_by_month(records: list[dict], date_field: str, ref: date | None = None) -> list[dict]:
    ref = ref or date.today()
    start = month_start(ref)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    result = []
    for row in records:
        d = parse_date(row.get(date_field))
        if d and start <= d < end:
            result.append(row)
    return result


def get_dashboard_metrics() -> dict[str, Any]:
    today = today_str()
    daily_reports = fetch_all("daily_reports")
    attendance_records = fetch_all("attendance_records")
    leave_requests = fetch_all("leave_requests")

    today_reports = [r for r in daily_reports if r.get("date") == today]
    today_attendance_emails = {
        r.get("employee_email") for r in attendance_records if r.get("date") == today
    }
    not_clocked_out = [
        r
        for r in today_reports
        if r.get("employee_email") not in today_attendance_emails
        and r.get("work_type") == "通常勤務"
    ]

    month_attendance = filter_by_month(attendance_records, "date")
    work_days = len({r.get("date") for r in month_attendance if r.get("work_minutes", 0) > 0})
    total_work = sum(int(r.get("work_minutes") or 0) for r in month_attendance)
    total_overtime = sum(int(r.get("overtime_minutes") or 0) for r in month_attendance)
    month_leaves = filter_by_month(leave_requests, "target_date")

    return {
        "today_report_count": len(today_reports),
        "not_clocked_out_count": len(not_clocked_out),
        "month_work_days": work_days,
        "month_work_minutes": total_work,
        "month_overtime_minutes": total_overtime,
        "month_leave_count": len(month_leaves),
        "paid_leave_balance": st.session_state.paid_leave_balance,
    }


# ---------------------------------------------------------------------------
# 画面：ダッシュボード
# ---------------------------------------------------------------------------


def page_dashboard() -> None:
    st.header("ダッシュボード")
    metrics = get_dashboard_metrics()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("今日の日報登録件数", metrics["today_report_count"])
    c2.metric("未退勤の件数", metrics["not_clocked_out_count"])
    c3.metric("今月の勤務日数", metrics["month_work_days"])
    c4.metric("今月の届出件数", metrics["month_leave_count"])

    c5, c6, c7 = st.columns(3)
    c5.metric("今月の勤務時間", minutes_to_hours_text(metrics["month_work_minutes"]))
    c6.metric("今月の時間外労働", minutes_to_hours_text(metrics["month_overtime_minutes"]))
    c7.metric("有給休暇残日数（仮）", f"{metrics['paid_leave_balance']:.1f}日")

    st.subheader("接続状態")
    if is_db_mode():
        st.success(f"保存先: {storage_mode_label()}")
    else:
        st.warning(f"保存先: {storage_mode_label()}（ブラウザを閉じると消えます）")

    st.subheader("直近の日報")
    reports = sorted(fetch_all("daily_reports"), key=lambda r: r.get("created_at", ""), reverse=True)[:10]
    if reports:
        st.dataframe(pd.DataFrame(reports), use_container_width=True, hide_index=True)
    else:
        st.info("日報データはまだありません。")


# ---------------------------------------------------------------------------
# 画面：朝の日報入力
# ---------------------------------------------------------------------------


def page_morning_report() -> None:
    st.header("朝の日報入力")

    with st.form("morning_report_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            report_date = st.date_input("日付", value=date.today())
            employee_name = st.text_input("氏名")
            employee_email = st.text_input("メールアドレス")
            work_type = st.selectbox("勤務区分", WORK_TYPES)
        with col2:
            planned_start = st.time_input("出勤予定時刻", value=time(9, 0))
            planned_end = st.time_input("退勤予定時刻", value=time(18, 0))
            planned_break = st.number_input("休憩予定分", min_value=0, max_value=480, value=60, step=5)
            work_place = st.text_input("作業場所")

        work_content = st.text_area("作業内容")
        memo = st.text_area("備考")

        submitted = st.form_submit_button("日報を登録", type="primary")

    if submitted:
        if not employee_name.strip() or not employee_email.strip():
            st.error("氏名とメールアドレスは必須です。")
            return

        date_str = report_date.isoformat()
        existing = find_daily_report(date_str, employee_email.strip())
        if existing:
            st.error(f"{date_str} の日報は既に登録されています。")
            return

        record = {
            "id": new_id(),
            "employee_name": employee_name.strip(),
            "employee_email": employee_email.strip(),
            "date": date_str,
            "work_type": work_type,
            "planned_start": time_to_str(planned_start),
            "planned_end": time_to_str(planned_end),
            "planned_break_minutes": int(planned_break),
            "work_content": work_content.strip(),
            "work_place": work_place.strip(),
            "memo": memo.strip(),
            "status": "登録済",
            "created_at": now_iso(),
        }
        insert_record("daily_reports", record)
        st.success("日報を登録しました。")
        st.balloons()


# ---------------------------------------------------------------------------
# 画面：退勤時の実績確定
# ---------------------------------------------------------------------------


def page_attendance() -> None:
    st.header("退勤時の実績確定")

    with st.form("attendance_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            report_date = st.date_input("日付", value=date.today(), key="att_date")
            employee_name = st.text_input("氏名", key="att_name")
            employee_email = st.text_input("メールアドレス", key="att_email")
        with col2:
            actual_start = st.time_input("実出勤時刻", value=time(9, 0))
            actual_end = st.time_input("実退勤時刻", value=time(18, 0))
            actual_break = st.number_input("実休憩分", min_value=0, max_value=480, value=60, step=5)

        actual_work_content = st.text_area("実作業内容")
        attendance_memo = st.text_area("退勤メモ")

        submitted = st.form_submit_button("実績を確定", type="primary")

    if submitted:
        if not employee_name.strip() or not employee_email.strip():
            st.error("氏名とメールアドレスは必須です。")
            return

        date_str = report_date.isoformat()
        work_minutes = calculate_work_minutes(actual_start, actual_end, int(actual_break))
        overtime_minutes = calculate_overtime(work_minutes)

        existing = find_attendance_record(date_str, employee_email.strip())
        record = {
            "employee_name": employee_name.strip(),
            "employee_email": employee_email.strip(),
            "date": date_str,
            "actual_start": time_to_str(actual_start),
            "actual_end": time_to_str(actual_end),
            "actual_break_minutes": int(actual_break),
            "work_minutes": work_minutes,
            "overtime_minutes": overtime_minutes,
            "status": "確定",
        }

        if existing:
            update_record(
                "attendance_records",
                existing["id"],
                {**record, "created_at": existing.get("created_at")},
            )
            st.success("実績を更新しました。")
        else:
            insert_record(
                "attendance_records",
                {
                    "id": new_id(),
                    **record,
                    "created_at": now_iso(),
                },
            )
            st.success("実績を確定しました。")

        daily = find_daily_report(date_str, employee_email.strip())
        if daily:
            daily_updates: dict[str, Any] = {"status": "退勤済"}
            if actual_work_content.strip():
                daily_updates["work_content"] = actual_work_content.strip()
            if attendance_memo.strip():
                prev_memo = daily.get("memo", "")
                daily_updates["memo"] = f"{prev_memo}\n[退勤] {attendance_memo}".strip()
            update_record("daily_reports", daily["id"], daily_updates)

        st.info(
            f"勤務時間: {minutes_to_hours_text(work_minutes)} / "
            f"時間外労働: {minutes_to_hours_text(overtime_minutes)}"
        )


# ---------------------------------------------------------------------------
# 画面：届出作成
# ---------------------------------------------------------------------------


def page_leave_request() -> None:
    st.header("届出作成")

    with st.form("leave_request_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            request_date = st.date_input("届出日", value=date.today())
            employee_name = st.text_input("氏名", key="leave_name")
            employee_email = st.text_input("メールアドレス", key="leave_email")
            target_date = st.date_input("対象日", value=date.today())
        with col2:
            leave_type = st.selectbox("休暇種類", LEAVE_TYPES)
            acquisition_type = st.selectbox("取得形態", ACQUISITION_TYPES)
            reason = st.selectbox("理由", REASONS)
            days_count = st.number_input("取得日数", min_value=0.0, max_value=30.0, value=1.0, step=0.5)

        reason_detail = st.text_area("理由の詳細・備考")
        submitted = st.form_submit_button("届出を登録", type="primary")

    if submitted:
        if not employee_name.strip() or not employee_email.strip():
            st.error("氏名とメールアドレスは必須です。")
            return

        record = {
            "id": new_id(),
            "employee_name": employee_name.strip(),
            "employee_email": employee_email.strip(),
            "request_date": request_date.isoformat(),
            "target_date": target_date.isoformat(),
            "leave_type": leave_type,
            "acquisition_type": acquisition_type,
            "reason": reason,
            "reason_detail": reason_detail.strip(),
            "days_count": float(days_count),
            "status": "申請中",
            "created_at": now_iso(),
        }
        insert_record("leave_requests", record)
        st.success("届出を登録しました。")


# ---------------------------------------------------------------------------
# 画面：管理者
# ---------------------------------------------------------------------------


def page_admin() -> None:
    st.header("管理者確認画面")

    if not st.session_state.admin_authenticated:
        st.caption("管理者のみ閲覧できます。パスワードは Streamlit secrets で設定可能です。")
        with st.form("admin_login_form"):
            password = st.text_input("管理者パスワード", type="password")
            submitted = st.form_submit_button("ログイン")
        if submitted:
            if password == get_admin_password():
                st.session_state.admin_authenticated = True
                st.rerun()
            else:
                st.error("パスワードが正しくありません。")
        return

    st.success("管理者としてログイン中")
    if st.button("ログアウト"):
        st.session_state.admin_authenticated = False
        st.rerun()

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["日報一覧", "勤怠一覧", "届出一覧", "未退勤一覧", "設定"]
    )

    daily_reports = sorted(fetch_all("daily_reports"), key=lambda r: r.get("date", ""), reverse=True)
    attendance_records = sorted(
        fetch_all("attendance_records"), key=lambda r: r.get("date", ""), reverse=True
    )
    leave_requests = sorted(
        fetch_all("leave_requests"), key=lambda r: r.get("target_date", ""), reverse=True
    )

    with tab1:
        st.subheader("日報一覧")
        if daily_reports:
            st.dataframe(pd.DataFrame(daily_reports), use_container_width=True, hide_index=True)
        else:
            st.info("データがありません。")

    with tab2:
        st.subheader("勤怠一覧")
        if attendance_records:
            display_rows = []
            for row in attendance_records:
                display_rows.append(
                    {
                        **row,
                        "勤務時間": minutes_to_hours_text(int(row.get("work_minutes") or 0)),
                        "時間外": minutes_to_hours_text(int(row.get("overtime_minutes") or 0)),
                    }
                )
            st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
        else:
            st.info("データがありません。")

    with tab3:
        st.subheader("届出一覧")
        if leave_requests:
            st.dataframe(pd.DataFrame(leave_requests), use_container_width=True, hide_index=True)
        else:
            st.info("データがありません。")

    with tab4:
        st.subheader("未退勤一覧（本日）")
        today = today_str()
        today_reports = [r for r in daily_reports if r.get("date") == today]
        today_attendance_emails = {
            r.get("employee_email") for r in attendance_records if r.get("date") == today
        }
        not_clocked_out = [
            r
            for r in today_reports
            if r.get("employee_email") not in today_attendance_emails
            and r.get("work_type") == "通常勤務"
        ]
        if not_clocked_out:
            st.dataframe(pd.DataFrame(not_clocked_out), use_container_width=True, hide_index=True)
        else:
            st.info("未退勤の記録はありません。")

    with tab5:
        st.subheader("有給休暇残日数（仮表示）")
        balance = st.number_input(
            "残日数を手入力",
            min_value=0.0,
            max_value=100.0,
            value=float(st.session_state.paid_leave_balance),
            step=0.5,
        )
        if st.button("残日数を保存"):
            st.session_state.paid_leave_balance = balance
            st.success("保存しました（セッション内）。")


# ---------------------------------------------------------------------------
# 画面：CSV出力
# ---------------------------------------------------------------------------


def page_csv_export() -> None:
    st.header("CSV出力")

    daily_df = pd.DataFrame(fetch_all("daily_reports"))
    attendance_df = pd.DataFrame(fetch_all("attendance_records"))
    leave_df = pd.DataFrame(fetch_all("leave_requests"))

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("日報")
        st.caption(f"{len(daily_df)} 件")
        if not daily_df.empty:
            st.download_button(
                "日報 CSV をダウンロード",
                data=df_to_csv_download(daily_df),
                file_name=f"daily_reports_{today_str()}.csv",
                mime="text/csv",
            )
        else:
            st.info("データがありません。")

    with col2:
        st.subheader("勤怠")
        st.caption(f"{len(attendance_df)} 件")
        if not attendance_df.empty:
            st.download_button(
                "勤怠 CSV をダウンロード",
                data=df_to_csv_download(attendance_df),
                file_name=f"attendance_records_{today_str()}.csv",
                mime="text/csv",
            )
        else:
            st.info("データがありません。")

    with col3:
        st.subheader("届出")
        st.caption(f"{len(leave_df)} 件")
        if not leave_df.empty:
            st.download_button(
                "届出 CSV をダウンロード",
                data=df_to_csv_download(leave_df),
                file_name=f"leave_requests_{today_str()}.csv",
                mime="text/csv",
            )
        else:
            st.info("データがありません。")

    st.subheader("全データ一括")
    if not daily_df.empty or not attendance_df.empty or not leave_df.empty:
        buffer = io.StringIO()
        if not daily_df.empty:
            buffer.write("=== daily_reports ===\n")
            daily_df.to_csv(buffer, index=False)
            buffer.write("\n")
        if not attendance_df.empty:
            buffer.write("=== attendance_records ===\n")
            attendance_df.to_csv(buffer, index=False)
            buffer.write("\n")
        if not leave_df.empty:
            buffer.write("=== leave_requests ===\n")
            leave_df.to_csv(buffer, index=False)

        st.download_button(
            "全データ CSV をダウンロード",
            data=buffer.getvalue().encode("utf-8-sig"),
            file_name=f"attendance_export_{today_str()}.csv",
            mime="text/csv",
        )


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------


PAGES = {
    "ダッシュボード": page_dashboard,
    "朝の日報入力": page_morning_report,
    "退勤時の実績確定": page_attendance,
    "届出作成": page_leave_request,
    "管理者確認画面": page_admin,
    "CSV出力": page_csv_export,
}


def main() -> None:
    init_page()
    init_session_state()

    st.title("日報・出退勤かんたん記録")
    st.caption("社内確認用 — 日報・出退勤・届出の簡易記録")

    with st.sidebar:
        st.header("メニュー")
        page_name = st.radio("画面を選択", list(PAGES.keys()), label_visibility="collapsed")
        st.divider()
        if is_db_mode():
            st.success("保存先: Supabase")
        else:
            st.warning("保存先: session_state（ローカル）")

    PAGES[page_name]()
    show_footer()


if __name__ == "__main__":
    main()
