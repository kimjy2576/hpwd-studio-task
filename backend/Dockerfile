FROM python:3.11-slim

WORKDIR /app

# 의존성 먼저 복사 → Docker layer caching 활용
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 서버 코드 + 컴포넌트
COPY server.py .
COPY components/ ./components/
# Design Studio 모듈 (calibration / validation / sessions)
COPY design/ ./design/
# Sessions 저장 디렉토리 (.gitkeep만 있어도 디렉토리 생성)
COPY sessions/ ./sessions/

# Railway는 PORT 환경변수로 포트 지정
ENV PORT=8000
EXPOSE 8000

# 실행
CMD ["python", "server.py"]
