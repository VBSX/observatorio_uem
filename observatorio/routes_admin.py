# observatorio/routes_admin.py

from flask import render_template, request, flash, current_app, url_for
from collections import defaultdict
import cloudinary.uploader
import psycopg2.extras
from threading import Thread
from .db import get_db
from .utils import auth_required, safe_redirect,send_approval_notification
from .forms import AdminActionForm, LendaForm

def register_admin_routes(app):
    """Registra todas as rotas de admin na instância principal do Flask."""

    def delete_cloudinary_midia(url, resource_type='image'):
        """Deleta uma midia do Cloudinary dado seu URL completo."""
        if not url: return
        try:
            public_id = '/'.join(url.split('/')[-2:]).split('.')[0]
            if resource_type in ['video', 'audio']:
                cloudinary.uploader.destroy(public_id, resource_type='video')
            else:
                cloudinary.uploader.destroy(public_id)
        except Exception as e:
            current_app.logger.error(f"Erro ao deletar midia do Cloudinary ({url}): {e}")

    @app.route('/admin')
    @auth_required
    def admin():
        return safe_redirect('admin_relatos')

    @app.route('/admin/relatos')
    @auth_required
    def admin_relatos():
        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)

        filtro_status = request.args.get('filtro', 'pendentes')
        query = 'SELECT * FROM relatos'
        params = []

        if filtro_status == 'pendentes':
            query += ' WHERE aprovado = %s'
            params.append(False)
        elif filtro_status == 'aprovados':
            query += ' WHERE aprovado = %s'
            params.append(True)
        elif filtro_status == 'denunciados':
            cur.execute('SELECT DISTINCT relato_id FROM comentarios WHERE denunciado = TRUE')
            denunciados_ids_rows = cur.fetchall()
            denunciados_ids = [row['relato_id'] for row in denunciados_ids_rows]
            if not denunciados_ids:
                query += ' WHERE 1 = 0' # Nenhum relato para mostrar
            else:
                placeholders = ', '.join(['%s'] * len(denunciados_ids))
                query += f' WHERE id IN ({placeholders})'
                params.extend(denunciados_ids)

        if filtro_status == 'todos':
            query = 'SELECT * FROM relatos ORDER BY aprovado ASC, id DESC'
            params = []
        else:
            query += ' ORDER BY id DESC'

        cur.execute(query, tuple(params))
        relatos_filtrados = cur.fetchall()

        cur.execute('SELECT * FROM comentarios ORDER BY criado_em DESC')
        todos_comentarios = cur.fetchall()

        cur.execute('SELECT COUNT(id) FROM comentarios WHERE denunciado = TRUE')
        denuncias_count = cur.fetchone()[0]

        cur.close()

        comentarios_por_relato = defaultdict(list)
        for comentario in todos_comentarios:
            comentarios_por_relato[comentario['relato_id']].append(dict(comentario))

        action_form = AdminActionForm()

        return render_template('admin.html',
                               relatos=relatos_filtrados,
                               filtro_ativo=filtro_status,
                               comentarios=comentarios_por_relato,
                               denuncias_count=denuncias_count,
                               action_form=action_form)

    @app.route('/admin/approve/<int:relato_id>', methods=['POST'])
    @auth_required
    def approve_relato(relato_id):
        form = AdminActionForm()
        if form.validate_on_submit():
            db = get_db()
            cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute('UPDATE relatos SET aprovado = TRUE WHERE id = %s', (relato_id,))
            cur.execute("""
                SELECT r.titulo, u.email
                FROM relatos r
                LEFT JOIN users u ON r.user_id = u.id
                WHERE r.id = %s
            """, (relato_id,))
            relato_info = cur.fetchone()

            db.commit()
            cur.close()

            # --- CÓDIGO PARA ENVIAR E-MAIL AO USUÁRIO ---
            # Verifica se o relato foi encontrado e se tem um e-mail de usuário associado
            if relato_info and relato_info['email']:
                try:
                    # Gera a URL completa para o relato
                    relato_url = url_for('relato', relato_id=relato_id, _external=True)

                    # Prepara os dados para a função de e-mail
                    email_data = {
                        'titulo': relato_info['titulo'],
                        'relato_url': relato_url
                    }
                    
                    app_context = current_app._get_current_object()
                    
                    # Inicia a thread para enviar o e-mail em segundo plano
                    email_thread = Thread(
                        target=send_approval_notification,
                        args=(app_context, relato_info['email'], email_data)
                    )
                    email_thread.start()
                except Exception as e:
                    current_app.logger.error(f"Erro ao iniciar a thread de e-mail de aprovação: {e}")

            flash(f'Relato #{relato_id} foi aprovado com sucesso!')
        else:
            flash('Erro de validação ao aprovar o relato.')
        return safe_redirect('admin_relatos', filtro=request.args.get('filtro', 'pendentes'))

    @app.route('/admin/delete/<int:relato_id>', methods=['POST'])
    @auth_required
    def delete_relato(relato_id):
        form = AdminActionForm()
        if form.validate_on_submit():
            db = get_db()
            cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute('SELECT imagem_url, audio_url FROM relatos WHERE id = %s', (relato_id,))
            midia = cur.fetchone()
            if midia:
                delete_cloudinary_midia(midia['imagem_url'], resource_type='image')
                delete_cloudinary_midia(midia['audio_url'], resource_type='audio')

            cur.execute('DELETE FROM relatos WHERE id = %s', (relato_id,))
            db.commit()
            cur.close()
            flash(f'Relato #{relato_id} e seus dados associados foram excluídos!')
        else:
            flash('Erro de validação ao deletar o relato.')
        return safe_redirect('admin_relatos', filtro=request.args.get('filtro', 'pendentes'))


    @app.route('/admin/delete_comment/<int:comment_id>', methods=['POST'])
    @auth_required
    def delete_comment(comment_id):
        form = AdminActionForm()
        if form.validate_on_submit():
            db = get_db()
            cur = db.cursor()
            cur.execute('DELETE FROM comentarios WHERE id = %s', (comment_id,))
            db.commit()
            if cur.rowcount > 0:
                flash(f'Comentário #{comment_id} foi excluído com sucesso!')
            else:
                flash('Comentário não encontrado.')
            cur.close()
        else:
            flash('Erro de validação ao deletar comentário.')
        return safe_redirect('admin_relatos', filtro=request.args.get('filtro', 'denunciados'))

    @app.route('/admin/unreport_comment/<int:comment_id>', methods=['POST'])
    @auth_required
    def unreport_comment(comment_id):
        form = AdminActionForm()
        if form.validate_on_submit():
            db = get_db()
            cur = db.cursor()
            cur.execute('UPDATE comentarios SET denunciado = FALSE WHERE id = %s', (comment_id,))
            db.commit()
            if cur.rowcount > 0:
                flash(f'Denúncia do comentário #{comment_id} foi removida.')
            else:
                flash('Comentário não encontrado.')
            cur.close()
        else:
            flash('Erro de validação ao remover denúncia.')
        return safe_redirect('admin_relatos', filtro='denunciados')

    @app.route('/admin/lendas')
    @auth_required
    def admin_lendas():
        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT * FROM lendas ORDER BY id DESC')
        todas_lendas = cur.fetchall()
        cur.close()
        action_form = AdminActionForm()
        return render_template('admin_lendas.html', lendas=todas_lendas, action_form=action_form)

    @app.route('/admin/lenda/add', methods=['GET', 'POST'])
    @auth_required
    def add_lenda():
        form = LendaForm()
        locais_choices = sorted(current_app.config['LOCAIS_UEM'].keys())
        form.local.choices = [(l, l) for l in locais_choices]

        if form.validate_on_submit():
            titulo = form.titulo.data
            descricao = form.descricao.data
            local = form.local.data
            imagem_file = form.imagem.data
            imagem_url = None

            if imagem_file:
                try:
                    upload_result = cloudinary.uploader.upload(imagem_file, folder="observatorio_uem_lendas")
                    imagem_url = upload_result.get('secure_url')
                except Exception as e:
                    flash(f'Erro no upload da imagem: {e}')
                    return render_template('admin_lenda_form.html', form=form, title="Adicionar Nova Lenda")

            db = get_db()
            cur = db.cursor()
            cur.execute('INSERT INTO lendas (titulo, descricao, local, imagem_url) VALUES (%s, %s, %s, %s)',
                       (titulo, descricao, local, imagem_url))
            db.commit()
            cur.close()
            flash('Nova lenda adicionada com sucesso!')
            return safe_redirect('admin_lendas')

        return render_template('admin_lenda_form.html', form=form, title="Adicionar Nova Lenda")

    @app.route('/admin/lenda/edit/<int:lenda_id>', methods=['GET', 'POST'])
    @auth_required
    def edit_lenda(lenda_id):
        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT * FROM lendas WHERE id = %s', (lenda_id,))
        lenda = cur.fetchone()
        cur.close()
        if lenda is None:
            flash('Lenda não encontrada.')
            return safe_redirect('admin_lendas')

        form = LendaForm(obj=lenda)
        locais_choices = sorted(current_app.config['LOCAIS_UEM'].keys())
        form.local.choices = [(l, l) for l in locais_choices]

        if form.validate_on_submit():
            titulo = form.titulo.data
            descricao = form.descricao.data
            local = form.local.data
            imagem_file = form.imagem.data
            imagem_url = lenda['imagem_url']

            if imagem_file:
                try:
                    upload_result = cloudinary.uploader.upload(imagem_file, folder="observatorio_uem_lendas")
                    imagem_url = upload_result.get('secure_url')
                    # Deleta imagem antiga se uma nova foi enviada com sucesso
                    delete_cloudinary_midia(lenda['imagem_url'])
                except Exception as e:
                    flash(f'Erro no upload da nova imagem: {e}')
                    return render_template('admin_lenda_form.html', form=form, title=f"Editar Lenda #{lenda['id']}")

            db_conn = get_db()
            cur_conn = db_conn.cursor()
            cur_conn.execute('UPDATE lendas SET titulo = %s, descricao = %s, local = %s, imagem_url = %s WHERE id = %s',
                       (titulo, descricao, local, imagem_url, lenda_id))
            db_conn.commit()
            cur_conn.close()
            flash(f'Lenda #{lenda_id} atualizada com sucesso!')
            return safe_redirect('admin_lendas')

        return render_template('admin_lenda_form.html', form=form, title=f"Editar Lenda #{lenda['id']}")

    @app.route('/admin/lenda/delete/<int:lenda_id>', methods=['POST'])
    @auth_required
    def delete_lenda(lenda_id):
        form = AdminActionForm()
        if form.validate_on_submit():
            db = get_db()
            cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute('SELECT imagem_url FROM lendas WHERE id = %s', (lenda_id,))
            lenda = cur.fetchone()
            if lenda:
                delete_cloudinary_midia(lenda['imagem_url'])
                cur.execute('DELETE FROM lendas WHERE id = %s', (lenda_id,))
                db.commit()
                flash(f'Lenda #{lenda_id} foi excluída com sucesso!')
            else:
                flash("Lenda não encontrada.")
            cur.close()
        else:
            flash("Erro de validação.")
        return safe_redirect('admin_lendas')