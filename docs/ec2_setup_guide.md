# EC2 g6e.xlarge — Full Setup Guide
## Transcription Engine with VibeVoice + Gemma on AWS

---

## Phase 1: First SSH Connection

After launching your EC2 instance:

```bash
ssh -i your-key.pem ubuntu@<EC2_PUBLIC_IP>
```

Once inside, first verify the GPU is visible:
```bash
nvidia-smi
```
You should see the L40S listed with 48 GB. If not, the AMI did not include drivers and you need to install them (see Appendix A).

---

## Phase 2: Install System Packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl wget ffmpeg tmux htop build-essential
```

> [!NOTE]
> **tmux** is critical. It lets your batch job keep running even if your SSH connection drops. Always run long jobs inside a `tmux` session.

---

## Phase 3: Install Miniconda (Python environment)

```bash
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh
bash miniconda.sh -b -p $HOME/miniconda
echo 'export PATH="$HOME/miniconda/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
conda --version  # verify it works
```

Create and activate your environment (matching your local setup):
```bash
conda create -n genesis-kb python=3.11 -y
conda activate genesis-kb
```

---

## Phase 4: Install Docker & Docker Compose

Docker runs your PostgreSQL database.

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Allow your user to run docker without sudo
sudo usermod -aG docker $USER
newgrp docker  # apply without re-login

# Install Docker Compose v2
sudo apt install -y docker-compose-plugin
docker compose version  # verify
```

---

## Phase 5: Install Ollama (for Gemma)

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Verify it installed:
```bash
ollama --version
```

Start the Ollama service in the background:
```bash
ollama serve &
```

Pull the Gemma model you use:
```bash
ollama pull gemma4:12b
```

---

## Phase 6: Clone Your Repository

```bash
git clone https://github.com/<YOUR_USERNAME>/transcription_engine.git
cd transcription_engine
```

Install the project:
```bash
conda activate genesis-kb
pip install -e .
pip install -r requirements.txt
```

---

## Phase 6.1: Setup Tailscale and SOCKS Proxy

To securely route traffic and bypass IP blocks, you must connect the EC2 instance and your local machine via Tailscale and run a local proxy.

1. **Install Tailscale on both devices**
   On the EC2 instance, run:
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```
   *Make sure you also download and connect Tailscale on your local.*

2. **Start the SOCKS Proxy Server**
   Start a `tmux` session and run the proxy on port 1080 (this requires `microsocks` to be installed, which will happen in Phase 6):
   ```bash
   tmux new -s proxy
   microsocks -p 1080
   ```
   *Detach from tmux by pressing `Ctrl+B`, then `D`.*

3. **Verify IP and Update Config**
   Get the Tailscale IP of your system:
   ```bash
   tailscale ip -4
   ```
   *Make sure this exact Tailscale IP is the one you enter in your `.env` file under `PROXY_URL` (e.g., `socks5h://100.104.77.101:1080`). You must also use this IP to SSH securely in the future!*

---

## Phase 7: Configure `.env`

Create your `.env` file in the project root:
```bash
cd ~/transcription_engine
cp env.example .env
nano .env
```

Fill in these values:
```ini
# Server
TRANSCRIPTION_SERVER_URL=http://localhost:8000
PROFILE="development"
BTC_TRANSCRIPTS_URL="https://btctranscripts.com"

# Database — local Docker PostgreSQL
DATABASE_URL=postgresql://bitcoin:bitcoin@127.0.0.1:5434/transcription_engine

# HuggingFace — required for VibeVoice model download
HF_TOKEN=hf_your_token_here

# Gemma model
GEMMA_MODEL=gemma4:12b

# Leave empty if not using
GOOGLE_API_KEY=
OPENAI_API_KEY=
DEEPGRAM_API_KEY=

# Use proxy and update proxy url
USE_PROXY=true
PROXY_URL="socks5h://100.104.77.101:1080"
```

---

## Phase 8: Configure `config.ini`

```bash
cp config.ini.example config.ini
nano config.ini
```

Set it exactly like this for VibeVoice + Gemma:
```ini
[DEFAULT]
asr_provider = vibevoice
diarize = True
summarize = True
github = False
save_to_markdown = True
needs_review = False
one_sentence_per_line = True
vibevoice_chunk_length = 180

llm_provider = gemma
llm_correction_model = gemma4:12b
llm_summary_model = gemma4:12b

[development]
verbose_logging = True
server_mode = dev
server_verbose = True
```

