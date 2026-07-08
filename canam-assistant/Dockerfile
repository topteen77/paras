# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Using --no-cache-dir reduces image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
# This assumes your Dockerfile is in the root of your project (canam-assistant/)
# and will copy main.py, common/, handleAudioCalls/, etc.
COPY . .

# Expose the port the app runs on.
# Your application (with the suggested change to main.py) will listen on the port
# specified by the PORT environment variable (Cloud Run provides this, often 8080).
EXPOSE 8080

# Define the command to run the application.
# This will execute `python main.py`, which in turn starts the uvicorn server
# configured to listen on the host and port defined in your main.py's uvicorn.run() call.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
