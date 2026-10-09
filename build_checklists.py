# -*- coding: utf-8 -*-
"""서식 hwpx 2개 → checklists.json (11종). 새 서식이 오면 이 스크립트만 다시 실행."""
import json, re, sys
import xml.etree.ElementTree as ET
NS = {'hp': 'http://www.hancom.co.kr/hwpml/2011/paragraph'}
def txt(e): return "".join(t.text or "" for t in e.iter('{%s}t' % NS['hp'])).strip()

def tables(path):
    root = ET.parse(path).getroot()
    out = []
    for tbl in root.iter('{%s}tbl' % NS['hp']):
        rows = [[re.sub(r"\s+", " ", txt(tc)) for tc in tr.findall('hp:tc', NS)] for tr in tbl.findall('hp:tr', NS)]
        out.append(rows)
    return out

def parse_items(rows):
    """점수표(항목|근거|배점|비고) → sections [{name, group, items[{no,text,basis,scores,na}]}], total"""
    secs, cur, group, total = [], None, "", None
    for r in rows:
        cells = [c for c in r]
        joined = " ".join(cells)
        if not joined.strip() or cells[0].startswith("항") and "근거" in joined:
            continue
        if cells[0].startswith("총"):
            m = re.search(r"/\s*(\d+)\s*점", joined); total = int(m.group(1)) if m else None
            continue
        # 그룹 표시(공통/직영/직접조리만 해당/가정형만 해당) — 첫 셀이 그룹명이고 나머지가 섹션명 또는 문항
        if cells[0] in ("공통", "직영", "직접조리만 해당", "가정형만 해당") and len(cells) >= 2:
            group = cells[0]; cells = cells[1:]
        # 섹션행: 문항번호 없이 한 칸(또는 빈 뒤칸)
        if not re.match(r"^\d+(-\d+)?\.", cells[0]) and (len(cells) == 1 or all(not c for c in cells[1:])):
            name = re.sub(r"^[ⅠⅡⅢⅣⅤⅥ]+\.\s*", "", cells[0]).replace(" ", "")
            cur = {"name": name, "items": []}; secs.append(cur); continue
        m = re.match(r"^(\d+(?:-\d+)?)\.\s*(.*)$", cells[0])
        if not m:
            continue
        no, text = m.group(1), m.group(2)
        basis = cells[1] if len(cells) > 1 else ""
        sc = cells[2] if len(cells) > 2 else ""
        scores = [int(x) for x in re.findall(r"\d+", sc)]
        na = "N/A" in sc
        if not scores:  # 9. 식품 알레르기... 상위 문항 (하위 9-1, 9-2 있음)
            continue
        if cur is None:
            cur = {"name": "일반", "items": []}; secs.append(cur)
        cur["items"].append({"no": no, "text": text.strip(), "basis": re.sub(r"(?<=[조장률])(?=(노인복지법|장애인복지법|식품위생법|영유아보육법|아동복지법|학교급식법|유아교육법|청소년|농수산물|식품 등의|감염병|학교보건법|어린이식생활|교육관련))", " ", basis), "scores": sorted(set(scores), reverse=True), "na": na, "group": group})
    return secs, total

def parse_yn(rows):
    items = []
    for r in rows[1:]:
        m = re.match(r"^(\d+)\.\s*(.*)$", r[0])
        if m: items.append({"no": m.group(1), "text": m.group(2), "basis": r[1] if len(r) > 1 else ""})
    return items

def basic_fields(rows):
    """기본정보표 → 라벨 목록(선택지 포함)"""
    fields = []
    for r in rows:
        i = 0
        while i < len(r):
            lab = r[i].replace(" ", "")
            val = r[i + 1] if i + 1 < len(r) else ""
            if lab and lab not in ("", "계") and not lab.startswith("□") and not lab.startswith("⏨"):
                opts = [o.strip(" ,") for o in re.split(r"[⏨□■]", val) if o.strip(" ,")] if ("⏨" in val or "□" in val) else []
                fields.append({"label": lab, "options": opts, "hint": "" if opts else val})
            i += 2
    return fields

CL = []  # (id, name, 시설군, 기본정보표 index, 점수표 indexes, yn index)
src = sys.argv[1:] if len(sys.argv) > 2 else ["2026년 어린이급식소 체크리스트 서식.hwpx", "2026 사회복지급식소 체크리스트 서식(수정)251231.hwpx"]
import zipfile, io, os, tempfile
def load(hwpx):
    with zipfile.ZipFile(hwpx) as z:
        data = z.read("Contents/section0.xml")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xml"); tmp.write(data); tmp.close()
    return tables(tmp.name)
