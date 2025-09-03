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
    Verifica se a conexão está ativa antes de retorná-la, estabelecendo
    uma nova conexão se a anterior estiver fechada.
    """
    # Acessa a conexão no contexto 'g' da request.
    # A propriedade 'closed' em uma conexão psycopg2 é 0 se estiver aberta.
    if 'db' not in g or g.db.closed:
        try:
            # Se não há conexão em 'g' ou se a existente foi fechada,
            # obtemos uma nova do pool.
            g.db = pool.getconn()
        except psycopg2.OperationalError as e:
            current_app.logger.critical(f"CRITICAL: Não foi possível obter uma conexão do pool: {e}")
            # Lança a exceção para que o Flask possa retornar um erro 500.
            raise
    return g.db

def close_db(e=None):
    """
    Devolve a conexão de volta ao pool ou a fecha se ocorreu um erro.
    """
    db = g.pop('db', None)

    if db is not None:
        # Se houve uma exceção durante a request (e is not None) ou se a conexão
        # já está fechada, é mais seguro descartar a conexão em vez de devolvê-la ao pool.
        # Isso evita que uma conexão em estado inconsistente seja reutilizada.
        if e is None and not db.closed:
            pool.putconn(db)
        else:
            # Fecha a conexão permanentemente. O pool criará uma nova quando necessário.
            db.close()

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
    if pool is None:
        try:
            pool = psycopg2.pool.SimpleConnectionPool(
                1, 10, dsn=app.config['DATABASE_URL']
            )
        except psycopg2.OperationalError as e:
            app.logger.critical(f"FALHA CRÍTICA: Não foi possível criar o pool de conexões com o DB. {e}")
            raise RuntimeError(f"Could not create database connection pool: {e}")
    
    # Registra o close_db para ser chamado ao final de cada requisição.
    app.teardown_appcontext(close_db)
    
    # Adiciona o comando init-db ao CLI do Flask.
    app.cli.add_command(init_db_command)