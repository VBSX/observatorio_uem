# Usa uma imagem oficial e leve do Python como base
FROM python:3.11-slim

# Define o diretorio de trabalho dentro do container
WORKDIR /app

# Copia primeiro o arquivo de dependencias para aproveitar o cache do Docker
COPY requirements.txt .

# Instala as dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o resto do codigo do projeto para dentro do container
COPY . .

# Expõe a porta 5000 para que possamos nos conectar a ela de fora do container
EXPOSE 5011

# O comando para iniciar a aplicação quando o container rodar
# Usamos waitress e host 0.0.0.0 para aceitar conexões externas ao container
CMD ["waitress-serve", "--host=0.0.0.0", "--port=5011", "app:app"]