A = load(src[0]); B = load(src[1])

def mk(id_, name, grp, basic, scores, yn=None, note=""):
    parts = []
    for s in scores:
        secs, total = parse_items(s["rows"])
        parts.append({"name": s["name"], "sections": secs, "total": total})
    return {"id": id_, "name": name, "group": grp, "basic": basic_fields(basic), "parts": parts,
            "yn": parse_yn(yn) if yn else [], "note": note}

# --- 어린이 서식 테이블 순서(0-base): 0기본,1위생43,2지도 | 3기본,4위생29,5지도 | 6기본,7위생21,8YN,9영양8,10지도 | 11기본,12위생14,13영양4,14지도 | 15기본,16영양14,17지도 | 18기본,19위생42,20지도 | 21기본,22영양13,23지도
R = lambda T, i, n: {"name": n, "rows": T[i]}
CL += [
 mk("child_hyg_group", "어린이집(집단급식소) 위생·안전관리", "어린이집", A[0], [R(A,1,"위생·안전관리")], note="현원 50인 이상 등 집단급식소 신고 어린이집"),
 mk("child_hyg_small", "어린이집(소규모급식소) 위생·안전관리", "어린이집", A[3], [R(A,4,"위생·안전관리")], note="집단급식소 미신고 소규모 어린이집"),
 mk("child_nut", "어린이집 영양관리", "어린이집", A[15], [R(A,16,"영양관리")]),
 mk("other_over20", "기타시설(정원 20인 초과) 위생·안전·영양관리", "기타시설(지역아동센터 등)", A[6], [R(A,7,"위생·안전관리"), R(A,9,"영양관리")], yn=A[8]),
 mk("other_under20", "기타시설(정원 20인 이하) 위생·안전·영양관리", "기타시설(지역아동센터 등)", A[11], [R(A,12,"위생·안전관리"), R(A,13,"영양관리")]),
 mk("kinder_hyg", "유치원 위생·안전관리", "유치원", A[18], [R(A,19,"위생·안전관리")]),
 mk("kinder_nut", "유치원 영양관리", "유치원", A[21], [R(A,22,"영양관리")]),
]
# --- 사회복지 서식: 0기본,1위생29,2지도 | 3기본,4영양10,5지도 | 6기본,7외부조리(위생18+영양7),8지도 | 9기본,10가정형(위생14+영양5),11지도
def split_two(rows):
    """한 표에 Ⅰ.위생 … 총점 … Ⅱ.영양 … 총점 → 두 부분"""
    parts, cur = [], []
    for r in rows:
        cur.append(r)
        if r[0].startswith("총"):
            parts.append(cur); cur = []
    return parts
w, n = split_two(B[7]); w2, n2 = split_two(B[10])
CL += [
 mk("welfare_hyg", "사회복지시설(직접조리) 위생·안전관리", "사회복지시설", B[0], [R(B,1,"위생·안전관리")]),
 mk("welfare_nut", "사회복지시설(직접조리) 영양관리", "사회복지시설", B[3], [R(B,4,"영양관리")]),
 mk("welfare_outsourced", "사회복지시설(외부조리·도시락/배달) 위생·영양관리", "사회복지시설", B[6], [{"name":"위생·안전관리","rows":[B[7][0]]+w}, {"name":"영양관리","rows":[B[7][0]]+n}]),
 mk("welfare_home", "사회복지시설(가정형·경로당) 위생·영양관리", "사회복지시설", B[9], [{"name":"위생·안전관리","rows":[B[10][0]]+w2}, {"name":"영양관리","rows":[B[10][0]]+n2}]),
]
for c in CL:
    for p in c["parts"]:
        for s in p["sections"]:
            for i in s["items"]:
                if not i["text"]: i["text"] = "식품등의 원료 및 제품 중 부패･변질이 되기 쉬운 것은 냉동･냉장시설에 보관･관리"
json.dump(CL, open("checklists.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
for c in CL:
    cnt = sum(len(s["items"]) for p in c["parts"] for s in p["sections"])
    tot = [p["total"] for p in c["parts"]]
    calc = [sum(i["scores"][0] for s in p["sections"] for i in s["items"]) for p in c["parts"]]
    print(f'{c["id"]:20s} {c["name"]:40s} 문항 {cnt:3d}  총점표기 {tot}  배점합 {calc}  YN {len(c["yn"])}')
