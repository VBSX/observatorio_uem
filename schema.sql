-- Cria a tabela de usuários, somente se ela não existir
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    google_id VARCHAR(255) UNIQUE NOT NULL,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    profile_pic_url VARCHAR(255),
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

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
-- Adiciona a chave estrangeira para o usuário que enviou o relato
ALTER TABLE relatos ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;


-- Cria a tabela de comentários, somente se ela não existir
CREATE TABLE IF NOT EXISTS comentarios (
    id SERIAL PRIMARY KEY,
    relato_id INTEGER NOT NULL REFERENCES relatos(id) ON DELETE CASCADE,
    texto VARCHAR(500) NOT NULL,
    denunciado BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),
    city VARCHAR(100),
    user_agent VARCHAR(255)
);

-- Remove a coluna 'autor' antiga, se existir, pois agora usaremos o user_id
ALTER TABLE comentarios DROP COLUMN IF EXISTS autor;
-- Adiciona a chave estrangeira para o usuário que comentou
ALTER TABLE comentarios ADD COLUMN IF NOT EXISTS user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE;


-- Cria a tabela de votos, somente se ela não existir
CREATE TABLE IF NOT EXISTS votos (
    id SERIAL PRIMARY KEY,
    relato_id INTEGER NOT NULL REFERENCES relatos(id) ON DELETE CASCADE,
    session_id VARCHAR(36) NOT NULL,
    tipo_voto VARCHAR(10) NOT NULL,
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),
    city VARCHAR(100),
    user_agent VARCHAR(255)
);

-- Cria a tabela de testemunhas, somente se ela não existir
CREATE TABLE IF NOT EXISTS testemunhas (
    id SERIAL PRIMARY KEY,
    relato_id INTEGER NOT NULL REFERENCES relatos(id) ON DELETE CASCADE,
    session_id VARCHAR(36) NOT NULL,
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),
    city VARCHAR(100),
    user_agent VARCHAR(255)
);

-- Cria a tabela de lendas, somente se ela não existir
CREATE TABLE IF NOT EXISTS lendas (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(100) NOT NULL,
    descricao TEXT NOT NULL,
    local VARCHAR(255) NOT NULL,
    imagem_url VARCHAR(255)
);
