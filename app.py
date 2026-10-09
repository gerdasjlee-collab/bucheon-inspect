# -*- coding: utf-8 -*-
"""급식소 위생·영양 지도점검 도우미 — 부천시어린이·사회복지급식관리지원센터
체크리스트(식약처 2026 서식 11종) 현장 입력(휴대폰/패드/PC) → 점수 자동 집계 → AI 통지문 초안(칭찬+개선) → 워드/엑셀 → 구글 시트 기록·통계."""
import datetime as _dt
import json
import uuid

import pandas as pd
import streamlit as st

import checklist as CK
import inspectlog as L
import report as R

st.set_page_config(page_title="급식 지도점검 도우미", page_icon="✅", layout="wide")
CENTER = "부천시어린이·사회복지급식관리지원센터"


def _secret(name, default=""):
    try:
        return str(st.secrets.get(name, default))
    except Exception:  # noqa: BLE001
        return default


ACCESS_CODES = [c.strip() for c in _secret("ACCESS_CODE", "").split(",") if c.strip()]
ADMIN_CODES = [c.strip() for c in _secret("ADMIN_CODE", "").split(",") if c.strip()]
GEMINI_KEY = _secret("GEMINI_API_KEY", "").strip()
LOG_URL = _secret("LOG_WEBHOOK_URL", "").strip()
KST = lambda: _dt.datetime.utcnow() + _dt.timedelta(hours=9)  # noqa: E731

st.title("✅ 급식소 위생·영양 지도점검 도우미")
st.caption(f"{CENTER} · 식약처 2026 체크리스트 11종 · 현장에서 휴대폰/패드로, 사무실에서 PC로")

# ── 로그인 (센터 직원 전용) ──
if ACCESS_CODES and not st.session_state.get("user"):
    st.info("🔒 센터 직원 전용입니다. **접속 코드**와 점검자 성명을 입력하세요.")
    with st.form("login"):
        code = st.text_input("접속 코드 *", type="password")
        name = st.text_input("점검자 성명 *", placeholder="예: 홍길동")
        ok = st.form_submit_button("입장", use_container_width=True)
    if ok:
        c = code.strip()
        if c in ACCESS_CODES or c in ADMIN_CODES:
            if not name.strip():
                st.error("점검자 성명을 입력하세요.")
            else:
                st.session_state.user = {"name": name.strip(), "admin": c in ADMIN_CODES}; st.rerun()
        else:
            st.error("접속 코드가 올바르지 않습니다.")
    st.stop()
USER = st.session_state.get("user", {"name": "(테스트)", "admin": True})
S = st.session_state
S.setdefault("scores", {}); S.setdefault("notes", {}); S.setdefault("info", {}); S.setdefault("draft", {})

# ── 사이드바 ──
with st.sidebar:
    st.markdown(f"**👤 {USER['name']}**" + ("  \n🔑 관리자" if USER.get("admin") else ""))
    if st.button("🚪 로그아웃", use_container_width=True):
        for k in list(S.keys()):
            S.pop(k, None)
        st.rerun()
    page = st.radio("화면", ["📝 지도점검", "📊 관리자 통계"] if USER.get("admin") else ["📝 지도점검"], label_visibility="collapsed")
    st.divider()
    mode = st.radio("입력 방식", ["📱 카드 (휴대폰·패드)", "🖥️ 표 (PC)"], help="현장에서는 카드, 사무실에서 종이 점검표를 옮길 때는 표가 편합니다")
    st.divider()
    st.markdown("**💾 임시 저장 / 불러오기**")
    st.caption("현장에서 입력 중 통신이 끊겨도 잃지 않도록 구글 시트에 임시 저장합니다.")
    if st.button("💾 지금 임시 저장", use_container_width=True, disabled=not LOG_URL):
        info = S.info
        if not info.get("시설명") or not S.get("cid"):
            st.warning("시설명과 체크리스트를 먼저 선택하세요.")
        else:
            key = f"{info['시설명']}|{info.get('점검일자')}|{S['cid']}"
            try:
                L.save_draft(LOG_URL, key, info["시설명"], USER["name"], {"cid": S["cid"], "info": info, "scores": S.scores, "notes": S.notes, "draft": S.draft, "yn": S.get("yn", {})})
                st.success("임시 저장됨"); S["draft_key"] = key
            except Exception as e:  # noqa: BLE001
                st.error(f"저장 실패: {e}")
    if LOG_URL and st.button("📂 임시 저장 목록", use_container_width=True):
        try:
            S["drafts"] = L.list_drafts(LOG_URL)
        except Exception as e:  # noqa: BLE001
            st.error(f"불러오기 실패: {e}")
    if S.get("drafts"):
        opts = {f"{d['org']} · {d['key'].split('|')[1]} · {d['inspector']}": d for d in S["drafts"]}
        pick = st.selectbox("불러올 기록", list(opts))
        c1, c2 = st.columns(2)
        if c1.button("불러오기", use_container_width=True):
            p = json.loads(opts[pick]["payload"])
            S["cid"], S.info, S.scores, S.notes, S.draft, S["yn"] = p["cid"], p["info"], p["scores"], p["notes"], p.get("draft", {}), p.get("yn", {})
            S["draft_key"] = opts[pick]["key"]; S.pop("drafts"); st.rerun()
        if c2.button("삭제", use_container_width=True):
            L.delete_draft(LOG_URL, opts[pick]["key"]); S.pop("drafts"); st.rerun()
    st.divider()
    if st.button("🆕 새 점검 시작 (입력 초기화)", use_container_width=True):
        for k in ("scores", "notes", "info", "draft", "cid", "draft_key", "summ", "yn", "rid"):
            S.pop(k, None)
        st.rerun()

