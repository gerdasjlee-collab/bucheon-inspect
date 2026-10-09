# -*- coding: utf-8 -*-
"""체크리스트 정의 로딩·점수 계산. 데이터: checklists.json (build_checklists.py가 서식 hwpx에서 생성)."""
import json

import streamlit as st

GROUPS = ["어린이집", "기타시설(지역아동센터 등)", "유치원", "사회복지시설"]
NA = "해당없음"


@st.cache_data(show_spinner=False)
def load_all() -> list:
    return json.load(open("checklists.json", encoding="utf-8"))


def by_group(group: str) -> list:
    return [c for c in load_all() if c["group"] == group]


def get(cid: str) -> dict:
    return next(c for c in load_all() if c["id"] == cid)


def flat_items(cl: dict) -> list:
    """[(part_name, section_name, item)] 순서대로."""
    out = []
    for p in cl["parts"]:
        for s in p["sections"]:
            for it in s["items"]:
                out.append((p["name"], s["name"], it))
    return out


def key(part: str, it: dict) -> str:
    return f"{part}|{it['no']}"


def options(it: dict) -> list:
    """점수 선택지 문자열. 예: ['4점 (모두 충족)', '2점 (일부)', '0점 (미충족)', '해당없음']"""
    sc = it["scores"]
    labels = []
    for i, v in enumerate(sc):
        if len(sc) == 2:
            tag = "충족" if i == 0 else "미충족"
        else:
            tag = "모두 충족" if i == 0 else ("일부 충족" if i < len(sc) - 1 else "미충족")
        labels.append(f"{v}점 ({tag})")
    if it.get("na") or True:  # 모든 문항에 '해당없음' 허용(점검자 판단) — 만점에서 제외
        labels.append(NA)
    return labels


def value_of(label: str):
    if not label or label == NA:
        return None
    return int(label.split("점")[0])


def summarize(cl: dict, scores: dict) -> dict:
    """parts: [{name, got, max, applicable_max, pct}], total/… ; 미입력은 0점·만점 포함."""
    parts = []
    for p in cl["parts"]:
        got = mx = app_max = 0
        for s in p["sections"]:
            for it in s["items"]:
                top = it["scores"][0]
                mx += top
                v = scores.get(key(p["name"], it))
                if v == NA:
                    continue
                app_max += top
                got += value_of(v) or 0
        parts.append({"name": p["name"], "got": got, "max": mx, "app_max": app_max, "pct": round(got / app_max * 100) if app_max else 0})
    tg, tm, ta = sum(x["got"] for x in parts), sum(x["max"] for x in parts), sum(x["app_max"] for x in parts)
    return {"parts": parts, "got": tg, "max": tm, "app_max": ta, "pct": round(tg / ta * 100) if ta else 0}


def deficiencies(cl: dict, scores: dict, notes: dict) -> list:
    """감점 문항 목록 [(part, section, no, text, basis, got, max, note)] — 감점 큰 순."""
    out = []
    for part, sec, it in flat_items(cl):
        k = key(part, it)
        v = scores.get(k)
        if v == NA:
            continue
        got = value_of(v) or 0
        top = it["scores"][0]
        if got < top:
            out.append({"part": part, "section": sec, "no": it["no"], "text": it["text"], "basis": it["basis"], "got": got, "max": top, "note": notes.get(k, "")})
    return sorted(out, key=lambda d: d["max"] - d["got"], reverse=True)


def strengths(cl: dict, scores: dict, notes: dict) -> list:
    """만점 문항 중 비고가 있거나 배점이 큰 것 우선."""
    out = []
    for part, sec, it in flat_items(cl):
        k = key(part, it)
        v = scores.get(k)
        if v == NA or v is None:
            continue
        if value_of(v) == it["scores"][0]:
            out.append({"part": part, "section": sec, "no": it["no"], "text": it["text"], "max": it["scores"][0], "note": notes.get(k, "")})
    return sorted(out, key=lambda d: (bool(d["note"]), d["max"]), reverse=True)
