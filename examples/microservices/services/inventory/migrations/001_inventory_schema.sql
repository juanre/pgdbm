-- Inventory service schema
-- This migration creates tables for the inventory service in the 'inventory' schema

-- Create products table
CREATE TABLE IF NOT EXISTS {{tables.products}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    reserved_quantity INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_products_sku ON {{tables.products}}(sku);
CREATE INDEX IF NOT EXISTS idx_products_active ON {{tables.products}}(is_active);

-- Stock reservations table
CREATE TABLE IF NOT EXISTS {{tables.stock_reservations}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES {{tables.products}}(id),
    order_id UUID NOT NULL,  -- We can't reference orders table as it's in different schema
    quantity INTEGER NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    is_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes for stock reservations
CREATE INDEX IF NOT EXISTS idx_stock_reservations_product_id ON {{tables.stock_reservations}}(product_id);
CREATE INDEX IF NOT EXISTS idx_stock_reservations_order_id ON {{tables.stock_reservations}}(order_id);
CREATE INDEX IF NOT EXISTS idx_stock_reservations_expires_at ON {{tables.stock_reservations}}(expires_at);

-- Create updated_at trigger function if not exists
CREATE OR REPLACE FUNCTION {{schema}}.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for products
CREATE TRIGGER products_updated_at
    BEFORE UPDATE ON {{tables.products}}
    FOR EACH ROW
    EXECUTE FUNCTION {{schema}}.update_updated_at();
