-- Apaga as tabelas existentes para recriá-las com a nova estrutura
DROP TABLE IF EXISTS relatos;
DROP TABLE IF EXISTS votos;
DROP TABLE IF EXISTS comentarios;

-- Tabela principal de relatos, agora com categoria e contagem de votos
CREATE TABLE relatos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    titulo TEXT NOT NULL,
    descricao TEXT NOT NULL,
    local TEXT NOT NULL,
    categoria TEXT NOT NULL,
    votos_acredito INTEGER NOT NULL DEFAULT 0,
    votos_cetico INTEGER NOT NULL DEFAULT 0
);

-- Tabela para registrar os votos individuais e evitar duplicidade
CREATE TABLE votos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relato_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    tipo_voto TEXT NOT NULL, -- 'acredito' ou 'cetico'
    FOREIGN KEY (relato_id) REFERENCES relatos (id),
    UNIQUE (relato_id, session_id) -- Garante que cada sessão só pode votar uma vez por relato
);

-- Tabela para os comentários
CREATE TABLE comentarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relato_id INTEGER NOT NULL,
    autor TEXT NOT NULL,
    texto TEXT NOT NULL,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (relato_id) REFERENCES relatos (id)
);