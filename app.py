import sqlite3
import json
from datetime import datetime
from collections import defaultdict
from flask import Flask, render_template, request, url_for, flash, redirect, g, jsonify, session
import requests
import os
from dotenv import load_dotenv
load_dotenv()
# --- Configuração Inicial ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['RECAPTCHA_SITE_KEY'] = os.environ.get('RECAPTCHA_SITE_KEY')
app.config['RECAPTCHA_SECRET_KEY'] = os.environ.get('RECAPTCHA_SECRET_KEY')

# --- Carregamento de Dados ---
def load_locations():
    try:
        with open('locais_uem.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            locations = {key: value for key, value in data.items() if not key.startswith('_')}
            return locations
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERRO CRÍTICO ao carregar 'locais_uem.json': {e}")
        return {}

LOCAIS_UEM = load_locations()
CATEGORIAS = ["Aparição", "Som Estranho", "Objeto Visto", "Sensação Estranha", "Outro Fenômeno"]

# --- Funções do Banco de Dados ---
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

# --- Rotas do Site ---
@app.route('/')
def index():
    db = get_db()
    query = 'SELECT * FROM relatos ORDER BY id DESC'
    params = []
    relatos_db = db.execute(query, params).fetchall()
    
    # --- LINHA DE DIAGNÓSTICO ---
    print(f"--- DIAGNÓSTICO: {len(relatos_db)} relato(s) encontrado(s) no banco de dados. ---")
    # -----------------------------
    
    relatos_agrupados = defaultdict(list)
    default_coords = LOCAIS_UEM.get("Outro Local / Não Listado", [-23.4065, -51.9395])

    for relato in relatos_db:
        relato_dict = dict(relato)
        relato_dict['criado_em'] = datetime.strptime(relato_dict['criado_em'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y')
        
        local_key = relato['local']
        if local_key.startswith('Outro:'):
            coords = default_coords
        else:
            coords = LOCAIS_UEM.get(local_key, default_coords)
        
        coord_key = tuple(coords)
        relatos_agrupados[coord_key].append(relato_dict)

    locais_para_mapa = []
    for coords, relatos in relatos_agrupados.items():
        locais_para_mapa.append({
            "lat": coords[0],
            "lon": coords[1],
            "relatos": relatos
        })

    return render_template('index.html', locais_para_mapa=locais_para_mapa, categorias=CATEGORIAS)

@app.route('/submit', methods=('GET', 'POST'))
def submit():
    if request.method == 'POST':
        # --- LÓGICA DE VERIFICAÇÃO DO RECAPTCHA ---
        secret_key = app.config['RECAPTCHA_SECRET_KEY']
        captcha_response = request.form.get('g-recaptcha-response')
        
        verify_url = f"https://www.google.com/recaptcha/api/siteverify"
        payload = {
            'secret': secret_key,
            'response': captcha_response
        }
        response = requests.post(verify_url, data=payload)
        response_data = response.json()

        # Se a verificação falhar, recarrega a página com erro
        if not response_data.get('success'):
            flash('Verificação do reCAPTCHA falhou. Por favor, tente novamente.')
            return render_template('submit.html', 
                                   locais=sorted(LOCAIS_UEM.keys()), 
                                   categorias=CATEGORIAS, 
                                   form_data=request.form,
                                   site_key=app.config['RECAPTCHA_SITE_KEY'])
        # --- FIM DA VERIFICAÇÃO ---


        titulo = request.form['titulo']
        descricao = request.form['descricao']
        local_selecionado = request.form['local']
        categoria = request.form['categoria']
        
        local_final = local_selecionado
        
        if local_selecionado == 'Outro Local / Não Listado':
            outro_local_texto = request.form.get('outro_local_texto', '').strip()
            if not outro_local_texto:
                flash('Você selecionou "Outro Local", por favor, especifique qual é.')
                return render_template('submit.html', locais=sorted(LOCAIS_UEM.keys()), categorias=CATEGORIAS, form_data=request.form, site_key=app.config['RECAPTCHA_SITE_KEY'])
            local_final = f"Outro: {outro_local_texto}"

        if not titulo or not descricao or not categoria:
            flash('Todos os campos são obrigatórios!')
        else:
            db = get_db()
            db.execute('INSERT INTO relatos (titulo, descricao, local, categoria) VALUES (?, ?, ?, ?)',
                       (titulo, descricao, local_final, categoria))
            db.commit()
            flash('Seu relato foi enviado para o mapa do inexplicável!')
            return redirect(url_for('index'))
            
    # Para o método GET, passa a chave do site para o template
    return render_template('submit.html', 
                           locais=sorted(LOCAIS_UEM.keys()), 
                           categorias=CATEGORIAS, 
                           form_data={},
                           site_key=app.config['RECAPTCHA_SITE_KEY'])

@app.route('/relato/<int:relato_id>')
def relato(relato_id):
    db = get_db()
    relato_db = db.execute('SELECT * FROM relatos WHERE id = ?', (relato_id,)).fetchone()
    
    if relato_db is None:
        return "Relato não encontrado!", 404
    
    relato_dict = dict(relato_db)
    relato_dict['criado_em'] = datetime.strptime(relato_dict['criado_em'], '%Y-%m-%d %H:%M:%S')

    comentarios_db = db.execute('SELECT * FROM comentarios WHERE relato_id = ? ORDER BY criado_em ASC', (relato_id,)).fetchall()
    comentarios_list = [dict(c) for c in comentarios_db]
    for c in comentarios_list:
        c['criado_em'] = datetime.strptime(c['criado_em'], '%Y-%m-%d %H:%M:%S')

    voto_usuario = db.execute('SELECT tipo_voto FROM votos WHERE relato_id = ? AND session_id = ?', 
                              (relato_id, session.get('sid'))).fetchone()

    return render_template('relato.html', relato=relato_dict, comentarios=comentarios_list, voto_usuario=voto_usuario)

@app.route('/relato/<int:relato_id>/comment', methods=['POST'])
def add_comment(relato_id):
    autor = request.form['autor']
    texto = request.form['texto']
    
    if not autor or not texto:
        flash("Autor e comentário são obrigatórios!")
    else:
        db = get_db()
        db.execute('INSERT INTO comentarios (relato_id, autor, texto) VALUES (?, ?, ?)',
                   (relato_id, autor, texto))
        db.commit()
        flash("Comentário adicionado!")
    return redirect(url_for('relato', relato_id=relato_id))

@app.route('/vote/<int:relato_id>/<string:tipo_voto>', methods=['POST'])
def vote(relato_id, tipo_voto):
    if 'sid' not in session:
        import uuid
        session['sid'] = str(uuid.uuid4())
    
    if tipo_voto not in ['acredito', 'cetico']:
        return jsonify({'success': False, 'message': 'Tipo de voto inválido'}), 400
    
    db = get_db()
    voto_existente = db.execute('SELECT * FROM votos WHERE relato_id = ? AND session_id = ?', 
                                (relato_id, session['sid'])).fetchone()
    if voto_existente:
        return jsonify({'success': False, 'message': 'Você já votou neste relato.'}), 403

    db.execute('INSERT INTO votos (relato_id, session_id, tipo_voto) VALUES (?, ?, ?)',
               (relato_id, session['sid'], tipo_voto))
    
    coluna_voto = 'votos_acredito' if tipo_voto == 'acredito' else 'votos_cetico'
    db.execute(f'UPDATE relatos SET {coluna_voto} = {coluna_voto} + 1 WHERE id = ?', (relato_id,))
    db.commit()

    contagens = db.execute('SELECT votos_acredito, votos_cetico FROM relatos WHERE id = ?', (relato_id,)).fetchone()
    return jsonify({
        'success': True, 
        'message': 'Voto computado!',
        'votos_acredito': contagens['votos_acredito'],
        'votos_cetico': contagens['votos_cetico']
    })

@app.cli.command('init-db')
def init_db_command():
    init_db()