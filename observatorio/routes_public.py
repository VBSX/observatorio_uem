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

from .db import get_db
from .utils import get_request_metadata, safe_redirect

def register_public_routes(app, limiter):
    """Registra todas as rotas públicas na instância principal do Flask."""

    @app.route('/')
    def index():
        db = get_db()
        conditions = ['aprovado = ?']
        params = [1]
        filter_category = request.args.get('categoria')
        filter_period = request.args.get('periodo')
        search_query = request.args.get('q', '').strip()
        categorias_config = current_app.config['CATEGORIAS']
        locais_uem_config = current_app.config['LOCAIS_UEM']
        if filter_category and filter_category in categorias_config:
            conditions.append('categoria = ?')
            params.append(filter_category)
        if filter_period == 'ultimo_mes':
            conditions.append("criado_em >= date('now', '-1 month')")
        if search_query:
            conditions.append('(LOWER(titulo) LIKE ? OR LOWER(descricao) LIKE ?)')
            search_term = f"%{search_query.lower()}%"
            params.extend([search_term, search_term])
        query = 'SELECT * FROM relatos WHERE ' + ' AND '.join(conditions) + ' ORDER BY id DESC'
        relatos_db = db.execute(query, params).fetchall()
        relatos_agrupados = defaultdict(list)
        default_coords = locais_uem_config.get("Outro Local / Não Listado", [-23.4065, -51.9395])
        for relato in relatos_db:
            relato_dict = dict(relato)
            # CORREÇÃO: O valor já é um objeto datetime, então só precisamos formatá-lo.
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
        show_captcha = not current_app.debug
        locais_sorted = sorted(current_app.config['LOCAIS_UEM'].keys())
        categorias_config = current_app.config['CATEGORIAS']
        site_key = current_app.config['RECAPTCHA_SITE_KEY']
        if request.method == 'POST':
            if show_captcha:
                secret_key = current_app.config['RECAPTCHA_SECRET_KEY']
                captcha_response = request.form.get('g-recaptcha-response')
                if not captcha_response:
                    flash('Por favor, complete a verificação do reCAPTCHA.')
                    return render_template('submit.html', locais=locais_sorted, categorias=categorias_config, form_data=request.form, site_key=site_key, show_captcha=show_captcha)
                response = requests.post("https://www.google.com/recaptcha/api/siteverify", data={'secret': secret_key, 'response': captcha_response})
                if not response.json().get('success'):
                    flash('Verificação do reCAPTCHA falhou. Tente novamente.')
                    return render_template('submit.html', locais=locais_sorted, categorias=categorias_config, form_data=request.form, site_key=site_key, show_captcha=show_captcha)
            titulo = request.form['titulo']
            descricao = request.form['descricao']
            local_selecionado = request.form['local']
            categoria = request.form['categoria']
            if len(titulo) > 100 or len(descricao) > 2000:
                flash('Título ou descrição excedeu o limite de caracteres.')
                return render_template('submit.html', locais=locais_sorted, categorias=categorias_config, form_data=request.form, site_key=site_key, show_captcha=show_captcha)
            imagem_url = None
            imagem_file = request.files.get('imagem')
            if imagem_file and imagem_file.filename != '':
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
                filename = secure_filename(imagem_file.filename)
                if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                    try:
                        upload_result = cloudinary.uploader.upload(imagem_file, folder="observatorio_uem")
                        imagem_url = upload_result.get('secure_url')
                        if not imagem_url: raise Exception("Falha ao obter URL do Cloudinary.")
                    except Exception as e:
                        current_app.logger.error(f"Erro no upload para o Cloudinary: {e}")
                        flash('Houve um erro ao fazer o upload da imagem. Tente novamente.')
                        return render_template('submit.html', locais=locais_sorted, categorias=categorias_config, form_data=request.form, site_key=site_key, show_captcha=show_captcha)
                else:
                    flash('Tipo de arquivo de imagem inválido. Use PNG, JPG, JPEG ou GIF.')
                    return render_template('submit.html', locais=locais_sorted, categorias=categorias_config, form_data=request.form, site_key=site_key, show_captcha=show_captcha)
            local_final = local_selecionado
            if local_selecionado == 'Outro Local / Não Listado':
                outro_local_texto = request.form.get('outro_local_texto', '').strip()
                if not outro_local_texto:
                    flash('Você selecionou "Outro Local", por favor, especifique qual é.')
                    return render_template('submit.html', locais=locais_sorted, categorias=categorias_config, form_data=request.form, site_key=site_key, show_captcha=show_captcha)
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
                return safe_redirect('index')
        return render_template('submit.html', locais=locais_sorted, categorias=categorias_config, form_data={}, site_key=site_key, show_captcha=show_captcha)

    @app.route('/relato/<int:relato_id>')
    def relato(relato_id):
        db = get_db()
        relato_db = db.execute('SELECT * FROM relatos WHERE id = ? AND aprovado = 1', (relato_id,)).fetchone()
        if relato_db is None:
            flash("Este relato não foi encontrado ou ainda não foi aprovado.")
            return safe_redirect('index')
        relato_dict = dict(relato_db)
        # MELHORIA: A conversão abaixo era desnecessária, pois o DB já retorna um objeto datetime.
        # relato_dict['criado_em'] = datetime.strptime(relato_dict['criado_em'], '%Y-%m-%d %H:%M:%S')
        comentarios_db = db.execute('SELECT * FROM comentarios WHERE relato_id = ? ORDER BY criado_em ASC', (relato_id,)).fetchall()
        comentarios_list = [dict(c) for c in comentarios_db]
        # MELHORIA: O loop abaixo para converter datas também era desnecessário.
        # for c in comentarios_list:
        #     c['criado_em'] = datetime.strptime(c['criado_em'], '%Y-%m-%d %H:%M:%S')
        voto_usuario = db.execute('SELECT tipo_voto FROM votos WHERE relato_id = ? AND session_id = ?', (relato_id, session.get('sid'))).fetchone()
        testemunha_usuario = db.execute('SELECT id FROM testemunhas WHERE relato_id = ? AND session_id = ?', (relato_id, session.get('sid'))).fetchone()
        return render_template('relato.html', 
                               relato=relato_dict, 
                               comentarios=comentarios_list, 
                               voto_usuario=voto_usuario,
                               testemunha_usuario=testemunha_usuario,
                               site_key=current_app.config['RECAPTCHA_SITE_KEY'],
                               show_captcha=not current_app.debug)

    @app.route('/relato/<int:relato_id>/comment', methods=['POST'])
    @limiter.limit("10 per minute")
    def add_comment(relato_id):
        show_captcha = not current_app.debug
        if show_captcha:
            secret_key = current_app.config['RECAPTCHA_SECRET_KEY']
            captcha_response = request.form.get('g-recaptcha-response')
            if not captcha_response:
                flash('Por favor, complete a verificação do reCAPTCHA.')
                return safe_redirect('relato', relato_id=relato_id)
            response = requests.post("https://www.google.com/recaptcha/api/siteverify", data={'secret': secret_key, 'response': captcha_response})
            if not response.json().get('success'):
                flash('Verificação do reCAPTCHA falhou. Tente novamente.')
                return safe_redirect('relato', relato_id=relato_id)
        autor = request.form['autor']
        texto = request.form['texto']
        if len(autor) > 50 or len(texto) > 500:
            flash("Nome ou comentário excedeu o limite de caracteres!")
            return safe_redirect('relato', relato_id=relato_id)
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
        return safe_redirect('relato', relato_id=relato_id)

    @app.route('/report_comment/<int:comment_id>', methods=['POST'])
    @limiter.limit("15 per hour")
    def report_comment(comment_id):
        db = get_db()
        comment = db.execute('SELECT relato_id FROM comentarios WHERE id = ?', (comment_id,)).fetchone()
        if comment:
            db.execute('UPDATE comentarios SET denunciado = 1 WHERE id = ?', (comment_id,))
            db.commit()
            flash('Obrigado por sua denúncia. O comentário será revisado pela moderação.')
            return safe_redirect('relato', relato_id=comment['relato_id'])
        else:
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
        if db.execute('SELECT * FROM votos WHERE relato_id = ? AND session_id = ?', (relato_id, session['sid'])).fetchone() or \
           db.execute('SELECT * FROM testemunhas WHERE relato_id = ? AND session_id = ?', (relato_id, session['sid'])).fetchone():
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

    @app.route('/witness/<int:relato_id>', methods=['POST'])
    @limiter.limit("30 per hour")
    def witness(relato_id):
        if 'sid' not in session:
            session['sid'] = str(uuid.uuid4())
        db = get_db()
        if db.execute('SELECT * FROM votos WHERE relato_id = ? AND session_id = ?', (relato_id, session['sid'])).fetchone() or \
           db.execute('SELECT * FROM testemunhas WHERE relato_id = ? AND session_id = ?', (relato_id, session['sid'])).fetchone():
            return jsonify({'success': False, 'message': 'Você já interagiu com este relato.'}), 403
        ip_address, city, user_agent = get_request_metadata()
        db.execute(
            'INSERT INTO testemunhas (relato_id, session_id, ip_address, city, user_agent) VALUES (?, ?, ?, ?, ?)',
            (relato_id, session['sid'], ip_address, city, user_agent)
        )
        db.execute('UPDATE relatos SET votos_testemunha = votos_testemunha + 1 WHERE id = ?', (relato_id,))
        db.commit()
        nova_contagem = db.execute('SELECT votos_testemunha FROM relatos WHERE id = ?', (relato_id,)).fetchone()['votos_testemunha']
        return jsonify({'success': True, 'message': 'Testemunho registrado!', 'votos_testemunha': nova_contagem})

    @app.route('/lendas')
    def lendas():
        db = get_db()
        todas_lendas = db.execute('SELECT * FROM lendas ORDER BY titulo ASC').fetchall()
        return render_template('lendas.html', lendas=todas_lendas)

    @app.route('/lenda/<int:lenda_id>')
    def lenda(lenda_id):
        db = get_db()
        lenda = db.execute('SELECT * FROM lendas WHERE id = ?', (lenda_id,)).fetchone()
        if lenda is None:
            flash("Lenda não encontrada.")
            return safe_redirect('lendas')
        return render_template('lenda.html', lenda=lenda)
