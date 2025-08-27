import sqlite3
import json
from datetime import datetime
from collections import defaultdict
from flask import Flask, render_template, request, url_for, flash, redirect, g, jsonify, session, Response
import requests
import os
from dotenv import load_dotenv
from functools import wraps
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader
import cloudinary.api
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

load_dotenv()

# --- Configuração Inicial ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['RECAPTCHA_SITE_KEY'] = os.environ.get('RECAPTCHA_SITE_KEY')
app.config['RECAPTCHA_SECRET_KEY'] = os.environ.get('RECAPTCHA_SECRET_KEY')

# --- CONFIGURAÇÕES DE SEGURANÇA PARA PRODUÇÃO ---
# 1. Limite de tamanho do upload (ex: 4 Megabytes)
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024 
# 2. Configurações do cookie de sessão
app.config['SESSION_COOKIE_SECURE'] = True  # Só enviar cookie em HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True # Impede acesso via JavaScript
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax' # Proteção contra CSRF

# --- Configuração do Cloudinary ---
cloudinary.config(
  cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'), 
  api_key = os.environ.get('CLOUDINARY_API_KEY'), 
  api_secret = os.environ.get('CLOUDINARY_API_SECRET'),
  secure = True
)

# --- Credenciais do Admin ---
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')

# --- 3. CONFIGURAÇÃO DO RATE LIMITER ---
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

