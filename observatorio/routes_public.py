# observatorio/routes_public.py

import uuid
from flask import (
    render_template, request, url_for, flash, redirect, g,
    jsonify, session, current_app
)
from collections import defaultdict
import traceback
import psycopg2.extras
from authlib.integrations.flask_client import OAuth
import os
from .db import get_db
from .utils import get_request_metadata, safe_redirect,get_city_from_ip,log_register, upload_audio_task, upload_image_task,send_new_relato_notification
from .forms import SubmitForm, CommentForm, AdminActionForm
import time 
from threading import Thread

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

        query = """
            SELECT 
                local,
                json_agg(
                    json_build_object(
                        'id', id,
                        'titulo', titulo,
                        'categoria', categoria,
                        'criado_em', to_char(criado_em, 'DD/MM/YYYY'),
                        'imagem_url', imagem_url
                    ) ORDER BY id DESC
                ) as relatos_json
            FROM relatos
            WHERE {where_conditions}
            GROUP BY local
        """.format(where_conditions=' AND '.join(conditions))
        current_app.logger.info("Iniciando processamento do relato.")
        db_start = time.time()    
        
        cur.execute(query, tuple(params))
        locais_agrupados_db = cur.fetchall()
        cur.close()
        current_app.logger.info(f"sql para fantasmas no mapa: {time.time() - db_start:.2f} segundos.")
        # Processamento em Python agora é muito mais leve
        locais_para_mapa = []
        default_coords = locais_uem_config.get("Outro Local / Não Listado", [-23.4065, -51.9395])

        for local_agrupado in locais_agrupados_db:
            local_key = local_agrupado['local']
            
            # A lógica para encontrar as coordenadas permanece a mesma
            coords = default_coords if local_key.startswith('Outro:') else locais_uem_config.get(local_key, default_coords)
            
            locais_para_mapa.append({
                "lat": coords[0],
                "lon": coords[1],
                "relatos": local_agrupado['relatos_json']  # Usamos o JSON diretamente do banco
            })


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
            start_time = time.time()
            current_app.logger.info("Iniciando processamento do relato.")
            
            titulo = form.titulo.data
            descricao = form.descricao.data
            local_selecionado = form.local.data
            categoria = form.categoria.data
            outro_local_texto = form.outro_local_texto.data.strip()
            imagem_file = form.imagem.data
            audio_file = form.audio.data

            # Dicionário para coletar os resultados das threads
            upload_results = {}
            threads = []

            if imagem_file:
                imagem_file.seek(0, os.SEEK_END)
                if imagem_file.tell() > (5 * 1024 * 1024):
                    flash('A imagem enviada é muito grande. O limite é de 5 MB.')
                    return render_template('submit.html', form=form, site_key=site_key, show_captcha=show_captcha)
                imagem_file.seek(0)
                image_thread = Thread(target=upload_image_task, args=(imagem_file, upload_results))
                threads.append(image_thread)
                image_thread.start()

            if audio_file:
                # Validação de tamanho
                audio_file.seek(0, os.SEEK_END)
                if audio_file.tell() > (10 * 1024 * 1024):
                    flash('O arquivo de áudio é muito grande. O limite é de 10 MB.')
                    return render_template('submit.html', form=form, site_key=site_key, show_captcha=show_captcha)
                audio_file.seek(0)

                audio_thread = Thread(target=upload_audio_task, args=(audio_file, upload_results))
                threads.append(audio_thread)
                audio_thread.start()

            for thread in threads:
                thread.join()


            if 'image_error' in upload_results:
                flash(upload_results['image_error'])
                return render_template('submit.html', form=form, site_key=site_key, show_captcha=show_captcha)
            if 'audio_error' in upload_results:
                flash(upload_results['audio_error'])
                return render_template('submit.html', form=form, site_key=site_key, show_captcha=show_captcha)

            imagem_url = upload_results.get('imagem_url')
            audio_url = upload_results.get('audio_url')
            
            local_final = outro_local_texto if local_selecionado == 'Outro Local / Não Listado' else local_selecionado
            ip_address, city, user_agent = get_request_metadata()
            user_id = g.user['id'] if g.user else None
            
            db_start = time.time()
            db = get_db()
            cur = db.cursor()
            cur.execute(
                'INSERT INTO relatos (titulo, descricao, local, categoria, imagem_url, audio_url, ip_address, city, user_agent, user_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (titulo, descricao, local_final, categoria, imagem_url, audio_url, ip_address, city, user_agent, user_id)
            )
            db.commit()
            cur.close()

            # --- CÓDIGO NOVO PARA ENVIAR E-MAIL ---
            try:
                app_context = current_app._get_current_object() 
                # Prepara os dados do relato para o e-mail
                relato_para_email = {
                    'titulo': titulo,
                    'local': local_final,
                    'descricao': descricao
                }
                email_thread = Thread(
                    target=send_new_relato_notification, 
                    args=(app_context, relato_para_email)
                )
                email_thread.start()
            except Exception as e:
                current_app.logger.error(f"Erro ao iniciar a thread de e-mail: {e}")
            
            current_app.logger.info(f"Operação de banco de dados levou: {time.time() - db_start:.2f} segundos.")
            current_app.logger.info(f"Processamento total levou: {time.time() - start_time:.2f} segundos.")
            
            flash('Seu relato foi enviado e aguarda aprovação. Obrigado por contribuir!')
            return safe_redirect('index')

        return render_template('submit.html', form=form, site_key=site_key, show_captcha=show_captcha)


    @app.route('/relato/<int:relato_id>')
    def relato(relato_id):
        start_time = time.time()
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
        current_app.logger.info(f"Operação de banco de dados geral levou(abertura do relato): {time.time() - start_time:.2f} segundos.")
        
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
        start_time = time.time()
        if 'sid' not in session:
            session['sid'] = str(uuid.uuid4())
        if tipo_voto not in ['acredito', 'cetico']:
            return jsonify({'success': False, 'message': 'Tipo de voto inválido'}), 400

        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            # ETAPA 1: VERIFICAR VOTO EXISTENTE
            check_start = time.time()
            cur.execute('SELECT * FROM votos WHERE relato_id = %s AND session_id = %s', (relato_id, session['sid']))
            voto_existente = cur.fetchone()
            log_register(time.time() - check_start, f"Voto: Verificação de voto existente para relato {relato_id}")

            if voto_existente:
                cur.close()
                return jsonify({'success': False, 'message': 'Você já votou neste relato.'}), 403

            # ETAPA 2: INSERIR NOVO VOTO
            insert_start = time.time()
            ip_address, city, user_agent = get_request_metadata()
            cur.execute(
                'INSERT INTO votos (relato_id, session_id, tipo_voto, ip_address, city, user_agent) VALUES (%s, %s, %s, %s, %s, %s)',
                (relato_id, session['sid'], tipo_voto, ip_address, city, user_agent)
            )
            log_register(time.time() - insert_start, f"Voto: Inserção na tabela 'votos'")

            # ETAPA 3: ATUALIZAR CONTAGEM
            update_start = time.time()
            coluna = 'votos_acredito' if tipo_voto == 'acredito' else 'votos_cetico'
            cur.execute(f'UPDATE relatos SET {coluna} = {coluna} + 1 WHERE id = %s', (relato_id,))
            log_register(time.time() - update_start, f"Voto: Update na tabela 'relatos'")
            
            # ETAPA 4: COMMIT
            commit_start = time.time()
            db.commit()
            log_register(time.time() - commit_start, "Voto: db.commit()")

            # ETAPA 5: BUSCAR CONTAGENS FINAIS
            fetch_start = time.time()
            cur.execute('SELECT votos_acredito, votos_cetico FROM relatos WHERE id = %s', (relato_id,))
            contagens = cur.fetchone()
            cur.close()
            log_register(time.time() - fetch_start, "Voto: Busca de contagens finais")
            
            log_register(time.time() - start_time, f"Voto: Processo total finalizado com sucesso para relato {relato_id}")
            return jsonify({'success': True, 'message': 'Voto computado!', 'votos_acredito': contagens['votos_acredito'], 'votos_cetico': contagens['votos_cetico']})

        except Exception as e:
            db.rollback()
            cur.close()
            # Usando print para capturar o erro completo, como solicitado.
            print(f"\n!!!!!!!!!! FALHA CRÍTICA AO VOTAR (relato_id: {relato_id}) !!!!!!!!!!")
            traceback.print_exc() # Imprime o traceback completo do erro
            print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")
            log_register(time.time() - start_time, f"Voto: FALHA NO PROCESSO para relato {relato_id}")
            return jsonify({'success': False, 'message': 'Ocorreu um erro interno no servidor.'}), 500
        
    
    
    def update_witness_metadata_task(witness_id, ip_address, user_agent):
        """
        Busca a cidade e atualiza o registro da testemunha.
        Executada em segundo plano.
        """
        with app.app_context():
            city = get_city_from_ip(ip_address)
            
            db = get_db()
            cur = db.cursor()
            cur.execute(
                'UPDATE testemunhas SET ip_address = %s, city = %s, user_agent = %s WHERE id = %s',
                (ip_address, city, user_agent, witness_id)
            )
            db.commit()
            cur.close()


    @app.route('/witness/<int:relato_id>', methods=['POST'])
    @limiter.limit("30 per hour")
    def witness(relato_id):
        start_time = time.time()
        
        if 'sid' not in session:
            session['sid'] = str(uuid.uuid4())
        db_connection_time = time.time()
        db = get_db()
        log_register(time.time() - db_connection_time, "registro testemunha(conexão)")
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        db_select_testemunhas_time = time.time()
        cur.execute('SELECT * FROM testemunhas WHERE relato_id = %s AND session_id = %s', (relato_id, session['sid']))
        if cur.fetchone():
            cur.close()
            return jsonify({'success': False, 'message': 'Você já interagiu com este relato.'}), 403

        log_register(time.time() - db_select_testemunhas_time, "registro testemunha(select)")
        
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        user_agent = request.headers.get('User-Agent')

        db_insere_testemunha_time = time.time()
        cur.execute(
            'INSERT INTO testemunhas (relato_id, session_id) VALUES (%s, %s) RETURNING id',
            (relato_id, session['sid'])
        )
        witness_id = cur.fetchone()['id']
        log_register(time.time() - db_insere_testemunha_time, "registro testemunha(insert)")
        
        db_atualiza_relato_time = time.time()
        cur.execute('UPDATE relatos SET votos_testemunha = votos_testemunha + 1 WHERE id = %s', (relato_id,))
        db.commit()
        log_register(time.time() - db_atualiza_relato_time, "registro testemunha(update relato)" )
        
        metadata_time = time.time()
        metadata_thread = Thread(target=update_witness_metadata_task, args=(witness_id, ip_address, user_agent))
        metadata_thread.start()
        log_register(time.time() - metadata_time, "registro testemunha(metadata)")
        
        cur.execute('SELECT votos_testemunha FROM relatos WHERE id = %s', (relato_id,))
        nova_contagem = cur.fetchone()['votos_testemunha']
        cur.close()
        total_time = time.time() - start_time

        log_register(total_time,"registro testemunha(tempo total)" )
        
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
    
    
