# observatorio/routes_public.py

import uuid
from flask import (
    render_template, request, url_for, flash, redirect, g,
    jsonify, session, current_app
)
from collections import defaultdict
import cloudinary
import cloudinary.uploader
import psycopg2.extras
from authlib.integrations.flask_client import OAuth
import os
from .db import get_db
from .utils import get_request_metadata, safe_redirect
from .forms import SubmitForm, CommentForm, AdminActionForm

def register_public_routes(app, limiter):
    """Registra todas as rotas públicas na instância principal do Flask."""

    oauth = OAuth(app)
    google = oauth.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )

    @app.before_request
    def load_logged_in_user():
        user_id = session.get('user_id')
        g.user = None
        if user_id is not None:
            db = get_db()
            cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))
            g.user = cur.fetchone()
            cur.close()

    @app.route('/login')
    def login():
        redirect_uri = url_for('authorize', _external=True)
        return google.authorize_redirect(redirect_uri)

    @app.route('/authorize')
    def authorize():
        token = google.authorize_access_token()
        user_info = google.parse_id_token(token, nonce=session.get('nonce'))
        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT * FROM users WHERE google_id = %s', (user_info['sub'],))
        user = cur.fetchone()
        if user is None:
            cur.execute(
                'INSERT INTO users (google_id, nome, email, profile_pic_url) VALUES (%s, %s, %s, %s) RETURNING id',
                (user_info['sub'], user_info['name'], user_info['email'], user_info['picture'])
            )
            user_id = cur.fetchone()['id']
            db.commit()
        else:
            user_id = user['id']
        cur.close()
        session['user_id'] = user_id
        flash("Login realizado com sucesso!")
        return redirect(url_for('index'))

    @app.route('/logout')
    def logout():
        session.clear()
        flash("Você foi desconectado.")
        return redirect(url_for('index'))

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
                               categorias=categorias_config)

    @app.route('/submit', methods=('GET', 'POST'))
    @limiter.limit("5 per minute")
    def submit():
        form = SubmitForm()

        locais_choices = sorted(current_app.config['LOCAIS_UEM'].keys())
        form.local.choices = [('', 'Selecione um local...')] + [(l, l) for l in locais_choices]

        categorias_choices = current_app.config['CATEGORIAS']
        form.categoria.choices = [('', 'Selecione uma categoria...')] + [(c, c) for c in categorias_choices]

        site_key = current_app.config['RECAPTCHA_SITE_KEY']
        show_captcha = not current_app.debug

        if form.validate_on_submit():
            titulo = form.titulo.data
            descricao = form.descricao.data
            local_selecionado = form.local.data
            categoria = form.categoria.data
            outro_local_texto = form.outro_local_texto.data.strip()
            imagem_file = form.imagem.data
            audio_file = form.audio.data

            MAX_IMAGE_SIZE_MB = 5
            MAX_AUDIO_SIZE_MB = 10
            MAX_IMAGE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024
            MAX_AUDIO_BYTES = MAX_AUDIO_SIZE_MB * 1024 * 1024

            imagem_url = None
            if imagem_file:
                # Check file size by reading its content length
                imagem_file.seek(0, os.SEEK_END)
                if imagem_file.tell() > MAX_IMAGE_BYTES:
                    flash(f'A imagem enviada é muito grande. O limite é de {MAX_IMAGE_SIZE_MB} MB.')
                    return render_template('submit.html', form=form, site_key=site_key, show_captcha=show_captcha)
                imagem_file.seek(0)
                try:
                    upload_result = cloudinary.uploader.upload(imagem_file, folder="observatorio_uem_imagens", transformation=[{'width': 1920, 'height': 1080, 'crop': 'limit'}, {'quality': 'auto', 'fetch_format': 'auto'}])
                    imagem_url = upload_result.get('secure_url')
                except Exception as e:
                    current_app.logger.error(f"Erro no upload da imagem: {e}")
                    flash('Houve um erro ao fazer o upload da imagem.')
                    return render_template('submit.html', form=form, site_key=site_key, show_captcha=show_captcha)

            audio_url = None
            if audio_file:
                audio_file.seek(0, os.SEEK_END)
                if audio_file.tell() > MAX_AUDIO_BYTES:
                    flash(f'O arquivo de áudio é muito grande. O limite é de {MAX_AUDIO_SIZE_MB} MB.')
                    return render_template('submit.html', form=form, site_key=site_key, show_captcha=show_captcha)
                audio_file.seek(0)
                try:
                    upload_result = cloudinary.uploader.upload(audio_file, folder="observatorio_uem_audios", resource_type="video", transformation=[{'audio_codec': 'mp3', 'bit_rate': '64k'}])
                    audio_url = upload_result.get('secure_url')
                except Exception as e:
                    current_app.logger.error(f"Erro no upload do áudio: {e}")
                    flash('Houve um erro ao fazer o upload do áudio.')
                    return render_template('submit.html', form=form, site_key=site_key, show_captcha=show_captcha)

            local_final = outro_local_texto if local_selecionado == 'Outro Local / Não Listado' else local_selecionado
            ip_address, city, user_agent = get_request_metadata()
            user_id = g.user['id'] if g.user else None

            db = get_db()
            cur = db.cursor()
            cur.execute(
                'INSERT INTO relatos (titulo, descricao, local, categoria, imagem_url, audio_url, ip_address, city, user_agent, user_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (titulo, descricao, local_final, categoria, imagem_url, audio_url, ip_address, city, user_agent, user_id)
            )
            db.commit()
            cur.close()
            flash('Seu relato foi enviado e aguarda aprovação. Obrigado por contribuir!')
            return safe_redirect('index')

        return render_template('submit.html', form=form, site_key=site_key, show_captcha=show_captcha)

    @app.route('/relato/<int:relato_id>')
    def relato(relato_id):
        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT r.*, u.nome as autor_relato, u.id as autor_id FROM relatos r LEFT JOIN users u ON r.user_id = u.id WHERE r.id = %s AND r.aprovado = TRUE', (relato_id,))
        relato_db = cur.fetchone()
        if relato_db is None:
            cur.close()
            flash("Este relato não foi encontrado ou ainda não foi aprovado.")
            return safe_redirect('index')
        cur.execute("""
            SELECT c.*, u.nome as autor, u.profile_pic_url, u.id as autor_id
            FROM comentarios c JOIN users u ON c.user_id = u.id
            WHERE c.relato_id = %s ORDER BY c.criado_em ASC
        """, (relato_id,))
        comentarios_db = cur.fetchall()
        cur.execute('SELECT tipo_voto FROM votos WHERE relato_id = %s AND session_id = %s', (relato_id, session.get('sid')))
        voto_usuario = cur.fetchone()
        cur.execute('SELECT id FROM testemunhas WHERE relato_id = %s AND session_id = %s', (relato_id, session.get('sid')))
        testemunha_usuario = cur.fetchone()
        cur.close()

        comment_form = CommentForm()
        report_form = AdminActionForm()

        return render_template('relato.html',
                               relato=relato_db,
                               comentarios=comentarios_db,
                               voto_usuario=voto_usuario,
                               testemunha_usuario=testemunha_usuario,
                               site_key=current_app.config['RECAPTCHA_SITE_KEY'],
                               show_captcha=not current_app.debug,
                               comment_form=comment_form,
                               report_form=report_form)

    @app.route('/relato/<int:relato_id>/comment', methods=['POST'])
    @limiter.limit("10 per minute")
    def add_comment(relato_id):
        if g.user is None:
            flash("Você precisa estar logado para comentar.")
            return redirect(url_for('login'))

        form = CommentForm()
        if form.validate_on_submit():
            texto = form.texto.data
            ip_address, city, user_agent = get_request_metadata()
            db = get_db()
            cur = db.cursor()
            cur.execute(
                'INSERT INTO comentarios (relato_id, texto, user_id, ip_address, city, user_agent) VALUES (%s, %s, %s, %s, %s, %s)',
                (relato_id, texto, g.user['id'], ip_address, city, user_agent)
            )
            db.commit()
            cur.close()
            flash("Comentário adicionado!")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Erro no campo '{getattr(form, field).label.text}': {error}", "error")

        return safe_redirect('relato', relato_id=relato_id)

    @app.route('/profile/<int:user_id>')
    def profile(user_id):
        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))
        user = cur.fetchone()
        if user is None:
            flash("Investigador não encontrado.")
            return redirect(url_for('index'))
        cur.execute('SELECT * FROM relatos WHERE user_id = %s ORDER BY criado_em DESC', (user_id,))
        relatos = cur.fetchall()
        cur.execute("""
            SELECT c.*, r.titulo as relato_titulo
            FROM comentarios c JOIN relatos r ON c.relato_id = r.id
            WHERE c.user_id = %s ORDER BY c.criado_em DESC
        """, (user_id,))
        comentarios = cur.fetchall()
        cur.close()
        return render_template('profile.html', user=user, relatos=relatos, comentarios=comentarios)

    @app.route('/rankings')
    def rankings():
        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT id, titulo, votos_acredito FROM relatos
            WHERE aprovado = TRUE AND votos_acredito > 0
            ORDER BY votos_acredito DESC, criado_em DESC LIMIT 10;
        """)
        top_relatos = cur.fetchall()
        cur.execute("""
            SELECT local, COUNT(id) as total_relatos FROM relatos
            WHERE aprovado = TRUE GROUP BY local
            ORDER BY total_relatos DESC, local ASC LIMIT 10;
        """)
        top_locais = cur.fetchall()
        cur.close()
        return render_template('rankings.html', top_relatos=top_relatos, top_locais=top_locais)

    @app.route('/report_comment/<int:comment_id>', methods=['POST'])
    @limiter.limit("15 per hour")
    def report_comment(comment_id):
        form = AdminActionForm()
        if not form.validate_on_submit():
            flash('Falha na validação da denúncia. Tente novamente.')
            # Achar um bom redirecionamento é difícil sem saber de onde o usuário veio
            # A página inicial é uma opção segura.
            return safe_redirect('index')

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
        if voto_existente:
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
        cur.execute('SELECT * FROM testemunhas WHERE relato_id = %s AND session_id = %s', (relato_id, session['sid']))
        testemunha_existente = cur.fetchone()
        if testemunha_existente:
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
        lenda_db = cur.fetchone()
        cur.close()
        if lenda_db is None:
            flash("Lenda não encontrada.")
            return safe_redirect('lendas')
        return render_template('lenda.html', lenda=lenda_db)