FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

# fastmcp는 서버 프레임워크 직접 dep, uvicorn·python-multipart는 streamable-http(--http) 서버 기동에 직접 관여하는 transitive dep.
# 라이브 검증 버전으로 핀(fastmcp 3.4.2 = v0.2.1 NAS 라이브 이미지 실측 / uvicorn 0.48.0·python-multipart 0.0.30 = 0.1.5 라이브와 동일) →
# 재빌드 시 전이 의존성 자동 업데이트로 인한 서버 거동 변화 차단(재현 가능한 --http 이미지).
# v0.1.6 배포는 host networking 스모크로 정상 바인딩(406·initialize serverInfo.version=0.1.6) 확인.
RUN pip install --no-cache-dir . "fastmcp==3.4.2" "uvicorn==0.48.0" "python-multipart==0.0.30"

ENV PORT=8080
EXPOSE 8080

CMD ["korean-rnd-regs-mcp", "--http"]
