FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

# fastmcp는 서버 프레임워크 직접 dep, uvicorn·python-multipart는 streamable-http(--http) 서버 기동에 직접 관여하는 transitive dep.
# 라이브 검증 버전으로 핀(fastmcp 3.4.2 = v0.2.1 NAS 라이브 이미지 실측 / uvicorn 0.48.0·python-multipart 0.0.30 = 0.1.5 라이브와 동일) →
# 재빌드 시 전이 의존성 자동 업데이트로 인한 서버 거동 변화 차단(재현 가능한 --http 이미지).
# v0.1.6 배포는 host networking 스모크로 정상 바인딩(406·initialize serverInfo.version=0.1.6) 확인.
# v0.53.0: requests·urllib3 핀 추가(NAS 라이브 v0.52.0 컨테이너 실측 2026-08-23 = requests 2.34.2·urllib3 2.7.0).
# 근거 = v0.48.0 B3(thread-local keep-alive Session)의 안전 불변식이 두 패키지의 기본값 의미론(trust_env·adapter retry·
# pool sizing)에 의존하는데 재빌드마다 최신으로 풀리고 있었음(v0.49.0 재빌드에서 간접 deps 8건 자연 상승 실측).
# ★이 핀은 이 이미지(NAS 라이브)의 HTTP 클라이언트 조합만 고정한다 — PyPI·uvx 소비자의 의존성 해석은 pyproject 범위를 따름.
# cyclopts==4.23.1: v0.53.0 배포 게이트(pip freeze 라이브 전수 대조)에서 유일하게 드리프트한 패키지(후보 4.23.2)를 라이브 실측값으로 동결.
# fastmcp CLI(fastmcp/cli/*) 전용 라이브러리라 본 서버(`--http`) 런타임은 import하지 않음(python -v 실측 0건) — 동결은 "이미지 = 라이브" 증명을 위한 것.
# ★임시 재현성 핀(fastmcp==3.4.2에 종속) — fastmcp 핀을 바꿀 때 반드시 재검토. 다음 재빌드에서 다른 패키지가 드리프트하면 핀을 하나 더
# 늘리지 말고 게이트를 중단한 뒤 전체 lock(로드맵 단계 4 완결형) 전환 또는 별도 예외심사를 거칠 것(2026-08-23 Codex 조건).
RUN pip install --no-cache-dir . "fastmcp==3.4.2" "uvicorn==0.48.0" "python-multipart==0.0.30" "requests==2.34.2" "urllib3==2.7.0" "cyclopts==4.23.1"

ENV PORT=8080
EXPOSE 8080

CMD ["korean-rnd-regs-mcp", "--http"]
