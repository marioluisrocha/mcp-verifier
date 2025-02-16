# Use Python 3.12 slim image as the base
FROM python:3.12-slim

# Set working directory in the container
WORKDIR /app

# Copy requirements file
# COPY requirements.txt .

# Install dependencies
# RUN pip install --no-cache-dir -r requirements.txt
RUN pip install poetry
RUN poetry config virtualenvs.create false
RUN poetry install
# Copy the rest of the application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose the port the app runs on
EXPOSE 8501

# Command to run the application
CMD ["poetry", "run", "streamlit", "run", "src/mcp_verifier/ui.py"] 
