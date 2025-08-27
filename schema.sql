-- Apaga as tabelas existentes para recriá-las com a nova estrutura
DROP TABLE IF EXISTS relatos;
DROP TABLE IF EXISTS votos;
DROP TABLE IF EXISTS comentarios;

-- Tabela principal de relatos, com colunas de metadados
CREATE TABLE relatos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    titulo TEXT NOT NULL,
    descricao TEXT NOT NULL,
    local TEXT NOT NULL,
    categoria TEXT NOT NULL,
    imagem_url TEXT,
    votos_acredito INTEGER NOT NULL DEFAULT 0,
    votos_cetico INTEGER NOT NULL DEFAULT 0,
    aprovado INTEGER NOT NULL DEFAULT 0,
    ip_address TEXT,
    city TEXT,
    user_agent TEXT
);

-- Tabela para registrar os votos individuais, com metadados
CREATE TABLE votos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relato_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    tipo_voto TEXT NOT NULL,
    ip_address TEXT,
    city TEXT,
    user_agent TEXT,
    FOREIGN KEY (relato_id) REFERENCES relatos (id),
    UNIQUE (relato_id, session_id)
);

-- Tabela para os comentários, com metadados
CREATE TABLE comentarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relato_id INTEGER NOT NULL,
    autor TEXT NOT NULL,
    texto TEXT NOT NULL,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    denunciado INTEGER NOT NULL DEFAULT 0,
    ip_address TEXT,
    city TEXT,
    user_agent TEXT,
    FOREIGN KEY (relato_id) REFERENCES relatos (id)
);
