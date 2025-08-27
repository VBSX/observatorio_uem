import sqlite3
import click
from flask import current_app, g
import os

def get_db():
    """Conecta-se ao banco de dados, criando uma nova conexão se não existir."""
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    """Fecha a conexão com o banco de dados."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Limpa os dados existentes e cria novas tabelas."""
    db = get_db()
    schema_path = os.path.join(current_app.root_path, '..', 'schema.sql')
    with open(schema_path, 'r', encoding='utf-8') as f:
        db.executescript(f.read())

@click.command('init-db')
def init_db_command():
    """Comando de linha para inicializar o banco de dados."""
    init_db()
    click.echo('Banco de dados inicializado com sucesso.')

def init_app(app):
    """Registra funções do banco de dados com a aplicação Flask."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)