# --- Carregamento de Dados e Funções do DB ---
def load_locations():
    try:
        with open('locais_uem.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {key: value for key, value in data.items() if not key.startswith('_')}
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERRO CRÍTICO ao carregar 'locais_uem.json': {e}")
        return {}

LOCAIS_UEM = load_locations()
CATEGORIAS = ["Aparição", "Som Estranho", "Objeto Visto", "Sensação Estranha", "Outro Fenômeno"]

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect('database.db')
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    with app.open_resource('schema.sql', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()
    print("Banco de dados inicializado com sucesso.")

# --- Decorador de Autenticação para o Admin ---
def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if auth and auth.username == ADMIN_USERNAME and auth.password == ADMIN_PASSWORD:
            return f(*args, **kwargs)
        return Response(
            'Acesso negado. Autenticação necessária.', 401,
            {'WWW-Authenticate': 'Basic realm="Login Required"'}
        )
    return decorated

# --- Função Helper para Coletar Metadados ---
def get_request_metadata():
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = request.headers.get('User-Agent')
    city = "Desconhecida"
    try:
        geo_response = requests.get(f"http://ip-api.com/json/{ip_address}")
        if geo_response.status_code == 200 and geo_response.json().get('status') == 'success':
            geo_data = geo_response.json()
            city = f"{geo_data.get('city', '')}, {geo_data.get('regionName', '')}"
    except requests.exceptions.RequestException:
        print(f"Aviso: Falha ao contatar a API de geolocalização para o IP {ip_address}")
    return ip_address, city, user_agent

# --- Rotas Públicas ---
@app.route('/')
def index():
    db = get_db()
    conditions = ['aprovado = ?']
    params = [1]
    filter_category = request.args.get('categoria')
    filter_period = request.args.get('periodo')
    if filter_category and filter_category in CATEGORIAS:
        conditions.append('categoria = ?')
        params.append(filter_category)
    if filter_period == 'ultimo_mes':
        conditions.append("criado_em >= date('now', '-1 month')")
    query = 'SELECT * FROM relatos WHERE ' + ' AND '.join(conditions) + ' ORDER BY id DESC'
    relatos_db = db.execute(query, params).fetchall()
    relatos_agrupados = defaultdict(list)
    default_coords = LOCAIS_UEM.get("Outro Local / Não Listado", [-23.4065, -51.9395])
    for relato in relatos_db:
        relato_dict = dict(relato)
        relato_dict['criado_em'] = datetime.strptime(relato_dict['criado_em'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y')
        local_key = relato['local']
        coords = default_coords if local_key.startswith('Outro:') else LOCAIS_UEM.get(local_key, default_coords)
        coord_key = tuple(coords)
        relatos_agrupados[coord_key].append(relato_dict)
    locais_para_mapa = [{"lat": c[0], "lon": c[1], "relatos": r} for c, r in relatos_agrupados.items()]
    return render_template('index.html', locais_para_mapa=locais_para_mapa, categorias=CATEGORIAS)

@app.route('/submit', methods=('GET', 'POST'))
@limiter.limit("5 per minute") # Limita o envio de relatos
def submit():
    show_captcha = not app.debug
    if request.method == 'POST':
        if show_captcha:
            secret_key = app.config['RECAPTCHA_SECRET_KEY']
            captcha_response = request.form.get('g-recaptcha-response')
            if not captcha_response:
                flash('Por favor, complete a verificação do reCAPTCHA.')
                return render_template('submit.html', locais=sorted(LOCAIS_UEM.keys()), categorias=CATEGORIAS, form_data=request.form, site_key=app.config['RECAPTCHA_SITE_KEY'], show_captcha=show_captcha)
            verify_url = "https://www.google.com/recaptcha/api/siteverify"
            payload = {'secret': secret_key, 'response': captcha_response}
            response = requests.post(verify_url, data=payload)
            if not response.json().get('success'):
                flash('Verificação do reCAPTCHA falhou. Tente novamente.')
                return render_template('submit.html', locais=sorted(LOCAIS_UEM.keys()), categorias=CATEGORIAS, form_data=request.form, site_key=app.config['RECAPTCHA_SITE_KEY'], show_captcha=show_captcha)

        titulo = request.form['titulo']
        descricao = request.form['descricao']
        local_selecionado = request.form['local']
        categoria = request.form['categoria']
        
        if len(titulo) > 100 or len(descricao) > 2000:
            flash('Título ou descrição excedeu o limite de caracteres.')
            return render_template('submit.html', locais=sorted(LOCAIS_UEM.keys()), categorias=CATEGORIAS, form_data=request.form, site_key=app.config['RECAPTCHA_SITE_KEY'], show_captcha=show_captcha)
        
        imagem_url = None
        imagem_file = request.files.get('imagem')
        if imagem_file and imagem_file.filename != '':
            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
            filename = secure_filename(imagem_file.filename)
            if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                try:
                    upload_result = cloudinary.uploader.upload(imagem_file, folder="observatorio_uem")
                    imagem_url = upload_result.get('secure_url')
                    if not imagem_url:
                        raise Exception("Falha ao obter URL do Cloudinary.")
                except Exception as e:
                    print(f"Erro no upload para o Cloudinary: {e}")
                    flash('Houve um erro ao fazer o upload da imagem. Tente novamente.')
                    return render_template('submit.html', locais=sorted(LOCAIS_UEM.keys()), categorias=CATEGORIAS, form_data=request.form, site_key=app.config['RECAPTCHA_SITE_KEY'], show_captcha=show_captcha)
            else:
                flash('Tipo de arquivo de imagem inválido. Use PNG, JPG, JPEG ou GIF.')
                return render_template('submit.html', locais=sorted(LOCAIS_UEM.keys()), categorias=CATEGORIAS, form_data=request.form, site_key=app.config['RECAPTCHA_SITE_KEY'], show_captcha=show_captcha)

        local_final = local_selecionado
        if local_selecionado == 'Outro Local / Não Listado':
            outro_local_texto = request.form.get('outro_local_texto', '').strip()
            if not outro_local_texto:
                flash('Você selecionou "Outro Local", por favor, especifique qual é.')
                return render_template('submit.html', locais=sorted(LOCAIS_UEM.keys()), categorias=CATEGORIAS, form_data=request.form, site_key=app.config['RECAPTCHA_SITE_KEY'], show_captcha=show_captcha)
            local_final = f"Outro: {outro_local_texto}"
        
        if not titulo or not descricao or not categoria:
            flash('Todos os campos são obrigatórios!')
        else:
            ip_address, city, user_agent = get_request_metadata()
            db = get_db()
            db.execute(
                'INSERT INTO relatos (titulo, descricao, local, categoria, imagem_url, ip_address, city, user_agent) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (titulo, descricao, local_final, categoria, imagem_url, ip_address, city, user_agent)
            )
            db.commit()
            flash('Seu relato foi enviado e aguarda aprovação. Obrigado por contribuir!')
            return redirect(url_for('index'))
            
    return render_template('submit.html', locais=sorted(LOCAIS_UEM.keys()), categorias=CATEGORIAS, form_data={}, site_key=app.config['RECAPTCHA_SITE_KEY'], show_captcha=not app.debug)

@app.route('/relato/<int:relato_id>')
def relato(relato_id):
    db = get_db()
    relato_db = db.execute('SELECT * FROM relatos WHERE id = ? AND aprovado = 1', (relato_id,)).fetchone()
    if relato_db is None:
        flash("Este relato não foi encontrado ou ainda não foi aprovado.")
        return redirect(url_for('index'))
    
    relato_dict = dict(relato_db)
    relato_dict['criado_em'] = datetime.strptime(relato_dict['criado_em'], '%Y-%m-%d %H:%M:%S')
    
    comentarios_db = db.execute('SELECT * FROM comentarios WHERE relato_id = ? ORDER BY criado_em ASC', (relato_id,)).fetchall()
    comentarios_list = [dict(c) for c in comentarios_db]
    for c in comentarios_list:
        c['criado_em'] = datetime.strptime(c['criado_em'], '%Y-%m-%d %H:%M:%S')
    
    voto_usuario = db.execute('SELECT tipo_voto FROM votos WHERE relato_id = ? AND session_id = ?', (relato_id, session.get('sid'))).fetchone()
    
    return render_template('relato.html', 
                           relato=relato_dict, 
                           comentarios=comentarios_list, 
                           voto_usuario=voto_usuario,
                           site_key=app.config['RECAPTCHA_SITE_KEY'],
                           show_captcha=not app.debug)

@app.route('/relato/<int:relato_id>/comment', methods=['POST'])
@limiter.limit("10 per minute") # Limita o envio de comentários
def add_comment(relato_id):
    show_captcha = not app.debug
    if show_captcha:
        secret_key = app.config['RECAPTCHA_SECRET_KEY']
        captcha_response = request.form.get('g-recaptcha-response')
        if not captcha_response:
            flash('Por favor, complete a verificação do reCAPTCHA.')
            return redirect(url_for('relato', relato_id=relato_id))
        
        verify_url = "https://www.google.com/recaptcha/api/siteverify"
        payload = {'secret': secret_key, 'response': captcha_response}
        response = requests.post(verify_url, data=payload)
        if not response.json().get('success'):
            flash('Verificação do reCAPTCHA falhou. Tente novamente.')
            return redirect(url_for('relato', relato_id=relato_id))

    autor = request.form['autor']
    texto = request.form['texto']
    
    if len(autor) > 50 or len(texto) > 500:
        flash("Nome ou comentário excedeu o limite de caracteres!")
        return redirect(url_for('relato', relato_id=relato_id))
    
    if not autor or not texto:
        flash("Autor e comentário são obrigatórios!")
    else:
        ip_address, city, user_agent = get_request_metadata()
        db = get_db()
        db.execute(
            'INSERT INTO comentarios (relato_id, autor, texto, ip_address, city, user_agent) VALUES (?, ?, ?, ?, ?, ?)',
            (relato_id, autor, texto, ip_address, city, user_agent)
        )
        db.commit()
        flash("Comentário adicionado!")
    return redirect(url_for('relato', relato_id=relato_id))

@app.route('/report_comment/<int:comment_id>', methods=['POST'])
@limiter.limit("15 per hour") # Limita as denúncias
def report_comment(comment_id):
    db = get_db()
    comment = db.execute('SELECT relato_id FROM comentarios WHERE id = ?', (comment_id,)).fetchone()
    if comment:
        db.execute('UPDATE comentarios SET denunciado = 1 WHERE id = ?', (comment_id,))
        db.commit()
        flash('Obrigado por sua denúncia. O comentário será revisado pela moderação.')
        return redirect(url_for('relato', relato_id=comment['relato_id']))
    else:
        flash('Comentário não encontrado.')
        return redirect(url_for('index'))

@app.route('/vote/<int:relato_id>/<string:tipo_voto>', methods=['POST'])
@limiter.limit("30 per hour") # Limita os votos
def vote(relato_id, tipo_voto):
    if 'sid' not in session:
        import uuid
        session['sid'] = str(uuid.uuid4())
    if tipo_voto not in ['acredito', 'cetico']:
        return jsonify({'success': False, 'message': 'Tipo de voto inválido'}), 400
    db = get_db()
    if db.execute('SELECT * FROM votos WHERE relato_id = ? AND session_id = ?', (relato_id, session['sid'])).fetchone():
        return jsonify({'success': False, 'message': 'Você já votou neste relato.'}), 403
    
    ip_address, city, user_agent = get_request_metadata()
    db.execute(
        'INSERT INTO votos (relato_id, session_id, tipo_voto, ip_address, city, user_agent) VALUES (?, ?, ?, ?, ?, ?)',
        (relato_id, session['sid'], tipo_voto, ip_address, city, user_agent)
    )
    
    coluna = 'votos_acredito' if tipo_voto == 'acredito' else 'votos_cetico'
    db.execute(f'UPDATE relatos SET {coluna} = {coluna} + 1 WHERE id = ?', (relato_id,))
    db.commit()
    contagens = db.execute('SELECT votos_acredito, votos_cetico FROM relatos WHERE id = ?', (relato_id,)).fetchone()
    return jsonify({'success': True, 'message': 'Voto computado!', 'votos_acredito': contagens['votos_acredito'], 'votos_cetico': contagens['votos_cetico']})

# --- ROTAS DE ADMIN ---
@app.route('/admin')
@auth_required
def admin():
    db = get_db()
    filtro_status = request.args.get('filtro', 'pendentes')

    query = 'SELECT * FROM relatos'
    params = []
    
    if filtro_status == 'pendentes':
        query += ' WHERE aprovado = ?'
        params.append(0)
    elif filtro_status == 'aprovados':
        query += ' WHERE aprovado = ?'
        params.append(1)
    elif filtro_status == 'denunciados':
        denunciados_ids_rows = db.execute('SELECT DISTINCT relato_id FROM comentarios WHERE denunciado = 1').fetchall()
        denunciados_ids = [row['relato_id'] for row in denunciados_ids_rows]
        
        if not denunciados_ids:
            query += ' WHERE 1 = 0'
        else:
            placeholders = ', '.join('?' for _ in denunciados_ids)
            query += f' WHERE id IN ({placeholders})'
            params.extend(denunciados_ids)

    if filtro_status == 'todos':
        query += ' ORDER BY aprovado ASC, id DESC'
    else:
        query += ' ORDER BY id DESC'

    relatos_filtrados = db.execute(query, params).fetchall()
    
    todos_comentarios = db.execute('SELECT * FROM comentarios ORDER BY criado_em DESC').fetchall()
    comentarios_por_relato = defaultdict(list)
    for comentario in todos_comentarios:
        comentarios_por_relato[comentario['relato_id']].append(dict(comentario))
    
    denuncias_count = db.execute('SELECT COUNT(id) FROM comentarios WHERE denunciado = 1').fetchone()[0]

    return render_template('admin.html', 
                           relatos=relatos_filtrados, 
                           filtro_ativo=filtro_status,
                           comentarios=comentarios_por_relato,
                           denuncias_count=denuncias_count)

@app.route('/admin/approve/<int:relato_id>', methods=['POST'])
@auth_required
def approve_relato(relato_id):
    db = get_db()
    db.execute('UPDATE relatos SET aprovado = 1 WHERE id = ?', (relato_id,))
    db.commit()
    flash(f'Relato #{relato_id} foi aprovado com sucesso!')
    return redirect(url_for('admin', filtro=request.args.get('filtro', 'pendentes')))

@app.route('/admin/delete/<int:relato_id>', methods=['POST'])
@auth_required
def delete_relato(relato_id):
    db = get_db()
    db.execute('DELETE FROM votos WHERE relato_id = ?', (relato_id,))
    db.execute('DELETE FROM comentarios WHERE relato_id = ?', (relato_id,))
    db.execute('DELETE FROM relatos WHERE id = ?', (relato_id,))
    db.commit()
    flash(f'Relato #{relato_id} e seus dados associados foram excluídos!')
    return redirect(url_for('admin', filtro=request.args.get('filtro', 'pendentes')))

@app.route('/admin/delete_comment/<int:comment_id>', methods=['POST'])
@auth_required
def delete_comment(comment_id):
    db = get_db()
    comment = db.execute('SELECT id FROM comentarios WHERE id = ?', (comment_id,)).fetchone()
    if comment:
        db.execute('DELETE FROM comentarios WHERE id = ?', (comment_id,))
        db.commit()
        flash(f'Comentário #{comment_id} foi excluído com sucesso!')
    else:
        flash('Comentário não encontrado.')
    return redirect(url_for('admin', filtro=request.args.get('filtro', 'denunciados')))

@app.route('/admin/unreport_comment/<int:comment_id>', methods=['POST'])
@auth_required
def unreport_comment(comment_id):
    db = get_db()
    comment = db.execute('SELECT id FROM comentarios WHERE id = ?', (comment_id,)).fetchone()
    if comment:
        db.execute('UPDATE comentarios SET denunciado = 0 WHERE id = ?', (comment_id,))
        db.commit()
        flash(f'Denúncia do comentário #{comment_id} foi removida.')
    else:
        flash('Comentário não encontrado.')
    return redirect(url_for('admin', filtro='denunciados'))


@app.cli.command('init-db')
def init_db_command():
    init_db()