if page == "📊 관리자 통계":
    L.admin_panel(LOG_URL); st.stop()

# ── 1. 기본 정보 ──
st.markdown("### 1️⃣ 시설 · 체크리스트")
info = S.info
c1, c2 = st.columns([1, 2])
group = c1.selectbox("시설군", CK.GROUPS, index=CK.GROUPS.index(info.get("시설군", CK.GROUPS[0])))
cls = CK.by_group(group)
names = [c["name"] for c in cls]
cur_idx = next((i for i, c in enumerate(cls) if c["id"] == S.get("cid")), 0)
pick = c2.selectbox("체크리스트", names, index=cur_idx, help="같은 방문에서 위생과 영양을 모두 점검하면, 하나 확정 후 '새 점검 시작'으로 다른 하나를 진행하세요")
cl = cls[names.index(pick)]
if S.get("cid") != cl["id"]:
    S["cid"] = cl["id"]
if cl.get("note"):
    st.caption("ℹ️ " + cl["note"])

with st.expander("시설 기본 정보 (서식 머리 부분)", expanded=not info.get("시설명")):
    k1, k2, k3 = st.columns([2, 2, 1])
    org = k1.text_input("시설명 *", info.get("시설명", ""))
    addr = k2.text_input("주소", info.get("주소", ""))
    visit = k3.number_input("방문회차", 1, 20, int(info.get("방문회차", 1) or 1))
    k4, k5, k6, k7 = st.columns(4)
    date = k4.date_input("점검일자", _dt.date.fromisoformat(info["점검일자"]) if info.get("점검일자") else KST().date())
    kind = k5.selectbox("구분", ["정규", "기타"], index=["정규", "기타"].index(info.get("구분", "정규")))
    mem = k6.selectbox("회원유형", ["일반", "기본", "해당없음"], index=["일반", "기본", "해당없음"].index(info.get("회원유형", "일반")))
    grade = k7.selectbox("회원등급", ["열매", "새싹", "해당없음"], index=["열매", "새싹", "해당없음"].index(info.get("회원등급", "열매")))
    k8, k9, k10, k11 = st.columns(4)
    sub = k8.text_input("세부유형", info.get("세부유형", ""), placeholder="예: 국공립 / 노인요양시설 / 지역아동센터")
    cur = k9.number_input("현원 (명)", 0, 2000, int(info.get("현원", 0) or 0))
    mx = k10.number_input("1회 최대급식인원 (명)", 0, 2000, int(info.get("1회최대급식인원", 0) or 0))
    staff = k11.text_input("종사자 (총/영양사/조리원)", info.get("종사자", ""), placeholder="예: 12/1/2")
    k12, k13, k14, k15 = st.columns(4)
    diet = k12.selectbox("영양사 근무 형태", ["없음", "담당(전담)영양사", "공동영양사"], index=["없음", "담당(전담)영양사", "공동영양사"].index(info.get("영양사근무", "없음")))
    water = k13.selectbox("용수", ["상수도", "지하수"], index=["상수도", "지하수"].index(info.get("용수", "상수도")))
    drink = k14.selectbox("제공식수", ["정수기", "끓인 물", "기타"], index=["정수기", "끓인 물", "기타"].index(info.get("제공식수", "정수기")))
    serve = k15.selectbox("배식형태", ["교실배식", "식당배식", "식당+교실배식", "생활실(침실)배식", "기타"], index=["교실배식", "식당배식", "식당+교실배식", "생활실(침실)배식", "기타"].index(info.get("배식형태", "교실배식")))
    k16, k17 = st.columns(2)
    feed = k16.selectbox("급식·운영 형태", ["직접조리(직영)", "직접조리(위탁)", "외부조리(도시락/배달)", "가정형·경로당", "기타"], index=["직접조리(직영)", "직접조리(위탁)", "외부조리(도시락/배달)", "가정형·경로당", "기타"].index(info.get("급식형태", "직접조리(직영)")))
    interviewee = k17.text_input("면담자 (기관)", info.get("면담자", ""), placeholder="예: 원장 ○○○ / 조리원 ○○○")
    S.info = dict(info, 시설군=group, 시설명=org.strip(), 주소=addr.strip(), 방문회차=int(visit), 점검일자=date.isoformat(), 구분=kind, 회원유형=mem, 회원등급=grade, 세부유형=sub.strip(),
                  현원=int(cur), **{"1회최대급식인원": int(mx)}, 종사자=staff.strip(), 영양사근무=diet, 용수=water, 제공식수=drink, 배식형태=serve, 급식형태=feed, 면담자=interviewee.strip(), 점검자=USER["name"])
    info = S.info
    # 이전 방문 자동 조회
    if LOG_URL and org.strip() and st.button("🔎 이 시설의 이전 방문 기록 불러오기"):
        prev = L.previous_visit(LOG_URL, org)
        if prev:
            S.info["이전지도사항"] = str(prev.get("이번지도사항", "")); S.info["이전점검일"] = str(prev.get("점검일자", "")); S.info["이전득점률"] = prev.get("득점률")
            st.success(f"이전 방문 {prev.get('점검일자')} · {prev.get('체크리스트')} · 득점률 {prev.get('득점률')}% — 지도사항을 아래에 채웠습니다.")
        else:
            st.info("이전 기록이 없습니다 (첫 방문).")
    p1, p2 = st.columns([3, 1])
    S.info["이전지도사항"] = p1.text_area("이전 방문 시 지도사항", info.get("이전지도사항", ""), height=80)
    S.info["이전개선여부"] = p2.selectbox("이전 지도사항 개선 여부", ["해당없음(첫 방문)", "개선 완료", "일부 개선", "미개선"], index=["해당없음(첫 방문)", "개선 완료", "일부 개선", "미개선"].index(info.get("이전개선여부", "해당없음(첫 방문)")))
    info = S.info

