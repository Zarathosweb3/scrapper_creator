# Utilise une image Python légère
FROM python:3.9-slim-buster

# Installe Chromium et ChromeDriver pour Selenium
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Définit le répertoire de travail
WORKDIR /app

# Copie les fichiers de dépendances Python
COPY requirements.txt /app/requirements.txt

# Installe les dépendances
RUN pip install --no-cache-dir -r requirements.txt

# Copie le reste du code dans /app
COPY . /app

# Commande de lancement du bot
CMD ["python", "main.py"]