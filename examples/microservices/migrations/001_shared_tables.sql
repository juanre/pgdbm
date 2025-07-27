-- Shared tables for microservices
-- These tables are used for service coordination and don't belong to any specific service

-- Service registry for service discovery
CREATE TABLE IF NOT EXISTS {{tables.service_registry}} (
    service_name VARCHAR(100) PRIMARY KEY,
    service_url VARCHAR(255) NOT NULL,
    health_check_url VARCHAR(255),
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_healthy BOOLEAN NOT NULL DEFAULT TRUE
);

-- Events table for event sourcing and inter-service communication
CREATE TABLE IF NOT EXISTS {{tables.events}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(100) NOT NULL,
    aggregate_id UUID,
    aggregate_type VARCHAR(100),
    event_data JSONB NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

-- Create indexes for events
CREATE INDEX IF NOT EXISTS idx_events_type ON {{tables.events}}(event_type);
CREATE INDEX IF NOT EXISTS idx_events_aggregate ON {{tables.events}}(aggregate_type, aggregate_id);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON {{tables.events}}(created_at);
CREATE INDEX IF NOT EXISTS idx_events_unprocessed ON {{tables.events}}(processed_at) WHERE processed_at IS NULL;

-- Circuit breaker state for resilient service calls
CREATE TABLE IF NOT EXISTS {{tables.circuit_breakers}} (
    service_name VARCHAR(100) PRIMARY KEY,
    state VARCHAR(20) NOT NULL DEFAULT 'closed',
    failure_count INTEGER NOT NULL DEFAULT 0,
    last_failure_time TIMESTAMPTZ,
    next_retry_time TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
