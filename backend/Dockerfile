# MedBook backend image. Build from the medbook/ folder (docker compose does this):
#   docker build -f backend/Dockerfile -t medbook-backend .
# Build args:
#   WITH_XLMR=1   install CPU torch + transformers so the XLM-R model in results/*/model is used (default)
#                 WITH_XLMR=0 gives a ~400 MB image that runs the TF-IDF/CRF baseline NLU instead
#   TORCH_INDEX_URL  where torch comes from (default: the CPU-only wheels, ~200 MB instead of ~2.5 GB with CUDA)
#   WITH_VOICE=1  install faster-whisper + soundfile for /api/voice and /api/tts (weights download on first use;
#                 spoken replies also need WITH_XLMR=1 for torch)
FROM python:3.12-slim

ARG WITH_XLMR=1
ARG WITH_VOICE=0
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/hf-cache TZ=Asia/Karachi

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt \
 && if [ "$WITH_XLMR" = "1" ]; then \
      pip install --index-url "$TORCH_INDEX_URL" torch \
      && pip install "transformers>=4.40" sentencepiece; fi \
 && if [ "$WITH_VOICE" = "1" ]; then pip install faster-whisper "av<16" soundfile; fi

# Data the NLU needs at start-up: lexicons, the dataset (baseline training) and trained model weights.
COPY data_gen/ /app/data_gen/
COPY models/ /app/models/
COPY data/dataset_v1/ /app/data/dataset_v1/
COPY results/ /app/results/
COPY backend/ /app/backend/

RUN useradd --create-home --uid 1000 medbook \
 && mkdir -p /hf-cache /app/backend/data /app/backend/.cache \
 && chown -R medbook /hf-cache /app/backend/data /app/backend/.cache
USER medbook

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
# One worker by default: each worker loads its own copy of XLM-R (~1 GB RAM). With REDIS_URL set,
# WEB_CONCURRENCY=2+ is safe because conversations live in Redis, not in the worker.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-1} --proxy-headers"]
