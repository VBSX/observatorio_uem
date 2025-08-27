# observatorio/routes_admin.py

from flask import render_template, request, flash, current_app
from collections import defaultdict
import cloudinary.uploader

from .db import get_db
from .utils import auth_required, safe_redirect

def register_admin_routes(app):
    """Registra todas as rotas de admin na instância principal do Flask."""

    @app.route('/admin')
    @auth_required
    def admin():
        return safe_redirect('admin_relatos')

    @app.route('/admin/relatos')
    @auth_required
    def admin_relatos():
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
        query += ' ORDER BY id DESC'
        if filtro_status == 'todos':
            query = 'SELECT * FROM relatos ORDER BY aprovado ASC, id DESC'
            params = []
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
        return safe_redirect('admin_relatos', filtro=request.args.get('filtro', 'pendentes'))

    @app.route('/admin/delete/<int:relato_id>', methods=['POST'])
    @auth_required
    def delete_relato(relato_id):
        db = get_db()
        db.execute('DELETE FROM votos WHERE relato_id = ?', (relato_id,))
        db.execute('DELETE FROM comentarios WHERE relato_id = ?', (relato_id,))
        db.execute('DELETE FROM testemunhas WHERE relato_id = ?', (relato_id,))
        db.execute('DELETE FROM relatos WHERE id = ?', (relato_id,))
        db.commit()
        flash(f'Relato #{relato_id} e seus dados associados foram excluídos!')
        return safe_redirect('admin_relatos', filtro=request.args.get('filtro', 'pendentes'))

    @app.route('/admin/delete_comment/<int:comment_id>', methods=['POST'])
    @auth_required
    def delete_comment(comment_id):
        db = get_db()
        if db.execute('SELECT id FROM comentarios WHERE id = ?', (comment_id,)).fetchone():
            db.execute('DELETE FROM comentarios WHERE id = ?', (comment_id,))
            db.commit()
            flash(f'Comentário #{comment_id} foi excluído com sucesso!')
        else:
            flash('Comentário não encontrado.')
        return safe_redirect('admin_relatos', filtro=request.args.get('filtro', 'denunciados'))

    @app.route('/admin/unreport_comment/<int:comment_id>', methods=['POST'])
    @auth_required
    def unreport_comment(comment_id):
        db = get_db()
        if db.execute('SELECT id FROM comentarios WHERE id = ?', (comment_id,)).fetchone():
            db.execute('UPDATE comentarios SET denunciado = 0 WHERE id = ?', (comment_id,))
            db.commit()
            flash(f'Denúncia do comentário #{comment_id} foi removida.')
        else:
            flash('Comentário não encontrado.')
        return safe_redirect('admin_relatos', filtro='denunciados')

    @app.route('/admin/lendas')
    @auth_required
    def admin_lendas():
        db = get_db()
        todas_lendas = db.execute('SELECT * FROM lendas ORDER BY id DESC').fetchall()
        return render_template('admin_lendas.html', lendas=todas_lendas)

    @app.route('/admin/lenda/add', methods=['GET', 'POST'])
    @auth_required
    def add_lenda():
        locais_sorted = sorted(current_app.config['LOCAIS_UEM'].keys())
        if request.method == 'POST':
            titulo = request.form['titulo']
            descricao = request.form['descricao']
            local = request.form['local']
            if not all([titulo, descricao, local]):
                flash('Todos os campos são obrigatórios.')
            else:
                imagem_url = None
                imagem_file = request.files.get('imagem')
                if imagem_file and imagem_file.filename != '':
                    try:
                        upload_result = cloudinary.uploader.upload(imagem_file, folder="observatorio_uem_lendas")
                        imagem_url = upload_result.get('secure_url')
                    except Exception as e:
                        flash(f'Erro no upload da imagem: {e}')
                        return render_template('admin_lenda_form.html', lenda=request.form, locais=locais_sorted, title="Adicionar Nova Lenda")
                db = get_db()
                db.execute('INSERT INTO lendas (titulo, descricao, local, imagem_url) VALUES (?, ?, ?, ?)',
                           (titulo, descricao, local, imagem_url))
                db.commit()
                flash('Nova lenda adicionada com sucesso!')
                return safe_redirect('admin_lendas')
        return render_template('admin_lenda_form.html', lenda={}, locais=locais_sorted, title="Adicionar Nova Lenda")

    @app.route('/admin/lenda/edit/<int:lenda_id>', methods=['GET', 'POST'])
    @auth_required
    def edit_lenda(lenda_id):
        db = get_db()
        lenda = db.execute('SELECT * FROM lendas WHERE id = ?', (lenda_id,)).fetchone()
        if lenda is None:
            flash('Lenda não encontrada.')
            return safe_redirect('admin_lendas')
        locais_sorted = sorted(current_app.config['LOCAIS_UEM'].keys())
        if request.method == 'POST':
            titulo = request.form['titulo']
            descricao = request.form['descricao']
            local = request.form['local']
            if not all([titulo, descricao, local]):
                flash('Todos os campos são obrigatórios.')
            else:
                imagem_url = lenda['imagem_url']
                imagem_file = request.files.get('imagem')
                if imagem_file and imagem_file.filename != '':
                    try:
                        upload_result = cloudinary.uploader.upload(imagem_file, folder="observatorio_uem_lendas")
                        imagem_url = upload_result.get('secure_url')
                    except Exception as e:
                        flash(f'Erro no upload da nova imagem: {e}')
                        return render_template('admin_lenda_form.html', lenda=lenda, locais=locais_sorted, title=f"Editar Lenda #{lenda['id']}")
                db.execute('UPDATE lendas SET titulo = ?, descricao = ?, local = ?, imagem_url = ? WHERE id = ?',
                           (titulo, descricao, local, imagem_url, lenda_id))
                db.commit()
                flash(f'Lenda #{lenda_id} atualizada com sucesso!')
                return safe_redirect('admin_lendas')
        return render_template('admin_lenda_form.html', lenda=lenda, locais=locais_sorted, title=f"Editar Lenda #{lenda['id']}")

    @app.route('/admin/lenda/delete/<int:lenda_id>', methods=['POST'])
    @auth_required
    def delete_lenda(lenda_id):
        db = get_db()
        db.execute('DELETE FROM lendas WHERE id = ?', (lenda_id,))
        db.commit()
        flash(f'Lenda #{lenda_id} foi excluída com sucesso!')
        return safe_redirect('admin_lendas')