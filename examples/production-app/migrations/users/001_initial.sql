-- Users schema initial migration

-- Create users table
CREATE TABLE IF NOT EXISTS {{tables.users}} (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS users_email ON {{tables.users}} (email);
CREATE INDEX IF NOT EXISTS users_active ON {{tables.users}} (is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS users_created ON {{tables.users}} (created_at DESC);

-- Add updated_at trigger
CREATE OR REPLACE FUNCTION {{schema}}.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON {{tables.users}}
    FOR EACH ROW
    EXECUTE FUNCTION {{schema}}.update_updated_at_column();