if not info.get("시설명"):
    st.warning("시설명을 입력하면 점검 문항이 나타납니다."); st.stop()

# ── 2. 점검 입력 ──
st.markdown(f"### 2️⃣ 점검 — {cl['name']}")
cid = cl["id"]
scores, notes = S.scores, S.notes
flat = CK.flat_items(cl)
done = sum(1 for p, s_, it in flat if scores.get(CK.key(p, it)))
st.progress(done / max(len(flat), 1), text=f"입력 {done}/{len(flat)} 문항")


def _set_score(k, wkey):
    S.scores[k] = S[wkey]


def _set_note(k, wkey):
    S.notes[k] = S[wkey]


tabs = st.tabs([p["name"] for p in cl["parts"]]) if len(cl["parts"]) > 1 else [st.container()]
for p, tab in zip(cl["parts"], tabs):
    with tab:
        if mode.startswith("📱"):
            for s_ in p["sections"]:
                st.markdown(f"#### ▸ {s_['name']}" + (f"  <span style='font-size:0.8em;color:gray'>({s_['items'][0]['group']})</span>" if s_["items"] and s_["items"][0].get("group") else ""), unsafe_allow_html=True)
                for it in s_["items"]:
                    k = CK.key(p["name"], it); opts = CK.options(it)
                    st.markdown(f"**{it['no']}. {it['text']}**")
                    st.caption(f"근거: {it['basis'] or '권고'} · 배점 {'-'.join(map(str, it['scores']))}")
                    wkey = f"r::{cid}::{k}"
                    if scores.get(k) in opts:
                        S[wkey] = scores[k]
                    st.radio("점수", opts, key=wkey, horizontal=True, label_visibility="collapsed", index=None if scores.get(k) not in opts else None, on_change=_set_score, args=(k, wkey))
                    nkey = f"n::{cid}::{k}"
                    S[nkey] = notes.get(k, "")
                    st.text_input("비고", key=nkey, placeholder="관찰 내용·수치·면담 메모 (통지문 근거가 됩니다)", label_visibility="collapsed", on_change=_set_note, args=(k, nkey))
                    st.divider()
        else:
            rows = []
            for s_ in p["sections"]:
                for it in s_["items"]:
                    k = CK.key(p["name"], it)
                    rows.append({"구분": s_["name"], "번호": it["no"], "항목": it["text"], "근거": it["basis"] or "권고", "배점": "-".join(map(str, it["scores"])),
                                 "점수": scores.get(k, None), "비고": notes.get(k, ""), "_k": k, "_opts": CK.options(it)})
            df = pd.DataFrame(rows)
            all_opts = sorted({o for r_ in rows for o in r_["_opts"]}, key=lambda x: (-100 if x == CK.NA else -(CK.value_of(x) or 0)))
            ed = st.data_editor(df.drop(columns=["_k", "_opts"]), hide_index=True, use_container_width=True, height=min(80 + 36 * len(rows), 900), key=f"tbl::{cid}::{p['name']}",
                                column_config={"구분": st.column_config.TextColumn(width="small", disabled=True), "번호": st.column_config.TextColumn(width="small", disabled=True),
                                               "항목": st.column_config.TextColumn(width="large", disabled=True), "근거": st.column_config.TextColumn(width="medium", disabled=True),
                                               "배점": st.column_config.TextColumn(width="small", disabled=True),
                                               "점수": st.column_config.SelectboxColumn("점수", options=all_opts, width="medium", help="문항 배점에 맞는 값을 고르세요"),
                                               "비고": st.column_config.TextColumn(width="large")})
            for r_, (_, e) in zip(rows, ed.iterrows()):
                v = e["점수"]
                if isinstance(v, str) and v:
                    if v in r_["_opts"]:
                        scores[r_["_k"]] = v
                    else:
                        st.warning(f"{r_['번호']}번: '{v}'는 이 문항 배점({r_['배점']})에 없는 값입니다.")
                notes[r_["_k"]] = str(e["비고"]) if pd.notna(e["비고"]) else ""

