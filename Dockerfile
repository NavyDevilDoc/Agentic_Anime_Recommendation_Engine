# Use the official Python 3.12 lightweight image
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Railway assigns $PORT dynamically; Streamlit reads it at runtime
EXPOSE ${PORT:-8501}

# Launch Streamlit using Railway's PORT, falling back to 8501 for local dev
CMD streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true
