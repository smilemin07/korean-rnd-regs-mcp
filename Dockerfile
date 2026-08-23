# v0.53.1 「NAS 라이브 이미지 의존성 lock」 — 기반 이미지 digest 고정 + requirements.lock 2단 설치.
#
# FROM: python:3.13-slim 태그가 아니라 digest로 고정한다(Docker는 digest만 신뢰·태그는 표기용). 2026-08-23 NAS 라이브
# (컨테이너 c6cfb3e8c12b·이미지 7ea3d1762177) 기반 RepoDigest 실측값 = Python 3.13.13·OpenSSL 3.5.6·pip 26.0.1.
# ★갱신 규율(2026-08-23 3-AI 합의): digest는 영구 동결이 아니라 「법령 시행 단계 정합 시리즈」(P4 v0.56.0) 종료까지의
# 기준선이다. 갱신 트리거 = ①도달 가능한 중대 CVE(Python·OpenSSL·Debian)와 수정 이미지 존재 ②Python/OpenSSL 보안
# 릴리스·지원 종료 ③digest 취득 불능 ④NAS 아키텍처 변경 ⑤시리즈 종료 후 계획된 재기준화. 갱신 시 digest만 바꾸지 말고
# 새 기반에서 requirements.lock 71종을 다시 산출해 전체 배포 게이트(후보 pip freeze 전수 대조·pip check·스모크)를 반복한다.
FROM python:3.13-slim@sha256:b04b5d7233d2ad9c379e22ea8927cd1378cd15c60d4ef876c065b25ea8fb3bf3

WORKDIR /app

# 1단: 제3자 의존성 71종을 requirements.lock(라이브 pip freeze 박제·재해석 금지)에서 정확 버전으로 설치.
#       소스보다 먼저 COPY해 소스만 바뀌는 릴리스(P2·P3·P4)에서 이 레이어를 재사용한다.
#       ★v0.53.0까지의 개별 핀 6종(fastmcp·uvicorn·python-multipart·requests·urllib3·cyclopts)은 lock으로 흡수됐다 —
#       Dockerfile에 `이름==버전` 핀을 다시 쓰지 말 것(핀 증식 금지 규율·tests/test_dockerfile_pins.py가 차단).
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

# 2단: 앱 자신만 --no-deps로 설치(런타임 의존성 재해석 0 — lock 밖 패키지가 섞여 들어오는 경로 차단) 후 pip check로
#       선언 의존성(Requires-Dist) 불일치·누락을 빌드 단계에서 fail-closed. (미선언 import는 pytest·후보 스모크가 담당)
#       ★고정 범위 밖: PEP 517 빌드 격리 환경의 빌드 백엔드(hatchling)는 설치 시점에 PyPI에서 별도 해석된다(빌드 시 아웃바운드
#       네트워크 필요·런타임 이미지에는 남지 않음). lock은 '버전 집합' 고정이며 wheel 바이트(해시)까지 고정하지는 않는다.
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/
RUN pip install --no-cache-dir --no-deps . && pip check

ENV PORT=8080
EXPOSE 8080

CMD ["korean-rnd-regs-mcp", "--http"]
