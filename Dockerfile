FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    HOST=0.0.0.0 \
    PORT=8000

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY run.py .
COPY app ./app

# DB·로그·쿠키 키는 컨테이너 밖에 보관 (재빌드해도 유지)
VOLUME /app/data
EXPOSE 8000
CMD ["python", "run.py"]