---

## Phase 9: Start the PostgreSQL Database

```bash
cd ~/transcription_engine
docker compose up -d postgres
```

Verify it's healthy:
```bash
docker compose ps
```

Initialize the DB tables (one-time only):
```bash
tstbtc db init
```

---

## Phase 10: Start the Transcription Server

```bash
# Inside a tmux session so it survives SSH disconnects
tmux new -s server

conda activate genesis-kb
cd ~/transcription_engine
tstbtc server start

# Detach from tmux: Ctrl+B, then D
```

Verify the server is running:
```bash
curl http://localhost:8000/health
```

---

## Phase 11: Run the Batch Transcription

Copy your `filtered_videos.txt` file to the EC2 instance:

Run this batch script directly in the terminal:
```bash
#!/bin/bash
# batch_transcribe.sh
# Reads filtered_videos.txt and transcribes each video one by one.

INPUT_FILE="filtered_videos.txt"
LOG_FILE="batch_run.log"
COUNTER=0
TOTAL=$(grep -c "http" "$INPUT_FILE")

echo "=== Batch Transcription Started at $(date) ===" | tee -a "$LOG_FILE"
echo "Total videos to process: $TOTAL" | tee -a "$LOG_FILE"

while IFS= read -r url || [[ -n "$url" ]]; do
    # Skip empty lines
    [[ -z "$url" ]] && continue

    COUNTER=$((COUNTER + 1))
    echo "" | tee -a "$LOG_FILE"
    echo "[$COUNTER/$TOTAL] Processing: $url" | tee -a "$LOG_FILE"
    echo "Started at: $(date)" | tee -a "$LOG_FILE"

    tstbtc transcribe "$url" \
        --asr-provider vibevoice \
        --llm-provider gemma \
        --loc "bitcoin_conferences" \
        --username "John" \
        --diarize --markdown --summarize --correct \
        2>&1 | tee -a "$LOG_FILE"

    EXIT_CODE=${PIPESTATUS[0]}

    if [ $EXIT_CODE -eq 0 ]; then
        echo "SUCCESS: $url"
    else
        echo "FAILED (exit $EXIT_CODE): $url"
        echo "Failed at: $(date)" | tee -a "$LOG_FILE"
    fi

    echo "Completed at: $(date)" | tee -a "$LOG_FILE"
    # Small pause between videos to let Ollama fully unload
    sleep 5

done < "$INPUT_FILE"

echo "" | tee -a "$LOG_FILE"
echo "=== Batch Transcription Finished at $(date) ===" | tee -a "$LOG_FILE"
```

Save the above as `batch_transcribe.sh` on the EC2, then run it:
```bash
chmod +x batch_transcribe.sh
./batch_transcribe.sh
```

Detach from tmux so it keeps running even if you close your laptop:
```
Ctrl+B, then D
```

### Check DB records saved:
```bash
docker exec -t $(docker compose ps -q postgres) psql -U bitcoin -d transcription_engine -c "SELECT COUNT(*) FROM transcripts;"
```
---

## Important Notes

| Topic | Note |
|---|---|
| **VibeVoice** | First video will be slow — it downloads the HuggingFace model (~2 GB). After that it's cached. |
| **Gemma memory** | On L40S (48 GB), NO memory cycling needed. Both VibeVoice and Gemma can co-exist. You can raise `vibevoice_chunk_length` to `300` or even disable chunking. |
| **Failed videos** | If a video fails, re-run the script with only the `batch_failed.txt` URLs. The pipeline is resumable. |

---

## Appendix A: Manual NVIDIA Driver Install (only if needed)

If `nvidia-smi` fails after SSH, install drivers manually:
```bash
sudo apt install -y nvidia-driver-535
sudo reboot
# After reboot, SSH back in
nvidia-smi
```

---

## Appendix B: If the Server Keeps Crashing

Check server logs:
```bash
tail -n 100 logs/server_dev.log
```

Common fix — ensure Ollama is running before starting the server:
```bash
ollama serve &
sleep 3
tstbtc server start
```
