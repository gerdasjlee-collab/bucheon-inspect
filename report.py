# -*- coding: utf-8 -*-
"""지도 결과 통지문: AI 초안(Gemini) 또는 서식 초안 + 워드(docx)·엑셀 출력."""
import io
import datetime as dt

import checklist as CK

CENTER = "부천시어린이·사회복지급식관리지원센터"


def template_draft(info: dict, cl: dict, summ: dict, defs: list, goods: list) -> dict:
    """API 키 없을 때 쓰는 규칙 기반 초안."""
    praise = [f"{g['no']}. {g['text']}" + (f" — {g['note']}" if g["note"] else "") for g in goods[:5]]
    improve = [f"{d['no']}. {d['text']} ({d['got']}/{d['max']}점, {d['basis'] or '권고'})" + (f" — {d['note']}" if d["note"] else "") for d in defs]
    return {"칭찬": praise, "개선": improve, "다음확인": [f"{d['no']}. {d['text']}" for d in defs[:5]],
            "총평": f"{info.get('시설명','')}의 {cl['name']} 점검 결과 {summ['got']}/{summ['app_max']}점({summ['pct']}%)입니다."}


def ai_draft(api_key: str, info: dict, cl: dict, summ: dict, defs: list, goods: list, tone: str = "따뜻하고 격려하는") -> dict:
    """Gemini로 칭찬·개선·다음 확인사항·총평 초안. 실패 시 template_draft."""
    import json
    try:
        from google import genai
        client = genai.Client(api_key=api_key, vertexai=api_key.startswith("AQ."))
        body = {
            "시설": info.get("시설명"), "체크리스트": cl["name"], "점검일": info.get("점검일자"), "총점": f"{summ['got']}/{summ['app_max']} ({summ['pct']}%)",
            "영역별": [f"{p['name']} {p['got']}/{p['app_max']}" for p in summ["parts"]],
            "감점문항": [{"번호": d["no"], "항목": d["text"], "점수": f"{d['got']}/{d['max']}", "근거": d["basis"], "점검자비고": d["note"]} for d in defs],
            "만점문항_우수": [{"번호": g["no"], "항목": g["text"], "점검자비고": g["note"]} for g in goods[:12]],
            "이전지도사항": info.get("이전지도사항", ""), "이전개선여부": info.get("이전개선여부", ""),
        }
        prompt = (f"당신은 {CENTER}의 영양사입니다. 아래 급식소 위생·영양 지도점검 결과를 바탕으로 기관에 보내는 '지도 결과 통지문' 초안을 {tone} 어조의 한국어로 작성하세요. "
                  "반드시 JSON 객체 하나만 출력: {\"총평\": str, \"칭찬\": [str,...], \"개선\": [str,...], \"다음확인\": [str,...]}. "
                  "칭찬은 만점 문항·비고를 근거로 구체적으로 3~5개(점수만 나열하지 말 것). 개선은 감점 문항마다 1개씩: '문항번호. 무엇이 부족한지 → 어떻게 개선할지(법적 근거가 있으면 법명 포함, 권고면 권고라고)' 형식, 감점 큰 순. "
                  "다음확인은 다음 방문 때 확인할 사항 3~5개. 과장·추측 금지, 비고에 없는 사실을 지어내지 말 것.\n\n" + json.dumps(body, ensure_ascii=False))
        r = client.models.generate_content(model="gemini-3.5-flash-lite", contents=prompt)
        t = r.text.strip()
        t = t[t.find("{"): t.rfind("}") + 1]
        d = json.loads(t)
        for k in ("칭찬", "개선", "다음확인"):
            d[k] = [str(x) for x in d.get(k, [])]
        d["총평"] = str(d.get("총평", ""))
        return d
    except Exception:  # noqa: BLE001
        return template_draft(info, cl, summ, defs, goods)


