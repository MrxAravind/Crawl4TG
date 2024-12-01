FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y \
    python3 \
    python3-pip \
    git \
    ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages
RUN crawl4ai-setup
RUN playwright install-deps 


# Copy only files from the current directory (excluding directories)
COPY *.py ./
COPY *.sh ./
COPY .env ./

# Command to run your application (adjust as necessary)
CMD ["python3", "run.py"]
