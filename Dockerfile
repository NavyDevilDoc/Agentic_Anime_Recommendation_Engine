# Use the official Python 3.12 lightweight image
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Hugging Face Spaces requires applications to run on port 7860
EXPOSE 7860

# Command to launch the Streamlit app on the correct port and host
CMD ["streamlit", "run", "app.py", "--server.port=7860", "--server.address=0.0.0.0"]