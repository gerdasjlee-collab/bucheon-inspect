# -*- coding: utf-8 -*-
"""점검 기록 → 구글 시트(Apps Script 웹훅): 확정 기록·임시저장·이전 방문 조회·관리자 통계."""
import json
import urllib.request

import pandas as pd
import streamlit as st


def _post(url: str, payload: dict, timeout: int = 25):
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def save_record(url, row: dict, items: list):
    """확정 저장: '점검기록' 1행 + '문항기록' n행."""
    return _post(url, {"action": "log", "row": row, "items": items})


def save_draft(url, key: str, org: str, inspector: str, payload: dict):
    return _post(url, {"action": "draft", "key": key, "org": org, "inspector": inspector, "payload": json.dumps(payload, ensure_ascii=False)})


def list_drafts(url, inspector: str = "") -> list:
    r = _post(url, {"action": "drafts", "inspector": inspector})
    return r.get("rows", [])


def delete_draft(url, key: str):
    return _post(url, {"action": "draft_delete", "key": key})


@st.cache_data(ttl=60, show_spinner="구글 시트에서 기록을 불러오는 중…")
def fetch(url: str, kind: str) -> pd.DataFrame:
    if not url:
        return pd.DataFrame()
    r = _post(url, {"action": "rows", "sheet": kind})
    df = pd.DataFrame(r.get("rows", []), columns=r.get("headers", []))
    for c in df.columns:
        if c in ("총점", "만점", "득점률", "방문회차", "점수", "배점"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def previous_visit(url: str, org: str) -> dict | None:
    """같은 시설의 가장 최근 확정 기록(지도사항 자동 채움용)."""
    try:
        df = fetch(url, "점검기록")
    except Exception:  # noqa: BLE001
        return None
    if df.empty or "시설명" not in df.columns:
        return None
    d = df[df["시설명"].astype(str).str.strip() == org.strip()].sort_values("점검일자")
    return None if d.empty else d.iloc[-1].to_dict()


def admin_panel(url: str):
    st.markdown("### 📊 관리자 통계 (지도점검 현황)")
    if not url:
        st.warning("Secrets에 LOG_WEBHOOK_URL 이 없습니다."); return
    if st.button("🔄 새로 고침"):
        fetch.clear()
    try:
        df = fetch(url, "점검기록"); it = fetch(url, "문항기록")
    except Exception as e:  # noqa: BLE001
        st.error(f"시트를 읽지 못했습니다: {e}"); return
    if df.empty:
        st.info("아직 확정된 점검 기록이 없습니다."); return
    df["월"] = df["점검일자"].astype(str).str[:7]
    f1, f2, f3 = st.columns(3)
    months = sorted(df["월"].unique().tolist()); sel_m = f1.multiselect("월", months, default=months)
    groups = sorted(df["시설군"].unique().tolist()); sel_g = f2.multiselect("시설군", groups, default=groups)
    q = f3.text_input("시설명 검색")
    d = df[df["월"].isin(sel_m) & df["시설군"].isin(sel_g)]
    if q.strip():
        d = d[d["시설명"].astype(str).str.contains(q.strip(), na=False)]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("점검 건수", len(d)); m2.metric("점검 시설 수", d["시설명"].nunique())
    m3.metric("평균 득점률", f"{d['득점률'].mean():.0f} %" if len(d) else "-")
    imp = d["이전개선여부"].astype(str).str.contains("개선|완료|예", na=False).sum() if "이전개선여부" in d else 0
    m4.metric("이전 지도사항 개선 건수", int(imp))
    t1, t2, t3, t4, t5 = st.tabs(["시설별 추이", "시설군·체크리스트별", "취약 문항 TOP", "점검자별", "전체 기록"])
    with t1:
        g = d.groupby("시설명").agg(점검횟수=("점검일자", "size"), 최근점검=("점검일자", "max"), 평균득점률=("득점률", "mean"), 최근득점률=("득점률", "last")).reset_index()
        g["평균득점률"] = g["평균득점률"].round(0)
        st.dataframe(g.sort_values("평균득점률"), hide_index=True, use_container_width=True)
        org = st.selectbox("시설 선택 (회차별 점수 추이)", sorted(d["시설명"].unique()))
        s = d[d["시설명"] == org].sort_values("점검일자")[["점검일자", "체크리스트", "총점", "만점", "득점률", "이번지도사항"]]
        st.dataframe(s, hide_index=True, use_container_width=True)
        if len(s) > 1:
            st.line_chart(s.set_index("점검일자")["득점률"])
    with t2:
        g = d.groupby(["시설군", "체크리스트"]).agg(건수=("시설명", "size"), 시설수=("시설명", "nunique"), 평균득점률=("득점률", "mean"), 최저=("득점률", "min")).reset_index()
        g["평균득점률"] = g["평균득점률"].round(0)
        st.dataframe(g, hide_index=True, use_container_width=True)
        st.bar_chart(d.groupby("시설군")["득점률"].mean())
    with t3:
        if it.empty:
            st.info("문항 기록이 없습니다.")
        else:
            i2 = it[it["기록ID"].isin(d["기록ID"])] if "기록ID" in it and "기록ID" in d else it
            i2 = i2[i2["점수"].notna()]
            i2["감점"] = i2["배점"] - i2["점수"]
            w = i2.groupby(["체크리스트", "번호", "항목"]).agg(점검수=("점수", "size"), 감점시설수=("감점", lambda s: int((s > 0).sum())), 평균감점=("감점", "mean")).reset_index()
            w["감점률%"] = (w["감점시설수"] / w["점검수"] * 100).round(0); w["평균감점"] = w["평균감점"].round(2)
            st.caption("감점이 자주 발생하는 문항 — 집합 교육·안내문 주제 선정에 활용")
            st.dataframe(w.sort_values(["감점률%", "평균감점"], ascending=False).head(20), hide_index=True, use_container_width=True)
    with t4:
        g = d.groupby("점검자").agg(건수=("시설명", "size"), 시설수=("시설명", "nunique"), 평균득점률=("득점률", "mean")).reset_index()
        g["평균득점률"] = g["평균득점률"].round(0)
        st.dataframe(g, hide_index=True, use_container_width=True)
    with t5:
        st.dataframe(d.drop(columns=["월"]).sort_values("점검일자", ascending=False), hide_index=True, use_container_width=True, height=420)
        st.download_button("⬇️ 점검 기록 CSV", d.to_csv(index=False).encode("utf-8-sig"), "지도점검기록.csv", "text/csv")
        if not it.empty:
            st.download_button("⬇️ 문항별 기록 CSV", it.to_csv(index=False).encode("utf-8-sig"), "지도점검_문항기록.csv", "text/csv")
