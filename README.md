# 급식소 위생·영양 지도점검 도우미 (부천시어린이·사회복지급식관리지원센터)
식약처 2026 체크리스트 11종 현장 입력 → 자동 집계 → AI 통지문(칭찬+개선) → 워드/엑셀 → 구글 시트 기록·통계.
- app.py 화면 / checklist.py 문항·점수 / report.py 통지문·문서 / inspectlog.py 시트 기록·관리자 통계
- checklists.json: build_checklists.py 가 서식 hwpx에서 생성
- Secrets: ACCESS_CODE, ADMIN_CODE, GEMINI_API_KEY(선택), LOG_WEBHOOK_URL
