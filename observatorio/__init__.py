# observatorio/__init__.py

import os
import json
from flask import Flask
from dotenv import load_dotenv
import cloudinary
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

def create_app(test_config=None):
    load_dotenv()
    
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder='../templates',
        static_folder='../static'
    )
    
    # --- CONFIGURAÇÃO PARA POSTGRESQL (NEON) ---
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise RuntimeError("DATABASE_URL não está configurada. Verifique as suas variáveis de ambiente.")

    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY'),
        RECAPTCHA_SITE_KEY=os.environ.get('RECAPTCHA_SITE_KEY'),
        RECAPTCHA_SECRET_KEY=os.environ.get('RECAPTCHA_SECRET_KEY'),
        ADMIN_USERNAME=os.environ.get('ADMIN_USERNAME'),
        ADMIN_PASSWORD=os.environ.get('ADMIN_PASSWORD'),
        
        # --- Credenciais para Login com Google ---
        GOOGLE_CLIENT_ID=os.environ.get('GOOGLE_CLIENT_ID'),
        GOOGLE_CLIENT_SECRET=os.environ.get('GOOGLE_CLIENT_SECRET'),
        
        MAX_CONTENT_LENGTH=10 * 1024 * 1024, # Aumentado para 10MB para acomodar áudio
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        DATABASE_URL=db_url
    )

    if test_config is None:
        app.config.from_pyfile('config.py', silent=True)
    else:
        app.config.from_mapping(test_config)

    def load_locations():
        try:
            json_path = os.path.join(app.root_path, '..', 'locais_uem.json')
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {key: value for key, value in data.items() if not key.startswith('_')}
        except (FileNotFoundError, json.JSONDecodeError) as e:
            app.logger.error(f"ERRO CRÍTICO ao carregar 'locais_uem.json': {e}")
            return {}

    app.config['LOCAIS_UEM'] = load_locations()
    app.config['CATEGORIAS'] = ["Aparição", "Som Estranho", "Objeto Visto", "Sensação Estranha", "Outro Fenômeno"]
    
    cloudinary.config(
        cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'), 
        api_key = os.environ.get('CLOUDINARY_API_KEY'), 
        api_secret = os.environ.get('CLOUDINARY_API_SECRET'),
        secure = True
    )

    limiter.init_app(app)

    from . import db
    db.init_app(app)

    from . import routes_public
    routes_public.register_public_routes(app, limiter)

    from . import routes_admin
    routes_admin.register_admin_routes(app)
    
    return app
