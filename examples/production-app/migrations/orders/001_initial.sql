-- Orders schema initial migration

-- Create orders table
CREATE TABLE IF NOT EXISTS {{tables.orders}} (
    id SERIAL PRIMARY KEY,
    order_number VARCHAR(50) UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    total_amount DECIMAL(10, 2) NOT NULL DEFAULT 0,
    shipping_address TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT status_check CHECK (status IN ('pending', 'processing', 'shipped', 'delivered', 'cancelled'))
);

-- Create order items table
CREATE TABLE IF NOT EXISTS {{tables.order_items}} (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES {{tables.orders}}(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    price DECIMAL(10, 2) NOT NULL,
    total DECIMAL(10, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS orders_user ON {{tables.orders}} (user_id);
CREATE INDEX IF NOT EXISTS orders_status ON {{tables.orders}} (status);
CREATE INDEX IF NOT EXISTS orders_created ON {{tables.orders}} (created_at DESC);
CREATE INDEX IF NOT EXISTS orders_number ON {{tables.orders}} (order_number);

CREATE INDEX IF NOT EXISTS order_items_order ON {{tables.order_items}} (order_id);
CREATE INDEX IF NOT EXISTS order_items_product ON {{tables.order_items}} (product_id);

-- Add updated_at trigger for orders
CREATE OR REPLACE FUNCTION {{schema}}.update_orders_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_orders_updated_at
    BEFORE UPDATE ON {{tables.orders}}
    FOR EACH ROW
    EXECUTE FUNCTION {{schema}}.update_orders_updated_at();
