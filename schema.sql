-- Remove tabelas antigas se existirem, para garantir uma inicialização limpa
-- Esta parte é opcional e segura para desenvolvimento, mas perigosa em produção.
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS lendas CASCADE;
DROP TABLE IF EXISTS testemunhas CASCADE;
DROP TABLE IF EXISTS votos CASCADE;
DROP TABLE IF EXISTS comentarios CASCADE;
DROP TABLE IF EXISTS relatos CASCADE;

-- Cria a tabela de usuários
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    google_id VARCHAR(255) UNIQUE NOT NULL,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    profile_pic_url VARCHAR(255),
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Cria a tabela principal de relatos
CREATE TABLE relatos (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(100) NOT NULL,
    descricao TEXT NOT NULL,
    local VARCHAR(255) NOT NULL,
    categoria VARCHAR(50) NOT NULL,
    imagem_url VARCHAR(255),
    audio_url TEXT,
    aprovado BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    votos_acredito INTEGER NOT NULL DEFAULT 0,
    votos_cetico INTEGER NOT NULL DEFAULT 0,
    votos_testemunha INTEGER NOT NULL DEFAULT 0,
    ip_address VARCHAR(45),
    city VARCHAR(100),
    user_agent VARCHAR(255),
    -- user_id pode ser NULL para relatos anônimos
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
);

-- Cria a tabela de comentários (CORRIGIDA)
CREATE TABLE comentarios (
    id SERIAL PRIMARY KEY,
    relato_id INTEGER NOT NULL REFERENCES relatos(id) ON DELETE CASCADE,
    -- user_id é para usuários logados, pode ser NULL
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    -- autor é para usuários anônimos, pode ser NULL
    autor VARCHAR(50),
    texto VARCHAR(500) NOT NULL,
    denunciado BOOLEAN NOT NULL DEFAULT FALSE,
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),
    city VARCHAR(100),
    user_agent VARCHAR(255)
);

-- Cria a tabela de votos
CREATE TABLE votos (
    id SERIAL PRIMARY KEY,
    relato_id INTEGER NOT NULL REFERENCES relatos(id) ON DELETE CASCADE,
    session_id VARCHAR(36) NOT NULL,
    tipo_voto VARCHAR(10) NOT NULL,
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),
    city VARCHAR(100),
    user_agent VARCHAR(255)
);

-- Cria a tabela de testemunhas
CREATE TABLE testemunhas (
    id SERIAL PRIMARY KEY,
    relato_id INTEGER NOT NULL REFERENCES relatos(id) ON DELETE CASCADE,
    session_id VARCHAR(36) NOT NULL,
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),
    city VARCHAR(100),
    user_agent VARCHAR(255)
);

-- Cria a tabela de lendas
CREATE TABLE lendas (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(100) NOT NULL,
    descricao TEXT NOT NULL,
    local VARCHAR(255) NOT NULL,
    imagem_url VARCHAR(255)
);
