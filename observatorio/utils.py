# observatorio/utils.py

import requests
from functools import wraps
from urllib.parse import urlparse, urljoin
from flask import request, Response, url_for, redirect, current_app

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