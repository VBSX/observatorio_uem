import os
import psycopg2
from dotenv import load_dotenv
import time

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    raise Exception("Variável de ambiente DATABASE_URL não encontrada. Verifique seu arquivo .env")

conn = None 

try:
    print("Conectando ao banco de dados Neon...")
    time_start = time.time()
    conn = psycopg2.connect(DATABASE_URL)
    

    cur = conn.cursor()
    
    print("Conexão bem-sucedida!")
    print("-" * 30)

    print("Executando consulta na tabela 'relatos'...")
    cur.execute("SELECT * FROM relatos LIMIT 5;")

    relatos = cur.fetchall()
    
    if relatos:
        print(f"Encontrados {len(relatos)} registros:")
        for relato in relatos:
            print(relato)
    else:
        print("A consulta não retornou resultados (a tabela pode estar vazia).")

    cur.close()

except psycopg2.Error as e:
    print(f"Erro ao conectar ou executar a consulta: {e}")

finally:
    if conn is not None:
        conn.close()
        print("-" * 30)
        print("Conexão com o banco de dados fechada.")
        
        print("tempo total ", time.time() - time_start)