# observatorio/utils.py

import requests
from functools import wraps
from urllib.parse import urlparse, urljoin
from flask import request, Response, url_for, redirect, current_app
import cloudinary
import cloudinary.uploader

def auth_required(f):
    """Decorador para proteger rotas que exigem autenticação de admin."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if auth and auth.username == current_app.config['ADMIN_USERNAME'] and auth.password == current_app.config['ADMIN_PASSWORD']:
            return f(*args, **kwargs)
        return Response(
            'Acesso negado. Autenticação necessária.', 401,
            {'WWW-Authenticate': 'Basic realm="Login Required"'}
        )
    return decorated

def get_request_metadata():
    """Obtém IP, cidade e User-Agent do cliente que fez a requisição."""
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = request.headers.get('User-Agent')
    city = "Desconhecida"
    try:
        if not (ip_address.startswith('127.0.0.1') or ip_address.startswith('192.168.')):
            geo_response = requests.get(f"http://ip-api.com/json/{ip_address}")
            if geo_response.status_code == 200 and geo_response.json().get('status') == 'success':
                geo_data = geo_response.json()
                city = f"{geo_data.get('city', '')}, {geo_data.get('regionName', '')}"
    except requests.exceptions.RequestException as e:
        current_app.logger.warning(f"Falha ao contatar API de geolocalização para IP {ip_address}: {e}")
    return ip_address, city, user_agent

def is_safe_url(target):
    """Verifica se uma URL de redirecionamento é segura."""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

def safe_redirect(endpoint, **values):
    """Redireciona para um endpoint de forma segura."""
    target = url_for(endpoint, **values)
    if is_safe_url(target):
        return redirect(target)
    return redirect(url_for('index'))



def get_request_details():
    """
    Obtém detalhes rápidos do request (IP e User-Agent) que estão
    disponíveis no contexto da requisição principal. É uma função rápida.
    """
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = request.headers.get('User-Agent')
    return ip_address, user_agent


def get_city_from_ip(ip_address):
    """
    Recebe um endereço de IP e retorna a cidade.
    Esta é a função lenta que faz a chamada de rede para a API externa.
    """
    if not ip_address or ip_address.startswith('127.0.0.1') or ip_address.startswith('192.168.'):
        return "Desconhecida"
    
    try:
        geo_response = requests.get(f"http://ip-api.com/json/{ip_address}", timeout=3)
        if geo_response.status_code == 200 and geo_response.json().get('status') == 'success':
            geo_data = geo_response.json()
            return f"{geo_data.get('city', '')}, {geo_data.get('regionName', '')}"
    except requests.exceptions.RequestException as e:
        current_app.logger.warning(f"Falha ao contatar API de geolocalização para IP {ip_address}: {e}")
        
    return "Desconhecida"

def upload_image_task(imagem_file, results):
    """Esta função faz o upload da imagem e armazena a URL no dicionário de resultados."""
    try:
        upload_result = cloudinary.uploader.upload(
            imagem_file,
            folder="observatorio_uem_imagens",
            transformation=[{'width': 1920, 'height': 1080, 'crop': 'limit'}, {'quality': 'auto', 'fetch_format': 'auto'}]
        )
        results['imagem_url'] = upload_result.get('secure_url')
    except Exception as e:
        current_app.logger.error(f"Erro na thread de upload de imagem: {e}")
        results['imagem_url'] = None
        results['image_error'] = 'Houve um erro ao fazer o upload da imagem.'

def upload_audio_task(audio_file, results):
    """Esta função faz o upload do áudio e armazena a URL no dicionário de resultados."""
    try:
        upload_result = cloudinary.uploader.upload(
            audio_file,
            folder="observatorio_uem_audios",
            resource_type="video",
            transformation=[{'audio_codec': 'mp3', 'bit_rate': '64k'}]
        )
        results['audio_url'] = upload_result.get('secure_url')
    except Exception as e:
        current_app.logger.error(f"Erro na thread de upload de áudio: {e}")
        results['audio_url'] = None
        results['audio_error'] = 'Houve um erro ao fazer o upload do áudio.'

def log_register(time, description):
    text = f"Operação ({description}) levou: {time:.2f} segundos."
    print(text)
    current_app.logger.info(text)
