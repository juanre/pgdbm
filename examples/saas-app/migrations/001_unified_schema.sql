-- Row-level multi-tenant SaaS schema
-- All tenants share the same tables, isolated by tenant_id column

-- Enum types
CREATE TYPE tenant_plan AS ENUM ('free', 'starter', 'pro', 'enterprise');
CREATE TYPE tenant_status AS ENUM ('active', 'suspended', 'cancelled');
CREATE TYPE project_status AS ENUM ('planning', 'active', 'on_hold', 'completed', 'cancelled');

-- Update timestamp function
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Tenants table
CREATE TABLE {{tables.tenants}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug VARCHAR(63) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    plan tenant_plan NOT NULL DEFAULT 'free',
    status tenant_status NOT NULL DEFAULT 'active',
    metadata JSONB DEFAULT '{}',

    -- Billing
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),

    -- Limits
    max_projects INTEGER NOT NULL DEFAULT 10,
    max_users INTEGER NOT NULL DEFAULT 5,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    suspended_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ
);

CREATE INDEX idx_tenants_status ON {{tables.tenants}}(status);
CREATE INDEX idx_tenants_plan ON {{tables.tenants}}(plan);
CREATE INDEX idx_tenants_slug ON {{tables.tenants}}(slug);

-- Users table
CREATE TABLE {{tables.users}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    api_key VARCHAR(64) UNIQUE,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    tenant_id UUID REFERENCES {{tables.tenants}}(id) ON DELETE CASCADE,

    -- Profile
    display_name VARCHAR(255),
    avatar_url VARCHAR(500),
    timezone VARCHAR(50) DEFAULT 'UTC',

    -- Permissions within tenant
    role VARCHAR(50) DEFAULT 'member',
    permissions JSONB DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,
    deactivated_at TIMESTAMPTZ
);

CREATE INDEX idx_users_tenant_id ON {{tables.users}}(tenant_id);
CREATE INDEX idx_users_email ON {{tables.users}}(email);
CREATE INDEX idx_users_api_key ON {{tables.users}}(api_key) WHERE api_key IS NOT NULL;
CREATE INDEX idx_users_tenant_active ON {{tables.users}}(tenant_id, is_active);

-- Projects table
CREATE TABLE {{tables.projects}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES {{tables.tenants}}(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status project_status NOT NULL DEFAULT 'planning',
    owner_id UUID NOT NULL REFERENCES {{tables.users}}(id),
    metadata JSONB DEFAULT '{}',

    -- Dates
    start_date DATE,
    end_date DATE,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_projects_tenant ON {{tables.projects}}(tenant_id);
CREATE INDEX idx_projects_owner ON {{tables.projects}}(owner_id);
CREATE INDEX idx_projects_status ON {{tables.projects}}(status);
CREATE INDEX idx_projects_tenant_status ON {{tables.projects}}(tenant_id, status);

-- Tasks table
CREATE TABLE {{tables.agents}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES {{tables.tenants}}(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES {{tables.projects}}(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    assigned_to UUID REFERENCES {{tables.users}}(id),
    is_completed BOOLEAN NOT NULL DEFAULT FALSE,
    due_date DATE,
    priority INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_tasks_tenant ON {{tables.agents}}(tenant_id);
CREATE INDEX idx_tasks_project ON {{tables.agents}}(project_id);
CREATE INDEX idx_tasks_assigned ON {{tables.agents}}(assigned_to);
CREATE INDEX idx_tasks_tenant_completed ON {{tables.agents}}(tenant_id, is_completed);

-- Project members junction table
CREATE TABLE {{tables.project_members}} (
    project_id UUID NOT NULL REFERENCES {{tables.projects}}(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES {{tables.users}}(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL DEFAULT 'viewer',
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (project_id, user_id)
);

CREATE INDEX idx_project_members_user ON {{tables.project_members}}(user_id);

-- Comments
CREATE TABLE {{tables.comments}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES {{tables.tenants}}(id) ON DELETE CASCADE,
    task_id UUID NOT NULL REFERENCES {{tables.agents}}(id) ON DELETE CASCADE,
    author_id UUID NOT NULL REFERENCES {{tables.users}}(id),
    content TEXT NOT NULL,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    edited_at TIMESTAMPTZ
);

CREATE INDEX idx_comments_tenant ON {{tables.comments}}(tenant_id);
CREATE INDEX idx_comments_task ON {{tables.comments}}(task_id);
CREATE INDEX idx_comments_author ON {{tables.comments}}(author_id);

-- Tenant usage tracking
CREATE TABLE {{tables.tenant_usage}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES {{tables.tenants}}(id) ON DELETE CASCADE,
    metric_name VARCHAR(100) NOT NULL,
    metric_value INTEGER NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(tenant_id, metric_name, period_start, period_end)
);

CREATE INDEX idx_tenant_usage_tenant_period ON {{tables.tenant_usage}}(tenant_id, period_start, period_end);

-- Audit log
CREATE TABLE {{tables.audit_log}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES {{tables.tenants}}(id) ON DELETE SET NULL,
    user_id UUID REFERENCES {{tables.users}}(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id UUID,
    metadata JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_log_tenant_created ON {{tables.audit_log}}(tenant_id, created_at DESC);
CREATE INDEX idx_audit_log_user_created ON {{tables.audit_log}}(user_id, created_at DESC);

-- Triggers for updated_at
CREATE TRIGGER tenants_updated_at
    BEFORE UPDATE ON {{tables.tenants}}
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON {{tables.users}}
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER projects_updated_at
    BEFORE UPDATE ON {{tables.projects}}
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER tasks_updated_at
    BEFORE UPDATE ON {{tables.agents}}
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER comments_updated_at
    BEFORE UPDATE ON {{tables.comments}}
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- Row Level Security (optional but recommended)
-- Enable RLS on all tenant-scoped tables
ALTER TABLE {{tables.projects}} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {{tables.agents}} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {{tables.comments}} ENABLE ROW LEVEL SECURITY;

-- Example RLS policies (you'd set current_setting('app.current_tenant') in your app)
-- CREATE POLICY tenant_isolation_projects ON {{tables.projects}}
--     FOR ALL USING (tenant_id = current_setting('app.current_tenant')::uuid);
-- CREATE POLICY tenant_isolation_tasks ON {{tables.agents}}
--     FOR ALL USING (tenant_id = current_setting('app.current_tenant')::uuid);
-- CREATE POLICY tenant_isolation_comments ON {{tables.comments}}
--     FOR ALL USING (tenant_id = current_setting('app.current_tenant')::uuid);
