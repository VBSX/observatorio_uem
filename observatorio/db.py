# observatorio/db.py

import psycopg2
import psycopg2.pool
import click
from flask import current_app, g
import os

# Variável global para armazenar o pool de conexões.
# Será inicializada uma única vez quando a aplicação iniciar.
pool = None

def get_db():
    """
    Obtém uma conexão do pool para a requisição atual.
    Cria a conexão se ela ainda não existir no contexto 'g' da requisição.
    """
    if 'db' not in g:
        # Pega uma conexão do pool. Esta operação é MUITO RÁPIDA.
        g.db = pool.getconn()
    return g.db

def close_db(e=None):
    """
    Devolve a conexão de volta ao pool em vez de fechá-la.
    """
    db = g.pop('db', None)
    if db is not None:
        # Devolve a conexão para o pool para ser reutilizada.
        pool.putconn(db)

def init_db():
    """Executa o ficheiro schema.sql para criar as tabelas na base de dados."""
    # Pega uma conexão temporária para inicializar o banco
    conn = pool.getconn()
    cur = conn.cursor()
    schema_path = os.path.join(current_app.root_path, '..', 'schema.sql')
    with open(schema_path, 'r', encoding='utf-8') as f:
        cur.execute(f.read())
    conn.commit()
    cur.close()
    # Devolve a conexão
    pool.putconn(conn)
    click.echo('Base de dados PostgreSQL inicializada.')

@click.command('init-db')
def init_db_command():
    """Comando de linha para inicializar a base de dados."""
    # Esta função precisa de um contexto de aplicação para funcionar
    from flask.cli import with_appcontext
    
    @with_appcontext
    def wrapped_init_db():
        # A inicialização do pool acontece em init_app, então
        # o pool já estará disponível aqui.
        init_db()
        click.echo('Base de dados inicializada com sucesso.')
    
    wrapped_init_db()


def init_app(app):
    """Registra funções da base de dados com a aplicação Flask."""
    global pool
    
    # Cria o pool de conexões UMA ÚNICA VEZ quando a aplicação é inicializada.
    # minconn=1, maxconn=10 -> Começa com 1 conexão e pode crescer até 10.
    pool = psycopg2.pool.SimpleConnectionPool(
        1, 10, dsn=app.config['DATABASE_URL']
    )
    
    # Registra o close_db para ser chamado ao final de cada requisição.
    app.teardown_appcontext(close_db)
    
    # Adiciona o comando init-db ao CLI do Flask.
    app.cli.add_command(init_db_command)