S.setdefault("yn", {})
if cl.get("yn"):
    with st.expander("집단급식소 필수 확인 사항 (Y/N, 점수 미반영)", expanded=True):
        for it in cl["yn"]:
            yk = f"YN|{it['no']}"; wk = f"yn::{cid}::{yk}"
            if S.yn.get(yk) in ("Y", "N", "해당없음"):
                S[wk] = S.yn[yk]
            st.radio(f"{it['no']}. {it['text']}  _({it['basis']})_", ["Y", "N", "해당없음"], key=wk, horizontal=True, index=None, on_change=lambda yk=yk, wk=wk: S.yn.__setitem__(yk, S[wk]))

# ── 3. 결과 ──
summ = CK.summarize(cl, scores)
st.markdown("### 3️⃣ 결과")
cols = st.columns(len(summ["parts"]) + 2)
cols[0].metric("총점", f"{summ['got']} / {summ['app_max']}")
cols[1].metric("득점률", f"{summ['pct']} %", help="'해당없음' 문항은 만점에서 제외")
for c, p in zip(cols[2:], summ["parts"]):
    c.metric(p["name"], f"{p['got']} / {p['app_max']}")
if done < len(flat):
    st.warning(f"미입력 {len(flat) - done}문항은 0점으로 계산됩니다. 모두 입력한 뒤 확정하세요.")
defs = CK.deficiencies(cl, scores, notes); goods = CK.strengths(cl, scores, notes)
if defs:
    st.markdown("**감점 문항**")
    st.dataframe(pd.DataFrame(defs)[["no", "section", "text", "got", "max", "basis", "note"]].rename(columns={"no": "번호", "section": "구분", "text": "항목", "got": "점수", "max": "배점", "basis": "근거", "note": "비고"}), hide_index=True, use_container_width=True)

# ── 4. 통지문 ──
st.markdown("### 4️⃣ 지도 결과 통지문 (칭찬 + 개선사항)")
b1, b2 = st.columns([1, 3])
tone = b2.selectbox("어조", ["따뜻하고 격려하는", "정중하고 공식적인", "간결한"], label_visibility="collapsed")
if b1.button("🤖 AI 초안 만들기" if GEMINI_KEY else "📄 서식 초안 만들기", type="primary", use_container_width=True):
    with st.spinner("초안 작성 중…"):
        S.draft = R.ai_draft(GEMINI_KEY, info, cl, summ, defs, goods, tone) if GEMINI_KEY else R.template_draft(info, cl, summ, defs, goods)