def to_docx(info: dict, cl: dict, summ: dict, draft: dict, defs: list, scores: dict, notes: dict) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    doc = Document()
    st_ = doc.styles["Normal"]; st_.font.name = "맑은 고딕"; st_.font.size = Pt(10.5)
    st_.element.rPr.rFonts.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", "맑은 고딕")
    h = doc.add_heading("급식소 위생·영양 지도점검 결과 통지", 0); h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t = doc.add_table(rows=0, cols=4); t.style = "Table Grid"
    rows = [("시설명", info.get("시설명", ""), "점검일자", info.get("점검일자", "")), ("체크리스트", cl["name"], "방문회차", info.get("방문회차", "")),
            ("점검자", info.get("점검자", ""), "면담자", info.get("면담자", "")), ("총점", f"{summ['got']} / {summ['app_max']}점 ({summ['pct']}%)", "영역별", " · ".join(f"{p['name']} {p['got']}/{p['app_max']}" for p in summ["parts"]))]
    for a, b, c, d in rows:
        cells = t.add_row().cells
        cells[0].text, cells[1].text, cells[2].text, cells[3].text = a, str(b), c, str(d)
    doc.add_paragraph()
    doc.add_heading("1. 총평", 1); doc.add_paragraph(draft.get("총평", ""))
    doc.add_heading("2. 잘하고 계신 점", 1)
    for x in draft.get("칭찬", []): doc.add_paragraph(x, style="List Bullet")
    doc.add_heading("3. 개선이 필요한 사항", 1)
    for x in draft.get("개선", []): doc.add_paragraph(x, style="List Number")
    doc.add_heading("4. 다음 방문 시 확인 사항", 1)
    for x in draft.get("다음확인", []): doc.add_paragraph(x, style="List Bullet")
    if info.get("이전지도사항"):
        doc.add_heading("5. 이전 방문 지도사항 및 개선 여부", 1)
        doc.add_paragraph(f"이전 지도사항: {info['이전지도사항']}"); doc.add_paragraph(f"개선 여부: {info.get('이전개선여부', '')}")
    doc.add_paragraph()
    doc.add_heading("붙임. 점검표", 1)
    t2 = doc.add_table(rows=1, cols=5); t2.style = "Table Grid"
    for i, hname in enumerate(["번호", "항목", "배점", "점수", "비고"]): t2.rows[0].cells[i].text = hname
    for part, sec, it in CK.flat_items(cl):
        k = CK.key(part, it); v = scores.get(k)
        got = "N/A" if v == CK.NA else ("" if v is None else str(CK.value_of(v)))
        c = t2.add_row().cells
        c[0].text, c[1].text, c[2].text, c[3].text, c[4].text = it["no"], f"[{sec}] {it['text']}", str(it["scores"][0]), got, notes.get(k, "")
    if cl.get("yn"):
        doc.add_paragraph()
        doc.add_heading("붙임 2. 집단급식소 필수 확인 사항", 2)
        yn = info.get("필수확인", {})
        for it in cl["yn"]:
            doc.add_paragraph(f"{it['no']}. {it['text']} — {yn.get('YN|' + it['no'], '미확인')}")
    doc.add_paragraph()
    p = doc.add_paragraph(f"{dt.date.today().strftime('%Y년 %m월 %d일')}\n{CENTER}"); p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    buf = io.BytesIO(); doc.save(buf); return buf.getvalue()


def to_xlsx(info: dict, cl: dict, summ: dict, scores: dict, notes: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook(); ws = wb.active; ws.title = "점검표"
    ws["A1"] = f"{cl['name']} 점검표 — {info.get('시설명', '')}"; ws["A1"].font = Font(bold=True, size=13)
    r = 2
    for k_, v_ in info.items():
        if v_ not in ("", None): ws.cell(row=r, column=1, value=k_).font = Font(bold=True); ws.cell(row=r, column=2, value=str(v_)); r += 1
    r += 1
    hdr = ["영역", "구분", "번호", "항목", "근거", "배점", "점수", "비고"]
    for j, h in enumerate(hdr, 1):
        c = ws.cell(row=r, column=j, value=h); c.font = Font(bold=True); c.fill = PatternFill("solid", fgColor="E8F0FE")
    for part, sec, it in CK.flat_items(cl):
        r += 1; k = CK.key(part, it); v = scores.get(k)
        got = "N/A" if v == CK.NA else ("" if v is None else CK.value_of(v))
        for j, val in enumerate([part, sec, it["no"], it["text"], it["basis"], it["scores"][0], got, notes.get(k, "")], 1):
            ws.cell(row=r, column=j, value=val).alignment = Alignment(wrap_text=True, vertical="top")
    r += 1; ws.cell(row=r, column=4, value="총점").font = Font(bold=True); ws.cell(row=r, column=6, value=summ["app_max"]); ws.cell(row=r, column=7, value=summ["got"]).font = Font(bold=True)
    for j, w in enumerate([12, 10, 6, 60, 24, 6, 6, 30], 1): ws.column_dimensions[chr(64 + j)].width = w
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()
