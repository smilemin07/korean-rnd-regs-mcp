FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

# uvicorn·python-multipart는 streamable-http(--http) 서버 기동에 직접 관여하는 transitive dep.
# 라이브(0.1.5) 이미지와 동일한 검증 버전(uvicorn 0.48.0·python-multipart 0.0.30)으로 핀 →
# 재빌드 시 전이 의존성 자동 업데이트로 인한 서버 거동 변화 차단(재현 가능한 --http 이미지).
# v0.1.6 배포는 host networking 스모크로 정상 바인딩(406·initialize serverInfo.version=0.1.6) 확인.
RUN pip install --no-cache-dir . "uvicorn==0.48.0" "python-multipart==0.0.30"

ENV PORT=8080
EXPOSE 8080

CMD ["korean-rnd-regs-mcp", "--http"]