d = S.draft
if d:
    st.caption("초안입니다. 고친 뒤 아래에서 확정하세요.")
    d["총평"] = st.text_area("총평", d.get("총평", ""), height=80)
    d["칭찬"] = [x for x in st.text_area("👍 잘하고 계신 점 (한 줄에 하나)", "\n".join(d.get("칭찬", [])), height=140).splitlines() if x.strip()]
    d["개선"] = [x for x in st.text_area("🔧 개선이 필요한 사항 (한 줄에 하나)", "\n".join(d.get("개선", [])), height=200).splitlines() if x.strip()]
    d["다음확인"] = [x for x in st.text_area("🔁 다음 방문 시 확인 사항", "\n".join(d.get("다음확인", [])), height=100).splitlines() if x.strip()]
    S.draft = d

# ── 5. 확정·내려받기 ──
st.markdown("### 5️⃣ 확정 · 내려받기")
ready = done == len(flat) and bool(d)
if not ready:
    st.caption("모든 문항 입력 + 통지문 초안 생성 후 확정할 수 있습니다.")
c1, c2, c3 = st.columns(3)
if c1.button("✅ 점검 확정 (구글 시트 기록)", type="primary", disabled=not ready, use_container_width=True):
    rid = S.get("rid") or uuid.uuid4().hex[:10]
    row = {"기록ID": rid, "점검일자": info["점검일자"], "시설군": group, "체크리스트": cl["name"], "시설명": info["시설명"], "주소": info.get("주소", ""), "방문회차": info["방문회차"], "구분": info["구분"],
           "세부유형": info.get("세부유형", ""), "현원": info.get("현원", ""), "점검자": USER["name"], "면담자": info.get("면담자", ""), "총점": summ["got"], "만점": summ["app_max"], "득점률": summ["pct"],
           "영역별점수": " · ".join(f"{p['name']} {p['got']}/{p['app_max']}" for p in summ["parts"]), "감점문항수": len(defs), "감점문항": ", ".join(x["no"] for x in defs),
           "이전지도사항": info.get("이전지도사항", ""), "이전개선여부": info.get("이전개선여부", ""), "이번지도사항": "\n".join(d.get("개선", [])), "칭찬": "\n".join(d.get("칭찬", [])),
           "다음확인": "\n".join(d.get("다음확인", [])), "총평": d.get("총평", ""), "필수확인YN": ", ".join(f"{k.split('|')[1]}:{v}" for k, v in S.get("yn", {}).items()), "저장일시": KST().strftime("%Y-%m-%d %H:%M")}
    items = [{"기록ID": rid, "점검일자": info["점검일자"], "시설명": info["시설명"], "체크리스트": cl["name"], "영역": p_, "구분": s_, "번호": it["no"], "항목": it["text"], "배점": it["scores"][0],
              "점수": ("" if scores.get(CK.key(p_, it)) == CK.NA else CK.value_of(scores.get(CK.key(p_, it)))), "비고": notes.get(CK.key(p_, it), "")} for p_, s_, it in flat]
    if LOG_URL:
        try:
            L.save_record(LOG_URL, row, items); S["rid"] = rid; L.fetch.clear()
            if S.get("draft_key"):
                try:
                    L.delete_draft(LOG_URL, S["draft_key"])
                except Exception:  # noqa: BLE001
                    pass
            st.success(f"확정 저장 완료 (기록ID {rid}). 아래에서 통지문·점검표를 내려받으세요.")
        except Exception as e:  # noqa: BLE001
            st.error(f"시트 저장 실패: {e} — 파일은 내려받을 수 있습니다.")
    else:
        st.info("LOG_WEBHOOK_URL이 없어 시트에는 저장하지 않았습니다.")
if d:
    fname = f"{info['시설명']}_{info['점검일자']}_{cl['name'][:12]}"
    c2.download_button("⬇️ 통지문 + 점검표 (워드)", R.to_docx(dict(info, 필수확인=S.get("yn", {})), cl, summ, d, defs, scores, notes), f"지도결과통지_{fname}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)
    c3.download_button("⬇️ 점검표 (엑셀)", R.to_xlsx(info, cl, summ, scores, notes), f"점검표_{fname}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

st.divider()
st.caption(f"체크리스트 출처: 식품의약품안전처·식생활안전관리원 2026 위생·안전·영양관리 체크리스트 해설서 · {CENTER}")
