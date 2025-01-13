# 베이스 이미지 선택
FROM python:3.10-slim

# 작업 디렉터리 설정
WORKDIR /app

# 의존성 파일 복사 및 설치
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 파일 복사
COPY . .

# 환경 변수 설정 (Railway에서 자동으로 설정)
ENV PYTHONUNBUFFERED=1

# 실행 명령
CMD ["python", "main.py"]
