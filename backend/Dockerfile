FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency installation
RUN pip install uv

COPY pyproject.toml .
RUN uv pip install --system --no-cache -e .

COPY . .

RUN mkdir -p data/entities data/simulations

EXPOSE 5001

CMD ["python", "run.py"]
