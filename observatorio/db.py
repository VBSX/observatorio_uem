import psycopg2
import psycopg2.extras
import click
from flask import current_app, g
import os

def get_db():
    """Conecta-se à base de dados PostgreSQL, criando uma nova conexão se não existir."""
    if 'db' not in g:
        try:
            # Usa a URL de conexão completa fornecida pelo Neon.
            g.db = psycopg2.connect(current_app.config['DATABASE_URL'])
        except psycopg2.OperationalError as e:
            # Loga um erro claro se a conexão falhar.
            current_app.logger.error(f"Erro ao conectar à base de dados PostgreSQL: {e}")
            raise
    return g.db

def close_db(e=None):
    """Fecha a conexão com a base de dados."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Executa o ficheiro schema.sql para criar as tabelas na base de dados."""
    db = get_db()
    cur = db.cursor()
    schema_path = os.path.join(current_app.root_path, '..', 'schema.sql')
    with open(schema_path, 'r', encoding='utf-8') as f:
        cur.execute(f.read())
    db.commit()
    cur.close()
    click.echo('Base de dados PostgreSQL inicializada.')

@click.command('init-db')
def init_db_command():
    """Comando de linha para inicializar a base de dados."""
    init_db()
    click.echo('Base de dados inicializada com sucesso.')

def init_app(app):
    """Registra funções da base de dados com a aplicação Flask."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
