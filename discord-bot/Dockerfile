FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if any are needed (none for now, python-slim is fine)
# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY bot.py .

# Run the bot
CMD ["python", "bot.py"]
