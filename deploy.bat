@echo off
set IMAGE_NAME=meu-flask-app
set CONTAINER_NAME=flask-container

echo.
echo >>> Puxando as ultimas alteracoes do repositorio...
git pull origin master

echo.
echo >>> Construindo a nova imagem Docker...
docker build -t %IMAGE_NAME% .

echo.
echo >>> Parando e removendo o container antigo (se existir)...
docker stop %CONTAINER_NAME% > nul 2>&1
docker rm %CONTAINER_NAME% > nul 2>&1

echo.
echo >>> Iniciando o novo container com a imagem atualizada...
docker run -d -p 5011:5011 --name %CONTAINER_NAME% %IMAGE_NAME%

echo.
echo >>> Deploy com Docker concluido!