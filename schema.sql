-- Cria a tabela principal de relatos, somente se ela não existir
CREATE TABLE IF NOT EXISTS relatos (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(100) NOT NULL,
    descricao TEXT NOT NULL,
    local VARCHAR(255) NOT NULL,
    categoria VARCHAR(50) NOT NULL,
    imagem_url VARCHAR(255),
    aprovado BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    votos_acredito INTEGER NOT NULL DEFAULT 0,
    votos_cetico INTEGER NOT NULL DEFAULT 0,
    votos_testemunha INTEGER NOT NULL DEFAULT 0,
    ip_address VARCHAR(45),
    city VARCHAR(100),
    user_agent VARCHAR(255)
);

-- Adiciona a coluna de áudio à tabela de relatos, somente se ela não existir
ALTER TABLE relatos ADD COLUMN IF NOT EXISTS audio_url TEXT;

-- Cria a tabela de comentários, somente se ela não existir
CREATE TABLE IF NOT EXISTS comentarios (
    id SERIAL PRIMARY KEY,
    relato_id INTEGER NOT NULL,
    autor VARCHAR(50) NOT NULL,
    texto VARCHAR(500) NOT NULL,
    denunciado BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),
    city VARCHAR(100),
    user_agent VARCHAR(255),
    FOREIGN KEY (relato_id) REFERENCES relatos (id) ON DELETE CASCADE
);

-- Cria a tabela de votos, somente se ela não existir
CREATE TABLE IF NOT EXISTS votos (
    id SERIAL PRIMARY KEY,
    relato_id INTEGER NOT NULL,
    session_id VARCHAR(36) NOT NULL,
    tipo_voto VARCHAR(10) NOT NULL,
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),
    city VARCHAR(100),
    user_agent VARCHAR(255),
    FOREIGN KEY (relato_id) REFERENCES relatos (id) ON DELETE CASCADE
);

-- Cria a tabela de testemunhas, somente se ela não existir
CREATE TABLE IF NOT EXISTS testemunhas (
    id SERIAL PRIMARY KEY,
    relato_id INTEGER NOT NULL,
    session_id VARCHAR(36) NOT NULL,
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),
    city VARCHAR(100),
    user_agent VARCHAR(255),
    FOREIGN KEY (relato_id) REFERENCES relatos (id) ON DELETE CASCADE
);

-- Cria a tabela de lendas, somente se ela não existir
CREATE TABLE IF NOT EXISTS lendas (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(100) NOT NULL,
    descricao TEXT NOT NULL,
    local VARCHAR(255) NOT NULL,
    imagem_url VARCHAR(255)
);
