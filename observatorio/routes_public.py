# observatorio/routes_public.py

import uuid
from flask import (
    render_template, request, url_for, flash, redirect, g,
    jsonify, session, current_app
)
from collections import defaultdict
from datetime import datetime
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader
import requests
import psycopg2.extras

from .db import get_db
from .utils import get_request_metadata, safe_redirect

def register_public_routes(app, limiter):
    """Registra todas as rotas públicas na instância principal do Flask."""

    @app.route('/')
    def index():
        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        conditions = ['aprovado = %s']
        params = [True]
        
        filter_category = request.args.get('categoria')
        filter_period = request.args.get('periodo')
        search_query = request.args.get('q', '').strip()
        categorias_config = current_app.config['CATEGORIAS']
        locais_uem_config = current_app.config['LOCAIS_UEM']

        if filter_category and filter_category in categorias_config:
            conditions.append('categoria = %s')
            params.append(filter_category)
        if filter_period == 'ultimo_mes':
            conditions.append("criado_em >= NOW() - INTERVAL '1 month'")
        if search_query:
            conditions.append('(LOWER(titulo) LIKE %s OR LOWER(descricao) LIKE %s)')
            search_term = f"%{search_query.lower()}%"
            params.extend([search_term, search_term])
        
        query = 'SELECT * FROM relatos WHERE ' + ' AND '.join(conditions) + ' ORDER BY id DESC'
        cur.execute(query, tuple(params))
        relatos_db = cur.fetchall()
        cur.close()

        relatos_agrupados = defaultdict(list)
        default_coords = locais_uem_config.get("Outro Local / Não Listado", [-23.4065, -51.9395])
        for relato in relatos_db:
            relato_dict = dict(relato)
            relato_dict['criado_em'] = relato_dict['criado_em'].strftime('%d/%m/%Y')
            local_key = relato['local']
            coords = default_coords if local_key.startswith('Outro:') else locais_uem_config.get(local_key, default_coords)
            coord_key = tuple(coords)
            relatos_agrupados[coord_key].append(relato_dict)
            
        locais_para_mapa = [{"lat": c[0], "lon": c[1], "relatos": r} for c, r in relatos_agrupados.items()]
        return render_template('index.html',
                               locais_para_mapa=locais_para_mapa,
                               categorias=categorias_config,
                               search_query=search_query)

    @app.route('/submit', methods=('GET', 'POST'))
    @limiter.limit("5 per minute")
    def submit():
        locais_sorted = sorted(current_app.config['LOCAIS_UEM'].keys())
        categorias_config = current_app.config['CATEGORIAS']
        site_key = current_app.config['RECAPTCHA_SITE_KEY']
        show_captcha = not current_app.debug

        if request.method == 'POST':
            # Extrai os dados do formulário ANTES de os usar
            titulo = request.form.get('titulo')
            descricao = request.form.get('descricao')
            local_selecionado = request.form.get('local')
            categoria = request.form.get('categoria')
            outro_local_texto = request.form.get('outro_local_texto', '').strip()
            imagem_file = request.files.get('imagem')

            # ... (Lógica do reCAPTCHA aqui, se aplicável) ...

            if not titulo or not descricao or not categoria:
                flash('Todos os campos são obrigatórios!')
                return render_template('submit.html', locais=locais_sorted, categorias=categorias_config, form_data=request.form, site_key=site_key, show_captcha=show_captcha)

            if len(titulo) > 100 or len(descricao) > 2000:
                flash('Título ou descrição excedeu o limite de caracteres.')
                return render_template('submit.html', locais=locais_sorted, categorias=categorias_config, form_data=request.form, site_key=site_key, show_captcha=show_captcha)

            imagem_url = None
            if imagem_file and imagem_file.filename != '':
                try:
                    upload_result = cloudinary.uploader.upload(imagem_file, folder="observatorio_uem")
                    imagem_url = upload_result.get('secure_url')
                    if not imagem_url: raise Exception("Falha ao obter URL do Cloudinary.")
                except Exception as e:
                    current_app.logger.error(f"Erro no upload para o Cloudinary: {e}")
                    flash('Houve um erro ao fazer o upload da imagem. Tente novamente.')
                    return render_template('submit.html', locais=locais_sorted, categorias=categorias_config, form_data=request.form, site_key=site_key, show_captcha=show_captcha)

            local_final = local_selecionado
            if local_selecionado == 'Outro Local / Não Listado':
                if not outro_local_texto:
                    flash('Você selecionou "Outro Local", por favor, especifique qual é.')
                    return render_template('submit.html', locais=locais_sorted, categorias=categorias_config, form_data=request.form, site_key=site_key, show_captcha=show_captcha)
                local_final = f"Outro: {outro_local_texto}"

            ip_address, city, user_agent = get_request_metadata()
            db = get_db()
            cur = db.cursor()
            cur.execute(
                'INSERT INTO relatos (titulo, descricao, local, categoria, imagem_url, ip_address, city, user_agent) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                (titulo, descricao, local_final, categoria, imagem_url, ip_address, city, user_agent)
            )
            db.commit()
            cur.close()
            flash('Seu relato foi enviado e aguarda aprovação. Obrigado por contribuir!')
            return safe_redirect('index')

        return render_template('submit.html', locais=locais_sorted, categorias=categorias_config, form_data={}, site_key=site_key, show_captcha=show_captcha)


    @app.route('/relato/<int:relato_id>')
    def relato(relato_id):
        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        cur.execute('SELECT * FROM relatos WHERE id = %s AND aprovado = TRUE', (relato_id,))
        relato_db = cur.fetchone()
        
        if relato_db is None:
            cur.close()
            flash("Este relato não foi encontrado ou ainda não foi aprovado.")
            return safe_redirect('index')
            
        cur.execute('SELECT * FROM comentarios WHERE relato_id = %s ORDER BY criado_em ASC', (relato_id,))
        comentarios_db = cur.fetchall()
        
        cur.execute('SELECT tipo_voto FROM votos WHERE relato_id = %s AND session_id = %s', (relato_id, session.get('sid')))
        voto_usuario = cur.fetchone()
        
        cur.execute('SELECT id FROM testemunhas WHERE relato_id = %s AND session_id = %s', (relato_id, session.get('sid')))
        testemunha_usuario = cur.fetchone()
        
        cur.close()
        
        return render_template('relato.html',
                               relato=relato_db,
                               comentarios=comentarios_db,
                               voto_usuario=voto_usuario,
                               testemunha_usuario=testemunha_usuario,
                               site_key=current_app.config['RECAPTCHA_SITE_KEY'],
                               show_captcha=not current_app.debug)

    @app.route('/relato/<int:relato_id>/comment', methods=['POST'])
    @limiter.limit("10 per minute")
    def add_comment(relato_id):
        autor = request.form.get('autor')
        texto = request.form.get('texto')
        if not autor or not texto:
            flash("Autor e comentário são obrigatórios!")
        else:
            ip_address, city, user_agent = get_request_metadata()
            db = get_db()
            cur = db.cursor()
            cur.execute(
                'INSERT INTO comentarios (relato_id, autor, texto, ip_address, city, user_agent) VALUES (%s, %s, %s, %s, %s, %s)',
                (relato_id, autor, texto, ip_address, city, user_agent)
            )
            db.commit()
            cur.close()
            flash("Comentário adicionado!")
        return safe_redirect('relato', relato_id=relato_id)

    @app.route('/report_comment/<int:comment_id>', methods=['POST'])
    @limiter.limit("15 per hour")
    def report_comment(comment_id):
        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT relato_id FROM comentarios WHERE id = %s', (comment_id,))
        comment = cur.fetchone()
        if comment:
            cur.execute('UPDATE comentarios SET denunciado = TRUE WHERE id = %s', (comment_id,))
            db.commit()
            cur.close()
            flash('Obrigado por sua denúncia. O comentário será revisado pela moderação.')
            return safe_redirect('relato', relato_id=comment['relato_id'])
        else:
            cur.close()
            flash('Comentário não encontrado.')
            return safe_redirect('index')

    @app.route('/vote/<int:relato_id>/<string:tipo_voto>', methods=['POST'])
    @limiter.limit("30 per hour")
    def vote(relato_id, tipo_voto):
        if 'sid' not in session:
            session['sid'] = str(uuid.uuid4())
        if tipo_voto not in ['acredito', 'cetico']:
            return jsonify({'success': False, 'message': 'Tipo de voto inválido'}), 400
        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT * FROM votos WHERE relato_id = %s AND session_id = %s', (relato_id, session['sid']))
        voto_existente = cur.fetchone()
        cur.execute('SELECT * FROM testemunhas WHERE relato_id = %s AND session_id = %s', (relato_id, session['sid']))
        testemunha_existente = cur.fetchone()

        if voto_existente or testemunha_existente:
            cur.close()
            return jsonify({'success': False, 'message': 'Você já votou neste relato.'}), 403
        
        ip_address, city, user_agent = get_request_metadata()
        cur.execute(
            'INSERT INTO votos (relato_id, session_id, tipo_voto, ip_address, city, user_agent) VALUES (%s, %s, %s, %s, %s, %s)',
            (relato_id, session['sid'], tipo_voto, ip_address, city, user_agent)
        )
        coluna = 'votos_acredito' if tipo_voto == 'acredito' else 'votos_cetico'
        cur.execute(f'UPDATE relatos SET {coluna} = {coluna} + 1 WHERE id = %s', (relato_id,))
        db.commit()
        
        cur.execute('SELECT votos_acredito, votos_cetico FROM relatos WHERE id = %s', (relato_id,))
        contagens = cur.fetchone()
        cur.close()
        return jsonify({'success': True, 'message': 'Voto computado!', 'votos_acredito': contagens['votos_acredito'], 'votos_cetico': contagens['votos_cetico']})

    @app.route('/witness/<int:relato_id>', methods=['POST'])
    @limiter.limit("30 per hour")
    def witness(relato_id):
        if 'sid' not in session:
            session['sid'] = str(uuid.uuid4())
        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT * FROM votos WHERE relato_id = %s AND session_id = %s', (relato_id, session['sid']))
        voto_existente = cur.fetchone()
        cur.execute('SELECT * FROM testemunhas WHERE relato_id = %s AND session_id = %s', (relato_id, session['sid']))
        testemunha_existente = cur.fetchone()

        if voto_existente or testemunha_existente:
            cur.close()
            return jsonify({'success': False, 'message': 'Você já interagiu com este relato.'}), 403

        ip_address, city, user_agent = get_request_metadata()
        cur.execute(
            'INSERT INTO testemunhas (relato_id, session_id, ip_address, city, user_agent) VALUES (%s, %s, %s, %s, %s)',
            (relato_id, session['sid'], ip_address, city, user_agent)
        )
        cur.execute('UPDATE relatos SET votos_testemunha = votos_testemunha + 1 WHERE id = %s', (relato_id,))
        db.commit()
        
        cur.execute('SELECT votos_testemunha FROM relatos WHERE id = %s', (relato_id,))
        nova_contagem = cur.fetchone()['votos_testemunha']
        cur.close()
        return jsonify({'success': True, 'message': 'Testemunho registrado!', 'votos_testemunha': nova_contagem})

    @app.route('/lendas')
    def lendas():
        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT * FROM lendas ORDER BY titulo ASC')
        todas_lendas = cur.fetchall()
        cur.close()
        return render_template('lendas.html', lendas=todas_lendas)

    @app.route('/lenda/<int:lenda_id>')
    def lenda(lenda_id):
        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT * FROM lendas WHERE id = %s', (lenda_id,))
        lenda = cur.fetchone()
        cur.close()
        if lenda is None:
            flash("Lenda não encontrada.")
            return safe_redirect('lendas')
        return render_template('lenda.html', lenda=lenda)
