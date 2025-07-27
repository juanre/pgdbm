-- Orders service schema
-- This migration creates tables for the order service in the 'orders' schema

-- Create order status enum in the schema
CREATE TYPE {{schema}}.order_status AS ENUM ('pending', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled');

-- Create orders table
CREATE TABLE IF NOT EXISTS {{tables.orders}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,  -- We can't reference users table as it's in different schema
    order_number VARCHAR(50) UNIQUE NOT NULL,
    status {{schema}}.order_status NOT NULL DEFAULT 'pending',
    total_amount DECIMAL(10, 2) NOT NULL,
    shipping_address JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    shipped_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON {{tables.orders}}(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON {{tables.orders}}(status);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON {{tables.orders}}(created_at DESC);

-- Order items table
CREATE TABLE IF NOT EXISTS {{tables.order_items}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES {{tables.orders}}(id) ON DELETE CASCADE,
    product_id UUID NOT NULL,  -- We can't reference products table as it's in different schema
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    total_price DECIMAL(10, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes for order items
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON {{tables.order_items}}(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON {{tables.order_items}}(product_id);

-- Create updated_at trigger function if not exists
CREATE OR REPLACE FUNCTION {{schema}}.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for orders
CREATE TRIGGER orders_updated_at
    BEFORE UPDATE ON {{tables.orders}}
    FOR EACH ROW
    EXECUTE FUNCTION {{schema}}.update_updated_at();
