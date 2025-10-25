-- Analytics schema initial migration

-- Create materialized view for user statistics
CREATE MATERIALIZED VIEW IF NOT EXISTS {{schema}}.user_stats AS
SELECT
    COUNT(*) as total_users,
    COUNT(*) FILTER (WHERE is_active = true) as active_users,
    COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) as new_today,
    COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE - INTERVAL '7 days') as new_week,
    COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE - INTERVAL '30 days') as new_month
FROM users.users;

-- Create materialized view for order statistics
CREATE MATERIALIZED VIEW IF NOT EXISTS {{schema}}.order_stats AS
SELECT
    COUNT(*) as total_orders,
    COUNT(*) FILTER (WHERE status = 'pending') as pending,
    COUNT(*) FILTER (WHERE status = 'processing') as processing,
    COUNT(*) FILTER (WHERE status = 'delivered') as delivered,
    COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled,
    SUM(total_amount) FILTER (WHERE status != 'cancelled') as total_revenue,
    AVG(total_amount) FILTER (WHERE status != 'cancelled') as avg_order_value
FROM orders.orders;

-- Create daily revenue aggregate table
CREATE TABLE IF NOT EXISTS {{tables.daily_revenue}} (
    date DATE PRIMARY KEY,
    order_count INTEGER NOT NULL DEFAULT 0,
    revenue DECIMAL(10, 2) NOT NULL DEFAULT 0,
    average_order_value DECIMAL(10, 2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS daily_revenue_date ON {{tables.daily_revenue}} (date DESC);

-- Create function to refresh analytics
CREATE OR REPLACE FUNCTION {{schema}}.refresh_analytics()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW {{schema}}.user_stats;
    REFRESH MATERIALIZED VIEW {{schema}}.order_stats;

    -- Update daily revenue for today
    INSERT INTO {{tables.daily_revenue}} (date, order_count, revenue, average_order_value)
    SELECT
        CURRENT_DATE,
        COUNT(*),
        COALESCE(SUM(total_amount), 0),
        COALESCE(AVG(total_amount), 0)
    FROM orders.orders
    WHERE DATE(created_at) = CURRENT_DATE
    AND status != 'cancelled'
    ON CONFLICT (date) DO UPDATE SET
        order_count = EXCLUDED.order_count,
        revenue = EXCLUDED.revenue,
        average_order_value = EXCLUDED.average_order_value,
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;

-- Schedule periodic refresh (would use pg_cron in production)
-- SELECT cron.schedule('refresh-analytics', '*/5 * * * *', 'SELECT analytics.refresh_analytics();');
